"""Tests for material request workflow."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.authorization import ProjectAccessContext, AuthenticatedUser
from app.domain.enums import MemberRole, ActorType
from app.domain.models import Material, MaterialRequest
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.memory import InMemoryRepositoryStore
from app.services.material_requests import (
    MaterialRequestError,
    MaterialRequestService,
    MaterialShortageCommand,
    MissingUnitError,
)
from app.workflows.runtime import RuntimeManager
from app.workflows.materials import run_materials_workflow
from app.domain.activity import MutationContext


@pytest.fixture
def store() -> RepositoryStore:
    return InMemoryRepositoryStore()


@pytest.fixture
def session(store: RepositoryStore) -> RepositorySession:
    return store


@pytest.fixture
def access() -> ProjectAccessContext:
    return ProjectAccessContext(
        project_id="prj_123",
        actor=AuthenticatedUser(user_id="usr_123", subject="sub_123", email="test@test.com"),
        role=MemberRole.MANAGER,
    )


@pytest.fixture
def setup_materials(
    session: RepositorySession,
    access: ProjectAccessContext,
) -> None:
    materials = session.repository(Material)
    materials.create(
        Material(
            id="mat_123",
            project_id="prj_123",
            name="2x4 Studs",
            normalized_name="2x4 studs",
            unit="units",
            available_quantity=Decimal("10"),
            reserved_quantity=Decimal("2"),
        )
    )
    materials.create(
        Material(
            id="mat_456",
            project_id="prj_123",
            name="Paint",
            normalized_name="paint",
            unit="litres",
            available_quantity=Decimal("5"),
            reserved_quantity=Decimal("0"),
        )
    )


def test_material_in_stock(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_materials: None,
) -> None:
    service = MaterialRequestService(store)
    runtime = RuntimeManager(store)

    result = run_materials_workflow(
        site_id="prj_123",
        item_name="2x4 Studs",
        required_qty=5.0,  # 10 avail - 2 reserved = 8 net avail (5 is less than 8)
        unit="units",
        estimated_unit_cost=10.0,
        supplier="Home Depot",
        service=service,
        runtime=runtime,
        access=access,
    )

    assert result["status"] == "in_stock"
    assert result["item_name"] == "2x4 Studs"


def test_material_shortage(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_materials: None,
) -> None:
    service = MaterialRequestService(store)
    runtime = RuntimeManager(store)

    result = run_materials_workflow(
        site_id="prj_123",
        item_name="2x4 Studs",
        required_qty=12.0,  # 8 net avail, need 12, shortage 4
        unit="units",
        estimated_unit_cost=10.0,
        supplier="Home Depot",
        service=service,
        runtime=runtime,
        access=access,
    )

    assert result["status"] == "paused_for_approval"
    assert result["net_quantity"] == 4.0
    assert result["total_estimated_cost"] == 40.0

    # Check it's persisted
    requests = store.run_transaction(lambda s: list(s.repository(MaterialRequest).list("prj_123")))
    assert len(requests) == 1
    req = requests[0]
    assert req.quantity == Decimal("4")


def test_material_request_duplicate(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_materials: None,
) -> None:
    service = MaterialRequestService(store)

    command = MaterialShortageCommand(
        project_id="prj_123",
        material_id_or_alias="2x4 Studs",
        required_quantity=Decimal("15"),
        unit="units",
        occurred_at=datetime.now(UTC),
        reason="Test",
    )

    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="same_key",
        source_event_id="evt_1234567890_abc",
    )

    result1 = service.evaluate_shortage(access, command, context)
    assert result1.is_shortage
    assert not result1.duplicate

    result2 = service.evaluate_shortage(access, command, context)
    assert result2.is_shortage
    assert result2.duplicate

    # Only 1 request persisted
    requests = store.run_transaction(lambda s: list(s.repository(MaterialRequest).list("prj_123")))
    assert len(requests) == 1


def test_material_missing_unit(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_materials: None,
) -> None:
    service = MaterialRequestService(store)
    runtime = RuntimeManager(store)

    with pytest.raises(MissingUnitError):
        run_materials_workflow(
            site_id="prj_123",
            item_name="Paint",
            required_qty=10.0,
            unit="units",  # Paint is GAL
            estimated_unit_cost=10.0,
            supplier="Home Depot",
            service=service,
            runtime=runtime,
            access=access,
        )


def test_material_request_requires_a_source_event(
    store: RepositoryStore,
    access: ProjectAccessContext,
    setup_materials: None,
) -> None:
    command = MaterialShortageCommand(
        project_id="prj_123",
        material_id_or_alias="2x4 Studs",
        required_quantity=Decimal("15"),
        unit="units",
        reason="Needed for tomorrow's framing",
    )
    context = MutationContext(
        project_id="prj_123",
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key="missing-source-event",
    )

    with pytest.raises(MaterialRequestError, match="source event"):
        MaterialRequestService(store).evaluate_shortage(access, command, context)
