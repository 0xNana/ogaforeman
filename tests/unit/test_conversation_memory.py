from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from datetime import UTC, datetime, timedelta
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
from app.domain.models import (
    ActivityEvent,
    ConversationMemory,
    ConversationProposalClaim,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService, conversation_proposal_id


def access(project_id: str = "prj_memory123") -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_ace123", subject="ace"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )


def pending_reopen(
    *,
    idempotency_key: str = "conversation:reopen:1",
    observed_memory_version: int = 0,
    created_at: datetime | None = None,
) -> PendingTaskCommand:
    created = created_at or datetime.now(UTC)
    return PendingTaskCommand(
        proposal_id=conversation_proposal_id("prj_memory123", "usr_ace123", idempotency_key),
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.CONFIRM_FIRST,
            reason_code="consequential_reversible_change",
        ),
        idempotency_key=idempotency_key,
        requested_action="Reopen plastering",
        observed_memory_version=observed_memory_version,
        created_at=created,
        expires_at=created + timedelta(minutes=15),
        command=ConversationTaskCommand(
            operation=TaskOperation.CHANGE_STATUS,
            target_status=TaskStatus.IN_PROGRESS,
            reopening=True,
        ),
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
    pending = pending_reopen()

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
    pending = pending_reopen()
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
            "idempotency_key": "conversation:cement:second",
            "proposal_id": conversation_proposal_id(
                "prj_memory123", "usr_ace123", "conversation:cement:second"
            ),
            "observed_memory_version": cleared.version,
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
    pending = pending_reopen()
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
    pending = pending_reopen()
    saved = service.remember_command(access(), pending)
    round_trip = ConversationMemory.model_validate_json(saved.model_dump_json())
    assert round_trip.pending_command == pending
    service.remember_pending(access(), proposed_action="new display state")

    with pytest.raises(ValueError, match="memory changed"):
        service.require_command(access(), pending.proposal_id, saved.version)
    with pytest.raises(ValueError, match="memory changed"):
        service.clear_command(access(), pending.proposal_id, saved.version)


def test_expired_pending_command_cannot_be_required_for_execution() -> None:
    store = InMemoryRepositoryStore()
    created_at = datetime(2020, 1, 1, 12, tzinfo=UTC)
    service = ConversationMemoryService(
        store,
        ConversationEntityResolver(store),
        clock=lambda: created_at + timedelta(minutes=5),
    )
    pending = PendingTaskCommand(
        proposal_id=conversation_proposal_id(
            "prj_memory123", "usr_ace123", "conversation:expired:1"
        ),
        project_id="prj_memory123",
        actor_id="usr_ace123",
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.CONFIRM_FIRST,
            reason_code="consequential_reversible_change",
        ),
        idempotency_key="conversation:expired:1",
        requested_action="Apply an expired change",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=15),
        observed_memory_version=0,
        observed_entity_versions={"tsk_plastering123": 4},
        command=ConversationTaskCommand(
            operation=TaskOperation.CHANGE_STATUS,
            task=EntityResolution(
                kind=EntityKind.TASK,
                reference="plastering",
                status=EntityResolutionStatus.RESOLVED,
                entity_id="tsk_plastering123",
                can_mutate=True,
            ),
            target_status=TaskStatus.IN_PROGRESS,
            reopening=True,
            expected_version=4,
        ),
    )
    saved = service.remember_command(access(), pending)

    expired_service = ConversationMemoryService(
        store,
        ConversationEntityResolver(store),
        clock=lambda: created_at + timedelta(minutes=16),
    )
    with pytest.raises(ValueError, match="expired"):
        expired_service.require_command(access(), pending.proposal_id, saved.version)
    assert expired_service.expire_command_if_due(access(), pending.proposal_id, saved.version)
    assert expired_service.load(access()).pending_command is None
    assert (
        store.repository(ConversationProposalClaim)
        .require("prj_memory123", pending.proposal_id)
        .outcome
        == "expired"
    )
    assert [
        activity.action for activity in store.repository(ActivityEvent).list("prj_memory123")
    ] == ["conversation.proposal_created", "conversation.proposal_expired"]


def test_pending_command_cannot_be_saved_against_stale_memory() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    service.remember_pending(access(), proposed_action="first state")
    current = service.remember_pending(access(), proposed_action="newer state")
    assert current.version == 1
    pending = pending_reopen(
        idempotency_key="conversation:stale-memory:1",
        observed_memory_version=0,
    )

    with pytest.raises(ValueError, match="memory changed"):
        service.remember_command(access(), pending)


@pytest.mark.parametrize(
    "pending",
    [
        PendingMaterialCommand(
            proposal_id=conversation_proposal_id(
                "prj_memory123", "usr_ace123", "conversation:auto:1"
            ),
            project_id="prj_memory123",
            actor_id="usr_ace123",
            policy_decision=MutationPolicyDecision(
                policy=MutationPolicyClass.AUTO_EXECUTE,
                reason_code="routine_reversible_operation",
            ),
            idempotency_key="conversation:auto:1",
            requested_action="Add a note",
            observed_memory_version=0,
            created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
            expires_at=datetime(2026, 8, 14, 12, 15, tzinfo=UTC),
            command=ConversationMaterialCommand(
                operation=MaterialOperation.ADD_NOTE, note="Count checked"
            ),
        ),
        PendingTaskCommand(
            proposal_id=conversation_proposal_id(
                "prj_memory123", "usr_ace123", "conversation:cancel:1"
            ),
            project_id="prj_memory123",
            actor_id="usr_ace123",
            policy_decision=MutationPolicyDecision(
                policy=MutationPolicyClass.APPROVAL_REQUIRED,
                reason_code="human_approval_required",
                use_existing_approval=True,
            ),
            idempotency_key="conversation:cancel:1",
            requested_action="Cancel plastering",
            observed_memory_version=0,
            created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
            expires_at=datetime(2026, 8, 14, 12, 15, tzinfo=UTC),
            command=ConversationTaskCommand(
                operation=TaskOperation.CHANGE_STATUS,
                target_status=TaskStatus.CANCELLED,
            ),
        ),
    ],
)
def test_only_confirm_first_commands_can_enter_pending_state(
    pending: PendingMaterialCommand | PendingTaskCommand,
) -> None:
    now = datetime(2026, 8, 14, 12, 5, tzinfo=UTC)
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store), clock=lambda: now)

    with pytest.raises(ValueError, match="only confirm-first"):
        service.remember_command(access(), pending)


def test_pending_command_rejects_fabricated_server_lifecycle_fields() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    valid = pending_reopen()

    with pytest.raises(ValueError, match="server-derived"):
        service.remember_command(
            access(), valid.model_copy(update={"proposal_id": "cpr_fabricated123"})
        )
    with pytest.raises(ValueError, match="lifecycle fields"):
        service.remember_command(access(), valid.model_copy(update={"expires_at": None}))


def test_require_command_rejects_a_tampered_persisted_envelope() -> None:
    store = InMemoryRepositoryStore()
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    valid = pending_reopen()
    tampered = valid.model_copy(
        update={
            "policy_decision": MutationPolicyDecision(
                policy=MutationPolicyClass.APPROVAL_REQUIRED,
                reason_code="human_approval_required",
                use_existing_approval=True,
            )
        }
    )
    empty = service.load(access())
    store.repository(ConversationMemory).create(
        empty.model_copy(update={"pending_command": tampered})
    )

    with pytest.raises(ValueError, match="confirm-first"):
        service.require_command(access(), tampered.proposal_id, 0)


def test_timestamp_different_exact_retry_returns_persisted_winner() -> None:
    store = InMemoryRepositoryStore()
    first = pending_reopen()
    service = ConversationMemoryService(
        store,
        ConversationEntityResolver(store),
        clock=lambda: first.created_at + timedelta(seconds=1),
    )
    saved = service.remember_command(access(), first)
    later = first.model_copy(
        update={
            "created_at": first.created_at + timedelta(milliseconds=1),
            "expires_at": first.expires_at + timedelta(milliseconds=1)
            if first.expires_at
            else None,
        }
    )

    replayed = service.remember_command(access(), later)

    assert replayed == saved
    assert replayed.pending_command == first


def test_signed_pending_payload_rejects_durable_tampering() -> None:
    store = InMemoryRepositoryStore()
    key = b"unit-conversation-proposal-signing-key-32-bytes"
    service = ConversationMemoryService(
        store,
        ConversationEntityResolver(store),
        proposal_signing_key=key,
    )
    signed = service.seal_command(pending_reopen())
    tampered = signed.model_copy(update={"requested_action": "Cancel every task"})
    empty = service.load(access())
    store.repository(ConversationMemory).create(
        empty.model_copy(update={"pending_command": tampered})
    )

    with pytest.raises(ValueError, match="signature"):
        service.require_command(access(), tampered.proposal_id, 0)


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
    pending = pending_reopen()

    assert service.remember_command(access(), pending).pending_command == pending
