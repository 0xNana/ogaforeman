from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from pydantic import ValidationError

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import ActorType, MemberRole
from app.domain.materials import (
    MaterialLedgerEntry,
    MaterialUnitMismatchError,
)
from app.domain.models import ActivityEvent, Material
from app.repositories.interfaces import VersionConflictError
from app.repositories.memory import InMemoryRepositoryStore
from app.services.materials import (
    MaterialQuantityCommand,
    MaterialService,
    NegativeMaterialStockError,
)
from app.tools.materials import update_material_quantity


NOW = datetime(2026, 8, 7, 14, 0, tzinfo=UTC)


def make_access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman", subject="firebase-foreman"),
        project_id="prj_ridge",
        role=MemberRole.FOREMAN,
    )


def make_context(key: str = "material:evt_update001:cement") -> MutationContext:
    return MutationContext(
        project_id="prj_ridge",
        actor_type=ActorType.AGENT,
        actor_id="agt_materials",
        source_event_id="evt_update001",
        agent_run_id="run_update001",
        idempotency_key=key,
        occurred_at=NOW,
    )


def make_command(**updates: object) -> MaterialQuantityCommand:
    values: dict[str, object] = {
        "project_id": "prj_ridge",
        "material_ref": "Portland Cement",
        "delta": Decimal("5"),
        "unit": "bag",
        "expected_version": 0,
        "reason": "Five bags arrived on site.",
        "occurred_at": NOW,
    }
    values.update(updates)
    return MaterialQuantityCommand(**values)


def make_store(*, quantity: Decimal = Decimal("10")) -> InMemoryRepositoryStore:
    store = InMemoryRepositoryStore()
    store.repository(Material).create(
        Material(
            id="mat_cement",
            project_id="prj_ridge",
            name="Cement Bags",
            normalized_name="cement bags",
            aliases=["Portland Cement", "50kg Cement"],
            unit="bags",
            available_quantity=quantity,
        )
    )
    return store


def test_alias_resolves_to_canonical_id_and_unit_alias_is_normalized() -> None:
    store = make_store()

    result = update_material_quantity(
        make_command(),
        service=MaterialService(store),
        access=make_access(),
        context=make_context(),
    )

    assert result.material.id == "mat_cement"
    assert result.material.available_quantity == 15
    assert result.material.unit == "bags"
    assert result.ledger_entry.material_id == "mat_cement"
    assert result.ledger_entry.unit == "bags"
    assert result.ledger_entry.quantity_delta == 5
    assert result.ledger_entry.balance_after == 15
    assert len(store.repository(MaterialLedgerEntry).list("prj_ridge")) == 1
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_duplicate_ledger_event_replays_without_second_quantity_change() -> None:
    store = make_store()
    service = MaterialService(store)

    first = service.update_quantity(make_access(), make_command(), make_context())
    replay = service.update_quantity(make_access(), make_command(), make_context())

    assert first.duplicate is False
    assert replay.duplicate is True
    assert replay.material.available_quantity == 15
    assert replay.ledger_entry.id == first.ledger_entry.id
    assert len(store.repository(MaterialLedgerEntry).list("prj_ridge")) == 1
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_unknown_or_mismatched_units_are_rejected_without_writes() -> None:
    store = make_store()
    service = MaterialService(store)

    with pytest.raises(ValidationError, match="unknown material unit"):
        make_command(unit="pallets")

    with pytest.raises(MaterialUnitMismatchError):
        service.update_quantity(
            make_access(),
            make_command(unit="kg"),
            make_context(),
        )

    assert store.repository(Material).require("prj_ridge", "mat_cement").version == 0
    assert store.repository(MaterialLedgerEntry).list("prj_ridge") == ()


def test_negative_stock_or_reserved_stock_violation_is_rejected_atomically() -> None:
    store = make_store()

    with pytest.raises(NegativeMaterialStockError):
        MaterialService(store).update_quantity(
            make_access(),
            make_command(delta=Decimal("-11"), unit="bags"),
            make_context(),
        )

    assert store.repository(Material).require("prj_ridge", "mat_cement").available_quantity == 10
    assert store.repository(MaterialLedgerEntry).list("prj_ridge") == ()
    assert store.repository(ActivityEvent).list("prj_ridge") == ()


def test_concurrent_updates_with_same_version_have_one_winner() -> None:
    store = make_store()
    service = MaterialService(store)
    barrier = Barrier(2)

    def adjust(index: int):
        barrier.wait()
        return service.update_quantity(
            make_access(),
            make_command(
                material_ref="mat_cement",
                delta=Decimal("-7"),
                unit="bags",
                reason=f"Issued stock batch {index}.",
            ),
            make_context(f"material:evt_update00{index}:cement"),
        )

    results: list[object] = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(adjust, index) for index in (1, 2)]
        for future in futures:
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - asserting the conflict class below
                errors.append(exc)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], VersionConflictError)
    assert store.repository(Material).require("prj_ridge", "mat_cement").available_quantity == 3
    assert len(store.repository(MaterialLedgerEntry).list("prj_ridge")) == 1
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1
