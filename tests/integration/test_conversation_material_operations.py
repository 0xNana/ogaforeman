from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    ConversationMaterialCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    MaterialOperation,
)
from app.domain.enums import ActorType, MaterialRequestStatus, MemberRole
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import ActivityEvent, Material, MaterialRequest
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.conversation_material_operations import ConversationMaterialService
from app.services.materials import MaterialService


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for conversation material integration",
    ),
]


def resolved(kind: EntityKind, entity_id: str, name: str) -> EntityResolution:
    return EntityResolution(
        kind=kind,
        reference=name,
        status=EntityResolutionStatus.RESOLVED,
        entity_id=entity_id,
        display_name=name,
        match_method="exact",
        can_mutate=True,
    )


def test_material_delivery_survives_firestore_restart_and_replays_once() -> None:
    cloud_project = f"oga-conversation-material-{uuid4().hex}"
    project_id = "prj_materials123"
    now = datetime(2026, 8, 14, 10, tzinfo=UTC)
    store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=project_id,
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("20"),
        )
    )
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id=project_id,
            material_id="mat_cement123",
            quantity=Decimal("90"),
            unit="bags",
            reason="Plastering stock",
            source_event_id="evt_request123",
            approval_id="apr_request123",
            status=MaterialRequestStatus.CONFIRMED,
        )
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )
    context = MutationContext(
        project_id=project_id,
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        idempotency_key="og:delivery:cement:90",
        occurred_at=now,
    )
    command = ConversationMaterialCommand(
        operation=MaterialOperation.RECORD_DELIVERY,
        material=resolved(EntityKind.MATERIAL, "mat_cement123", "Cement"),
        material_request=resolved(EntityKind.MATERIAL_REQUEST, "mrq_cement123", "Cement request"),
        quantity=Decimal("90"),
        unit="bags",
        delivery_complete=True,
        reason="All 90 bags arrived.",
    )

    ConversationMaterialService(MaterialService(store)).execute(access, command, context)
    restarted = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    replay = ConversationMaterialService(MaterialService(restarted)).execute(
        access, command, context
    )

    assert replay.duplicate is True
    assert restarted.repository(Material).require(
        project_id, "mat_cement123"
    ).available_quantity == Decimal("110")
    assert (
        restarted.repository(MaterialRequest).require(project_id, "mrq_cement123").status
        is MaterialRequestStatus.DELIVERED
    )
    assert len(restarted.repository(MaterialLedgerEntry).list(project_id)) == 1
    assert len(restarted.repository(ActivityEvent).list(project_id)) == 1
