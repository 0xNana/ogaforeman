from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.conversation import (
    ConversationMaterialCommand,
    ConversationTaskCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    MaterialOperation,
    MutationPolicyClass,
    MutationPolicyDecision,
    PendingMaterialCommand,
    PendingScheduleCommand,
    PendingTaskCommand,
    ScheduleChangeCommand,
    TaskOperation,
)
from app.domain.enums import MemberRole, TaskStatus
from app.domain.models import ConversationMemory, Task
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService


def access(project_id: str = "prj_memory123") -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_ace123", subject="ace"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )


def test_memory_is_scoped_and_revalidates_referenced_entities() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_electrical123",
            project_id="prj_memory123",
            title="Electrical rough-in",
            status=TaskStatus.BLOCKED,
        )
    )
    service = ConversationMemoryService(store, ConversationEntityResolver(store))

    saved = service.remember_reference(
        access(), EntityKind.TASK, "tsk_electrical123", topic="electrical"
    )
    resolved = service.resolve_recent(access(), EntityKind.TASK)

    assert saved.actor_id == "usr_ace123"
    assert resolved.status is EntityResolutionStatus.RESOLVED
    assert resolved.entity_id == "tsk_electrical123"
    assert service.load(access("prj_other123")).recent_entities == []


def test_stale_memory_never_becomes_project_truth() -> None:
    store = InMemoryRepositoryStore()
    task = store.repository(Task).create(
        Task(id="tsk_electrical123", project_id="prj_memory123", title="Electrical rough-in")
    )
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    service.remember_reference(access(), EntityKind.TASK, task.id)
    store.repository(Task).delete(task.project_id, task.id, expected_version=0)

    resolved = service.resolve_recent(access(), EntityKind.TASK)

    assert resolved.status is EntityResolutionStatus.NOT_FOUND
    assert resolved.can_mutate is False


def test_pending_command_persists_exact_typed_actor_scoped_proposal() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    pending = PendingMaterialCommand(
        proposal_id="cpr_cement123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.AUTO_EXECUTE,
            reason_code="routine_reversible_operation",
        ),
        idempotency_key="conversation:cement:100",
        requested_action="Record Cement at 100 bags",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ConversationMaterialCommand(
            operation=MaterialOperation.SET_ON_SITE,
            material=EntityResolution(
                kind=EntityKind.MATERIAL,
                reference="cement",
                status=EntityResolutionStatus.RESOLVED,
                entity_id="mat_cement123",
                display_name="Cement",
                match_method="exact",
                can_mutate=True,
            ),
            quantity=Decimal("100"),
            unit="bags",
            expected_version=4,
        ),
    )

    saved = service.remember_command(access(), pending)

    assert saved.pending_command == pending
    assert service.require_command(access(), pending.proposal_id, saved.version) == pending
    other_actor = access().model_copy(
        update={"actor": AuthenticatedUser(user_id="usr_other123", subject="other")}
    )
    assert service.load(other_actor).pending_command is None


def test_pending_command_clear_requires_exact_proposal_identity() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    pending = PendingMaterialCommand(
        proposal_id="cpr_cement123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.AUTO_EXECUTE,
            reason_code="routine_reversible_operation",
        ),
        idempotency_key="conversation:cement:100",
        requested_action="Record Cement at 100 bags",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ConversationMaterialCommand(operation=MaterialOperation.ADD_NOTE, note="Counted"),
    )
    saved = service.remember_command(access(), pending)

    with pytest.raises(ValueError, match="does not match"):
        service.clear_command(access(), "cpr_other123", saved.version)

    cleared = service.clear_command(access(), pending.proposal_id, saved.version)
    assert cleared.pending_command is None
    assert service.clear_command(access(), pending.proposal_id, saved.version) == cleared
    with pytest.raises(ValueError, match="consumed proposal"):
        service.remember_command(access(), pending)

    second = pending.model_copy(
        update={
            "proposal_id": "cpr_second123",
            "idempotency_key": "conversation:cement:second",
        }
    )
    second_saved = service.remember_command(access(), second)
    service.clear_command(access(), second.proposal_id, second_saved.version)
    assert (
        service.clear_command(access(), pending.proposal_id, saved.version).pending_command is None
    )
    with pytest.raises(ValueError, match="consumed proposal"):
        service.remember_command(access(), pending)


def test_proposal_identity_uses_canonical_persistable_format() -> None:
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        PendingMaterialCommand(
            proposal_id="cpr_UPPERCASE",
            project_id="prj_memory123",
            actor_id="usr_ace123",
            policy_decision=MutationPolicyDecision(
                policy=MutationPolicyClass.AUTO_EXECUTE,
                reason_code="routine_reversible_operation",
            ),
            idempotency_key="conversation:invalid-id",
            requested_action="Record Cement",
            created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
            command=ConversationMaterialCommand(
                operation=MaterialOperation.SET_ON_SITE,
                quantity=Decimal("1"),
                unit="bags",
            ),
        )


def test_pending_proposal_identity_is_immutable_and_policy_is_recomputed() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    pending = PendingMaterialCommand(
        proposal_id="cpr_cement123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.AUTO_EXECUTE,
            reason_code="routine_reversible_operation",
        ),
        idempotency_key="conversation:cement:100",
        requested_action="Record Cement at 100 bags",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ConversationMaterialCommand(
            operation=MaterialOperation.SET_ON_SITE,
            quantity=Decimal("100"),
            unit="bags",
        ),
    )
    service.remember_command(access(), pending)

    with pytest.raises(ValueError, match="cannot be reused"):
        service.remember_command(
            access(), pending.model_copy(update={"requested_action": "Record 1 bag"})
        )
    with pytest.raises(ValueError, match="policy does not match"):
        service.remember_command(
            access(),
            pending.model_copy(
                update={
                    "proposal_id": "cpr_other123",
                    "policy_decision": MutationPolicyDecision(
                        policy=MutationPolicyClass.APPROVAL_REQUIRED,
                        reason_code="human_approval_required",
                        use_existing_approval=True,
                    ),
                }
            ),
        )


def test_pending_command_uses_observed_memory_version_and_round_trips_json() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    pending = PendingMaterialCommand(
        proposal_id="cpr_cement123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.AUTO_EXECUTE,
            reason_code="routine_reversible_operation",
        ),
        idempotency_key="conversation:cement:100",
        requested_action="Record Cement at 100 bags",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ConversationMaterialCommand(
            operation=MaterialOperation.SET_ON_SITE,
            quantity=Decimal("100"),
            unit="bags",
        ),
    )
    saved = service.remember_command(access(), pending)
    round_trip = ConversationMemory.model_validate_json(saved.model_dump_json())
    assert round_trip.pending_command == pending
    service.remember_pending(access(), proposed_action="new display state")

    with pytest.raises(ValueError, match="memory changed"):
        service.require_command(access(), pending.proposal_id, saved.version)
    with pytest.raises(ValueError, match="memory changed"):
        service.clear_command(access(), pending.proposal_id, saved.version)


def test_pending_schedule_rejects_nested_cross_project_scope() -> None:
    with pytest.raises(ValidationError, match="project must match"):
        PendingScheduleCommand(
            proposal_id="cpr_schedule123",
            project_id="prj_memory123",
            actor_id="usr_ace123",
            policy_decision=MutationPolicyDecision(
                policy=MutationPolicyClass.CONFIRM_FIRST,
                reason_code="consequential_reversible_change",
            ),
            idempotency_key="conversation:schedule:1",
            requested_action="Move plastering",
            created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
            command=ScheduleChangeCommand(
                project_id="prj_other123",
                task=EntityResolution(
                    kind=EntityKind.TASK,
                    reference="plastering",
                    status=EntityResolutionStatus.RESOLVED,
                    entity_id="tsk_plastering123",
                    display_name="Plastering",
                    match_method="exact",
                    can_mutate=True,
                ),
                planned_start=datetime(2026, 8, 15, 8, tzinfo=UTC),
                planned_end=datetime(2026, 8, 15, 17, tzinfo=UTC),
            ),
        )


def test_service_revalidates_copied_pending_schedule_scope() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    valid = PendingScheduleCommand(
        proposal_id="cpr_schedule123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.CONFIRM_FIRST,
            reason_code="consequential_reversible_change",
        ),
        idempotency_key="conversation:schedule:1",
        requested_action="Move plastering",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ScheduleChangeCommand(
            project_id="prj_memory123",
            task=EntityResolution(
                kind=EntityKind.TASK,
                reference="plastering",
                status=EntityResolutionStatus.RESOLVED,
                entity_id="tsk_plastering123",
                display_name="Plastering",
                match_method="exact",
                can_mutate=True,
            ),
            planned_start=datetime(2026, 8, 15, 8, tzinfo=UTC),
            planned_end=datetime(2026, 8, 15, 17, tzinfo=UTC),
        ),
    )
    bypassed = valid.model_copy(
        update={"command": valid.command.model_copy(update={"project_id": "prj_other123"})}
    )

    with pytest.raises(ValidationError, match="project must match"):
        service.remember_command(access(), bypassed)


def test_material_risk_command_cannot_be_downgraded_to_auto_execute() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    pending = PendingMaterialCommand(
        proposal_id="cpr_risk123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.AUTO_EXECUTE,
            reason_code="routine_reversible_operation",
        ),
        idempotency_key="conversation:risk:1",
        requested_action="Record risky stock update",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ConversationMaterialCommand(
            operation=MaterialOperation.SET_ON_SITE,
            quantity=Decimal("10"),
            unit="bags",
            requires_material_risk_workflow=True,
        ),
    )

    with pytest.raises(ValueError, match="existing risk workflow"):
        service.remember_command(access(), pending)


def test_task_reopen_uses_confirm_first_policy() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    pending = PendingTaskCommand(
        proposal_id="cpr_reopen123",
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.CONFIRM_FIRST,
            reason_code="consequential_reversible_change",
        ),
        idempotency_key="conversation:reopen:1",
        requested_action="Reopen plastering",
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        command=ConversationTaskCommand(
            operation=TaskOperation.CHANGE_STATUS,
            target_status=TaskStatus.IN_PROGRESS,
            reopening=True,
        ),
    )

    assert service.remember_command(access(), pending).pending_command == pending
