from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    ConversationTaskCommand,
    MutationPolicyClass,
    MutationPolicyDecision,
    PendingTaskCommand,
    TaskOperation,
)
from app.domain.enums import MemberRole, TaskStatus
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService, conversation_proposal_id


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
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    created_at = datetime.now(UTC)
    pending = PendingTaskCommand(
        proposal_id=conversation_proposal_id(
            project_id, access.actor.user_id, "conversation:reopen:1"
        ),
        project_id=project_id,
        actor_id=access.actor.user_id,
        policy_decision=MutationPolicyDecision(
            policy=MutationPolicyClass.AUTO_EXECUTE,
            reason_code="routine_reversible_operation",
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
    saved = service.remember_command(access, pending)

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    restarted = ConversationMemoryService(
        restarted_store, ConversationEntityResolver(restarted_store)
    )
    assert restarted.require_command(access, pending.proposal_id, saved.version) == pending

    cleared = restarted.clear_command(access, pending.proposal_id, saved.version)
    final_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    final = ConversationMemoryService(final_store, ConversationEntityResolver(final_store))
    assert final.load(access).pending_command is None
    assert final.clear_command(access, pending.proposal_id, saved.version) == cleared
