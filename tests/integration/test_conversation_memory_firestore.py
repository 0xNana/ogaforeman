from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    ConversationTaskCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    MutationPolicyClass,
    MutationPolicyDecision,
    PendingScheduleCommand,
    PendingTaskCommand,
    ScheduleChangeCommand,
    TaskOperation,
)
from app.domain.enums import MemberRole, MemberStatus, TaskStatus
from app.domain.models import ActivityEvent, ConversationProposalClaim, ProjectMember, Task
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.conversation_confirmation import ConversationConfirmationService
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService, conversation_proposal_id
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_schedule_operations import ConversationScheduleService


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for conversation memory integration",
    ),
]


def test_pending_command_survives_firestore_restart_and_clear_replays() -> None:
    cloud_project = f"oga-conversation-memory-{uuid4().hex}"
    project_id = "prj_memory123"
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_ace123", subject="ace"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )
    store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    signing_key = b"firestore-conversation-signing-key-32-bytes"
    service = ConversationMemoryService(
        store,
        ConversationEntityResolver(store),
        proposal_signing_key=signing_key,
    )
    created_at = datetime.now(UTC)
    pending = service.seal_command(
        PendingTaskCommand(
            proposal_id=conversation_proposal_id(
                project_id, access.actor.user_id, "conversation:reopen:1"
            ),
            project_id=project_id,
            actor_id=access.actor.user_id,
            policy_decision=MutationPolicyDecision(
                policy=MutationPolicyClass.CONFIRM_FIRST,
                reason_code="consequential_reversible_change",
            ),
            idempotency_key="conversation:reopen:1",
            requested_action="Reopen plastering",
            observed_memory_version=0,
            created_at=created_at,
            expires_at=created_at + timedelta(minutes=15),
            command=ConversationTaskCommand(
                operation=TaskOperation.CHANGE_STATUS,
                target_status=TaskStatus.IN_PROGRESS,
                reopening=True,
            ),
        )
    )
    saved = service.remember_command(access, pending)

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    restarted = ConversationMemoryService(
        restarted_store,
        ConversationEntityResolver(restarted_store),
        proposal_signing_key=signing_key,
    )
    assert restarted.require_command(access, pending.proposal_id, saved.version) == pending

    cleared = restarted.clear_command(access, pending.proposal_id, saved.version)
    final_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    final = ConversationMemoryService(
        final_store,
        ConversationEntityResolver(final_store),
        proposal_signing_key=signing_key,
    )
    assert final.load(access).pending_command is None
    assert final.clear_command(access, pending.proposal_id, saved.version) == cleared


def test_schedule_proposal_confirms_once_after_firestore_restart() -> None:
    cloud_project = f"oga-conversation-golden-{uuid4().hex}"
    project_id = "prj_golden123"
    actor_id = "usr_manager123"
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=actor_id, subject="manager"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )
    signing_key = b"firestore-golden-proposal-signing-key-32-bytes"
    initial = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    initial.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id=actor_id,
            role=MemberRole.MANAGER,
            status=MemberStatus.ACTIVE,
        )
    )
    task = initial.repository(Task).create(
        Task(
            id="tsk_plastering123",
            project_id=project_id,
            title="Plastering",
            status=TaskStatus.PLANNED,
            planned_start=datetime(2026, 8, 17, 8, tzinfo=UTC),
            planned_end=datetime(2026, 8, 17, 17, tzinfo=UTC),
        )
    )
    schedules = ConversationScheduleService(
        initial, MutationPolicyService(), proposal_signing_key=signing_key
    )
    command = ScheduleChangeCommand(
        project_id=project_id,
        task=EntityResolution(
            kind=EntityKind.TASK,
            reference="plastering",
            status=EntityResolutionStatus.RESOLVED,
            entity_id=task.id,
            display_name=task.title,
            match_method="exact",
            can_mutate=True,
        ),
        planned_start=datetime(2026, 8, 21, 8, tzinfo=UTC),
        planned_end=datetime(2026, 8, 21, 17, tzinfo=UTC),
    )
    proposal = schedules.propose(access, command)
    idempotency_key = "conversation:golden:schedule"
    created_at = datetime.now(UTC)
    memory_service = ConversationMemoryService(
        initial,
        ConversationEntityResolver(initial),
        proposal_signing_key=signing_key,
    )
    pending = memory_service.seal_command(
        PendingScheduleCommand(
            proposal_id=conversation_proposal_id(project_id, actor_id, idempotency_key),
            project_id=project_id,
            actor_id=actor_id,
            policy_decision=MutationPolicyDecision(
                policy=MutationPolicyClass.CONFIRM_FIRST,
                reason_code="consequential_reversible_change",
            ),
            idempotency_key=idempotency_key,
            requested_action="Move plastering to Friday",
            observed_memory_version=0,
            observed_entity_versions={task.id: task.version},
            created_at=created_at,
            expires_at=created_at + timedelta(minutes=15),
            command=command.model_copy(update={"confirmed": True, "proposal": proposal.token}),
        )
    )
    saved = memory_service.remember_command(access, pending)
    assert initial.repository(Task).require(project_id, task.id).planned_start == task.planned_start

    restarted = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    restarted_schedules = ConversationScheduleService(
        restarted, MutationPolicyService(), proposal_signing_key=signing_key
    )
    confirmation = ConversationConfirmationService(
        restarted,
        schedules=restarted_schedules,
        proposal_signing_key=signing_key,
    )
    first = confirmation.confirm(access, pending.proposal_id, saved.version)
    replay = confirmation.confirm(access, pending.proposal_id, saved.version)

    final = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    assert first.duplicate is False
    assert replay.duplicate is True
    assert (
        final.repository(Task).require(project_id, task.id).planned_start == command.planned_start
    )
    assert (
        final.repository(ConversationProposalClaim).require(project_id, pending.proposal_id).outcome
        == "confirmed"
    )
    actions = {event.action for event in final.repository(ActivityEvent).list(project_id)}
    assert {
        "conversation.proposal_created",
        "conversation.proposal_confirmation_started",
        "schedule.updated",
        "conversation.proposal_confirmed",
    } <= actions
