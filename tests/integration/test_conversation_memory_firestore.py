from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    ConversationMaterialCommand,
    MaterialOperation,
    MutationPolicyClass,
    MutationPolicyDecision,
    PendingMaterialCommand,
)
from app.domain.enums import MemberRole
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService


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
    pending = PendingMaterialCommand(
        proposal_id="cpr_cement123",
        project_id=project_id,
        actor_id=access.actor.user_id,
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
