import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    MaterialRequestStatus,
    TaskStatus,
    MemberRole,
)
from app.domain.import_records import (
    ImportProvenance,
    ImportProvenanceTargetType,
    import_provenance_id,
)
from app.domain.models import ActivityEvent, AgentRun, Approval, Material, MaterialRequest, Task
from app.domain.project_import import SourceType
from app.repositories.firestore import FirestoreRepository, FirestoreRepositoryStore
from app.repositories.interfaces import EntityAlreadyExistsError, VersionConflictError
from app.config.settings import RuntimeEnvironment, Settings
from app.workflows.resume import ResumeWorkflow
from app.services.project_import_provenance import ProjectImportProvenanceService
from scripts.reset_demo import reset_demo


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for Firestore integration tests",
    ),
]


def make_task(project_id: str, task_id: str = "tsk_blockwork") -> Task:
    return Task(
        id=task_id,
        project_id=project_id,
        title="First-floor blockwork",
        status=TaskStatus.PLANNED,
    )


def make_activity(project_id: str) -> ActivityEvent:
    return ActivityEvent(
        id="act_task001",
        project_id=project_id,
        actor_type=ActorType.USER,
        actor_id="usr_manager",
        action="task.updated",
        entity_type="task",
        entity_id="tsk_blockwork",
        summary="Blockwork progress updated",
    )


def make_material(project_id: str) -> Material:
    return Material(
        id="mat_cement",
        project_id=project_id,
        name="Cement",
        normalized_name="cement",
        unit="bags",
        available_quantity=Decimal("10"),
    )


@pytest.fixture
def firestore_project_id() -> str:
    return f"oga-foreman-test-{uuid4().hex}"


def test_firestore_persists_across_clients_and_isolates_projects(
    firestore_project_id: str,
) -> None:
    first_client = firestore.Client(project=firestore_project_id)
    first_repository = FirestoreRepository(first_client, Task)
    first_repository.create(make_task("prj_ridge"))
    first_repository.create(make_task("prj_other"))

    restarted_client = firestore.Client(project=firestore_project_id)
    restarted_repository = FirestoreRepository(restarted_client, Task)

    assert restarted_repository.require("prj_ridge", "tsk_blockwork").project_id == "prj_ridge"
    assert restarted_repository.require("prj_other", "tsk_blockwork").project_id == "prj_other"
    assert restarted_repository.get("prj_unknown", "tsk_blockwork") is None


def test_firestore_import_provenance_survives_restart_and_resolves_by_target(
    firestore_project_id: str,
) -> None:
    project_id = "prj_provenance123"
    target_id = "tsk_foundation123"
    initial_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project_id))
    initial_store.repository(ImportProvenance).create(
        ImportProvenance(
            id=import_provenance_id(ImportProvenanceTargetType.TASK, target_id),
            project_id=project_id,
            import_id="imp_provenance123",
            source_id="src_provenance123",
            source_checksum="d" * 64,
            source_type=SourceType.MARKDOWN,
            source_name="trusted-plan.md",
            target_entity_type=ImportProvenanceTargetType.TASK,
            target_entity_id=target_id,
            imported_by="usr_admin123",
            imported_at=datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
            idempotency_key="project-import:provenance:task",
        )
    )

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=firestore_project_id))
    provenance = ProjectImportProvenanceService(restarted_store).get_for_target(
        ProjectAccessContext(
            actor=AuthenticatedUser(user_id="usr_viewer123", subject="test"),
            project_id=project_id,
            role=MemberRole.VIEWER,
        ),
        target_entity_type=ImportProvenanceTargetType.TASK,
        target_entity_id=target_id,
    )

    assert provenance.import_id == "imp_provenance123"
    assert provenance.source_checksum == "d" * 64
    assert provenance.target_entity_id == target_id


def test_firestore_transaction_commits_mutation_and_activity_atomically(
    firestore_project_id: str,
) -> None:
    client = firestore.Client(project=firestore_project_id)
    store = FirestoreRepositoryStore(client)
    tasks = store.repository(Task)
    activities = store.repository(ActivityEvent)
    current = tasks.create(make_task("prj_ridge"))

    def update_with_activity(transaction) -> None:
        transaction.repository(Task).save(
            current.model_copy(update={"completion_percent": Decimal("50")}),
            expected_version=current.version,
        )
        transaction.repository(ActivityEvent).create(make_activity("prj_ridge"))

    store.run_transaction(update_with_activity)

    assert tasks.require("prj_ridge", "tsk_blockwork").completion_percent == 50
    assert activities.require("prj_ridge", "act_task001").entity_id == "tsk_blockwork"


def test_firestore_session_reuses_reads_for_cross_collection_updates(
    firestore_project_id: str,
) -> None:
    client = firestore.Client(project=firestore_project_id)
    store = FirestoreRepositoryStore(client)
    store.repository(Task).create(make_task("prj_ridge"))
    store.repository(Material).create(make_material("prj_ridge"))

    def update_task_and_material(session) -> None:
        task = session.repository(Task).require("prj_ridge", "tsk_blockwork")
        material = session.repository(Material).require("prj_ridge", "mat_cement")

        session.repository(Task).save(
            task.model_copy(update={"completion_percent": Decimal("50")}),
            expected_version=task.version,
        )
        session.repository(Material).save(
            material.model_copy(update={"available_quantity": Decimal("5")}),
            expected_version=material.version,
        )

    store.run_transaction(update_task_and_material)

    assert store.repository(Task).require(
        "prj_ridge", "tsk_blockwork"
    ).completion_percent == Decimal("50")
    assert store.repository(Material).require(
        "prj_ridge", "mat_cement"
    ).available_quantity == Decimal("5")


def test_rejected_approval_atomically_closes_request_and_waiting_run(
    firestore_project_id: str,
) -> None:
    project_id = "prj_ridge"
    event_id = "evt_rejection_test"
    resolved_at = datetime.now(UTC)
    store = FirestoreRepositoryStore(firestore.Client(project=firestore_project_id))
    store.repository(Approval).create(
        Approval(
            id="apr_rejection_test",
            project_id=project_id,
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_id": "mat_cement"},
            reason="Cement purchase needs approval",
            status=ApprovalStatus.REJECTED,
            requested_by="system",
            requested_at=resolved_at,
            resolved_at=resolved_at,
            resolved_by="usr_manager",
        )
    )
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_rejection_test",
            project_id=project_id,
            material_id="mat_cement",
            quantity=Decimal("10"),
            unit="bags",
            reason="Cement shortage",
            source_event_id=event_id,
            approval_id="apr_rejection_test",
        )
    )
    store.repository(AgentRun).create(
        AgentRun(
            id="run_rejection_test",
            project_id=project_id,
            trigger_event_id=event_id,
            workflow="material_shortage",
            status=AgentRunStatus.WAITING_FOR_APPROVAL,
            trace_id="trace_rejection_test",
        )
    )

    ResumeWorkflow(store).handle_approval_rejected(
        project_id=project_id,
        approval_id="apr_rejection_test",
        resolver_id="usr_manager",
    )

    request = store.repository(MaterialRequest).require(project_id, "mrq_rejection_test")
    run = store.repository(AgentRun).require(project_id, "run_rejection_test")
    assert request.status is MaterialRequestStatus.CANCELLED
    assert run.status is AgentRunStatus.FAILED
    assert run.error_code == "APPROVAL_REJECTED"


def test_firestore_version_conflict_rejects_stale_update(firestore_project_id: str) -> None:
    client = firestore.Client(project=firestore_project_id)
    repository = FirestoreRepository(client, Task)
    current = repository.create(make_task("prj_ridge"))
    stale = current.model_copy(update={"completion_percent": Decimal("25")})

    repository.save(
        current.model_copy(update={"completion_percent": Decimal("50")}),
        expected_version=current.version,
    )

    with pytest.raises(VersionConflictError):
        repository.save(stale, expected_version=current.version)


def test_firestore_read_cache_does_not_mask_a_concurrent_update(
    firestore_project_id: str,
) -> None:
    client = firestore.Client(project=firestore_project_id)
    first_repository = FirestoreRepository(client, Task)
    second_repository = FirestoreRepository(client, Task)
    first_repository.create(make_task("prj_ridge"))
    stale = first_repository.require("prj_ridge", "tsk_blockwork")

    second_repository.save(
        stale.model_copy(update={"completion_percent": Decimal("50")}),
        expected_version=stale.version,
    )

    with pytest.raises(VersionConflictError):
        first_repository.save(
            stale.model_copy(update={"completion_percent": Decimal("25")}),
            expected_version=stale.version,
        )


def test_firestore_transaction_maps_duplicate_create_to_repository_error(
    firestore_project_id: str,
) -> None:
    client = firestore.Client(project=firestore_project_id)
    store = FirestoreRepositoryStore(client)
    store.repository(ActivityEvent).create(make_activity("prj_ridge"))

    with pytest.raises(EntityAlreadyExistsError):
        store.run_transaction(
            lambda transaction: transaction.repository(ActivityEvent).create(
                make_activity("prj_ridge")
            )
        )


def test_reset_is_idempotent_and_does_not_delete_another_project(
    firestore_project_id: str,
) -> None:
    client = firestore.Client(project=firestore_project_id)
    tasks = FirestoreRepository(client, Task)
    tasks.create(make_task("prj_other"))
    settings = Settings(
        oga_env=RuntimeEnvironment.TEST,
        demo_mode=True,
        google_cloud_project=firestore_project_id,
        firestore_database="(default)",
    )

    first = reset_demo(client, settings=settings)
    second = reset_demo(client, settings=settings)

    restarted = FirestoreRepository(firestore.Client(project=firestore_project_id), Task)
    assert first.project_id == "prj_ridge"
    assert second.project_id == "prj_ridge"
    assert len(restarted.list("prj_ridge")) == 4
    assert restarted.require("prj_other", "tsk_blockwork").project_id == "prj_other"
