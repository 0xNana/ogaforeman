from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
import os
from threading import Barrier
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import ActorType, MemberRole
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import ActivityEvent, Material
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.interfaces import VersionConflictError
from app.services.materials import CreateMaterialCommand, MaterialQuantityCommand, MaterialService


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for material integration",
    ),
]


def test_firestore_material_creation_with_initial_stock_is_atomic() -> None:
    cloud_project = f"oga-material-create-test-{uuid4().hex}"
    project_id = "prj_ridge"
    now = datetime(2026, 8, 10, 9, 30, tzinfo=UTC)
    store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager", subject="firebase-manager"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )

    result = MaterialService(store).create_material(
        access,
        CreateMaterialCommand(
            project_id=project_id,
            name="Timber",
            unit="pieces",
            available_quantity=Decimal("12"),
            minimum_required_quantity=Decimal("8"),
        ),
        MutationContext(
            project_id=project_id,
            actor_type=ActorType.USER,
            actor_id="usr_manager",
            idempotency_key="setup:material:timber",
            occurred_at=now,
        ),
    )

    assert result.material.available_quantity == 12
    assert len(store.repository(MaterialLedgerEntry).list(project_id)) == 1
    assert len(store.repository(ActivityEvent).list(project_id)) == 1


def test_firestore_material_concurrency_is_atomic_and_append_only() -> None:
    cloud_project = f"oga-material-test-{uuid4().hex}"
    project_id = "prj_ridge"
    now = datetime(2026, 8, 7, 14, 30, tzinfo=UTC)
    store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    store.repository(Material).create(
        Material(
            id="mat_cement",
            project_id=project_id,
            name="Cement Bags",
            normalized_name="cement bags",
            aliases=["Portland Cement"],
            unit="bags",
            available_quantity=Decimal("10"),
        )
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman", subject="firebase-foreman"),
        project_id=project_id,
        role=MemberRole.FOREMAN,
    )
    barrier = Barrier(2)

    def adjust(index: int):
        barrier.wait()
        return MaterialService(store).update_quantity(
            access,
            MaterialQuantityCommand(
                project_id=project_id,
                material_id="mat_cement",
                quantity_delta=Decimal("-7"),
                unit="bags",
                expected_version=0,
                reason=f"Issued batch {index}.",
                occurred_at=now,
            ),
            MutationContext(
                project_id=project_id,
                actor_type=ActorType.AGENT,
                actor_id="agt_materials",
                source_event_id=f"evt_update00{index}",
                agent_run_id="run_update001",
                idempotency_key=f"material:evt_update00{index}:cement",
                occurred_at=now,
            ),
        )

    successes = []
    failures = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(adjust, index) for index in (1, 2)]
        for future in futures:
            try:
                successes.append(future.result())
            except Exception as exc:  # noqa: BLE001 - verifying one optimistic conflict
                failures.append(exc)

    restarted = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], VersionConflictError)
    assert restarted.repository(Material).require(project_id, "mat_cement").available_quantity == 3
    assert len(restarted.repository(MaterialLedgerEntry).list(project_id)) == 1
    assert len(restarted.repository(ActivityEvent).list(project_id)) == 1
