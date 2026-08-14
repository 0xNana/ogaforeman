from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, RoleRequiredError
from app.domain.conversation import (
    ConversationMaterialCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    MaterialOperation,
)
from app.domain.enums import ActorType, MemberRole, MaterialRequestStatus
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import ActivityEvent, Material, MaterialRequest
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_material_operations import (
    ConversationMaterialService,
    MaterialRiskWorkflowRequired,
)
from app.services.materials import MaterialService


NOW = datetime(2026, 8, 14, 9, tzinfo=UTC)
PROJECT_ID = "prj_materials123"


def access(role: MemberRole = MemberRole.MANAGER) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager-subject"),
        project_id=PROJECT_ID,
        role=role,
    )


def context(key: str) -> MutationContext:
    return MutationContext(
        project_id=PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        idempotency_key=key,
        occurred_at=NOW,
    )


def resolution(kind: EntityKind, entity_id: str, name: str) -> EntityResolution:
    return EntityResolution(
        kind=kind,
        reference=name,
        status=EntityResolutionStatus.RESOLVED,
        entity_id=entity_id,
        display_name=name,
        match_method="exact",
        can_mutate=True,
    )


def store() -> InMemoryRepositoryStore:
    result = InMemoryRepositoryStore()
    result.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement",
            normalized_name="cement",
            aliases=["Portland cement"],
            unit="bags",
            available_quantity=Decimal("20"),
            minimum_required_quantity=Decimal("30"),
        )
    )
    result.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id=PROJECT_ID,
            material_id="mat_cement123",
            quantity=Decimal("90"),
            unit="bags",
            reason="Plastering stock",
            source_event_id="evt_request123",
            approval_id="apr_request123",
            status=MaterialRequestStatus.CONFIRMED,
        )
    )
    return result


def service(material_store: InMemoryRepositoryStore) -> ConversationMaterialService:
    return ConversationMaterialService(MaterialService(material_store))


def material() -> EntityResolution:
    return resolution(EntityKind.MATERIAL, "mat_cement123", "Cement")


def test_absolute_on_site_quantity_replays_without_a_second_ledger_entry() -> None:
    material_store = store()
    command = ConversationMaterialCommand(
        operation=MaterialOperation.SET_ON_SITE,
        material=material(),
        quantity=Decimal("35"),
        unit="bags",
        reason="We have 35 bags of cement now.",
    )

    first = service(material_store).execute(access(), command, context("og:cement:on-site:35"))
    replay = service(material_store).execute(access(), command, context("og:cement:on-site:35"))

    assert first.material.available_quantity == 35
    assert first.reply == "Done. Cement is now recorded at 35 bags."
    assert replay.duplicate is True
    assert len(material_store.repository(MaterialLedgerEntry).list(PROJECT_ID)) == 1
    assert len(material_store.repository(ActivityEvent).list(PROJECT_ID)) == 1


def test_required_quantity_and_note_are_atomic_and_authorized() -> None:
    material_store = store()

    required = service(material_store).execute(
        access(),
        ConversationMaterialCommand(
            operation=MaterialOperation.SET_REQUIRED,
            material=material(),
            quantity=Decimal("50"),
            unit="bags",
        ),
        context("og:cement:required:50"),
    )
    noted = service(material_store).execute(
        access(),
        ConversationMaterialCommand(
            operation=MaterialOperation.ADD_NOTE,
            material=material(),
            note="Keep the bags under cover.",
        ),
        context("og:cement:note:cover"),
    )

    assert required.material.minimum_required_quantity == 50
    assert noted.material.notes == ["Keep the bags under cover."]
    assert {
        event.action for event in material_store.repository(ActivityEvent).list(PROJECT_ID)
    } == {
        "material.required_quantity_updated",
        "material.note_added",
    }

    with pytest.raises(RoleRequiredError):
        service(material_store).execute(
            access(MemberRole.VIEWER),
            ConversationMaterialCommand(
                operation=MaterialOperation.ADD_NOTE,
                material=material(),
                note="Unauthorized note.",
            ),
            context("og:cement:viewer-note"),
        )


def test_full_delivery_updates_stock_and_request_once() -> None:
    material_store = store()
    command = ConversationMaterialCommand(
        operation=MaterialOperation.RECORD_DELIVERY,
        material=material(),
        material_request=resolution(EntityKind.MATERIAL_REQUEST, "mrq_cement123", "Cement request"),
        quantity=Decimal("90"),
        unit="bags",
        delivery_complete=True,
        reason="All 90 bags arrived.",
    )

    first = service(material_store).execute(access(), command, context("og:delivery:cement:90"))
    replay = service(material_store).execute(access(), command, context("og:delivery:cement:90"))

    assert first.material.available_quantity == 110
    assert first.reply == "Done. I recorded delivery of 90 bags of Cement."
    assert (
        material_store.repository(MaterialRequest).require(PROJECT_ID, "mrq_cement123").status
        is MaterialRequestStatus.DELIVERED
    )
    assert replay.duplicate is True
    assert len(material_store.repository(MaterialLedgerEntry).list(PROJECT_ID)) == 1


def test_partial_delivery_accumulates_before_request_is_completed() -> None:
    material_store = store()
    base = dict(
        operation=MaterialOperation.RECORD_DELIVERY,
        material=material(),
        material_request=resolution(EntityKind.MATERIAL_REQUEST, "mrq_cement123", "Cement request"),
        unit="bags",
    )

    service(material_store).execute(
        access(),
        ConversationMaterialCommand(
            **base, quantity=Decimal("40"), reason="First 40 bags arrived."
        ),
        context("og:delivery:cement:first-40"),
    )
    service(material_store).execute(
        access(),
        ConversationMaterialCommand(
            **base,
            quantity=Decimal("50"),
            delivery_complete=True,
            reason="The remaining 50 bags arrived.",
        ),
        context("og:delivery:cement:remaining-50"),
    )

    request = material_store.repository(MaterialRequest).require(PROJECT_ID, "mrq_cement123")
    assert request.delivered_quantity == 90
    assert request.status is MaterialRequestStatus.DELIVERED
    assert (
        material_store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity
        == 110
    )


def test_unclear_delivery_and_material_risk_do_not_mutate() -> None:
    material_store = store()

    with pytest.raises(ValueError, match="delivery quantity"):
        service(material_store).execute(
            access(),
            ConversationMaterialCommand(
                operation=MaterialOperation.RECORD_DELIVERY,
                material=material(),
                reason="The cement delivery came.",
            ),
            context("og:delivery:unclear"),
        )
    with pytest.raises(MaterialRiskWorkflowRequired):
        service(material_store).execute(
            access(),
            ConversationMaterialCommand(
                operation=MaterialOperation.SET_ON_SITE,
                material=material(),
                quantity=Decimal("10"),
                unit="bags",
                reason="We are down to 10 bags and plastering starts tomorrow.",
                requires_material_risk_workflow=True,
            ),
            context("og:risk:cement"),
        )

    assert (
        material_store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity
        == 20
    )
    assert material_store.repository(ActivityEvent).list(PROJECT_ID) == ()


def test_delivery_cannot_bypass_request_approval_lifecycle() -> None:
    material_store = store()
    request_repository = material_store.repository(MaterialRequest)
    request = request_repository.require(PROJECT_ID, "mrq_cement123")
    request_repository.save(
        request.model_copy(update={"status": MaterialRequestStatus.AWAITING_APPROVAL}),
        expected_version=0,
    )

    with pytest.raises(ValueError, match="confirmed request"):
        service(material_store).execute(
            access(),
            ConversationMaterialCommand(
                operation=MaterialOperation.RECORD_DELIVERY,
                material=material(),
                material_request=resolution(
                    EntityKind.MATERIAL_REQUEST, "mrq_cement123", "Cement request"
                ),
                quantity=Decimal("90"),
                unit="bags",
                delivery_complete=True,
                reason="Delivery claim before approval.",
            ),
            context("og:delivery:unapproved"),
        )

    assert (
        material_store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity
        == 20
    )
    assert material_store.repository(ActivityEvent).list(PROJECT_ID) == ()


def test_create_material_uses_manage_permission_and_replays() -> None:
    material_store = store()
    command = ConversationMaterialCommand(
        operation=MaterialOperation.CREATE,
        name="Sharp sand",
        unit="tonnes",
        quantity=Decimal("4"),
    )

    first = service(material_store).execute(
        access(MemberRole.ADMIN), command, context("og:create:sharp-sand")
    )
    replay = service(material_store).execute(
        access(MemberRole.ADMIN), command, context("og:create:sharp-sand")
    )

    assert first.material.name == "Sharp sand"
    assert first.material.available_quantity == 4
    assert replay.duplicate is True
