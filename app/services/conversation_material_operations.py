"""Conversational material commands composed from typed material services."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.conversation import (
    ConversationMaterialCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    MaterialOperation,
)
from app.domain.materials import ensure_same_unit
from app.domain.models import Material
from app.services.materials import (
    CreateMaterialCommand,
    MaterialService,
    RecordMaterialDeliveryCommand,
    SetMaterialQuantityCommand,
    UpdateMaterialDetailsCommand,
)


class MaterialRiskWorkflowRequired(ValueError):
    """The statement belongs to existing material-risk reasoning."""


@dataclass(frozen=True, slots=True)
class ConversationMaterialResult:
    material: Material
    activity_id: str
    reply: str
    duplicate: bool


class ConversationMaterialService:
    def __init__(self, materials: MaterialService) -> None:
        self._materials = materials

    def execute(
        self,
        access: ProjectAccessContext,
        command: ConversationMaterialCommand,
        context: MutationContext,
    ) -> ConversationMaterialResult:
        if command.requires_material_risk_workflow:
            raise MaterialRiskWorkflowRequired(
                "material shortage or schedule risk requires the existing risk workflow"
            )
        if command.operation is MaterialOperation.CREATE:
            if command.name is None or command.unit is None:
                raise ValueError("material name and unit are required for creation")
            created = self._materials.create_material(
                access,
                CreateMaterialCommand(
                    project_id=access.project_id,
                    name=command.name,
                    unit=command.unit,
                    aliases=list(command.aliases),
                    available_quantity=command.quantity or Decimal("0"),
                ),
                context,
            )
            return ConversationMaterialResult(
                created.material,
                created.activity.id,
                f"Done. I created {created.material.name}.",
                created.duplicate,
            )

        material_id = _resolved_id(command.material, EntityKind.MATERIAL, "material")
        current = self._materials.resolve_material(access, material_id)
        if command.operation is MaterialOperation.SET_ON_SITE:
            quantity, unit = _quantity_and_unit(command)
            changed = self._materials.set_quantity(
                access,
                SetMaterialQuantityCommand(
                    project_id=access.project_id,
                    material_id_or_alias=material_id,
                    quantity=quantity,
                    unit=unit,
                    expected_version=current.version,
                    reason=command.reason or "Conversational stock count.",
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            return _result(
                changed.material,
                changed.activity.id,
                f"Done. {changed.material.name} is now recorded at {quantity} {changed.material.unit}.",
                changed.duplicate,
            )

        if command.operation is MaterialOperation.SET_REQUIRED:
            quantity, unit = _quantity_and_unit(command)
            ensure_same_unit(current.unit, unit)
            changed = self._materials.update_details(
                access,
                UpdateMaterialDetailsCommand(
                    project_id=access.project_id,
                    material_id=material_id,
                    expected_version=current.version,
                    required_quantity=quantity,
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            return _result(
                changed.material,
                changed.activity.id,
                f"Done. {changed.material.name} now requires {quantity} {changed.material.unit}.",
                changed.duplicate,
            )

        if command.operation is MaterialOperation.ADD_NOTE:
            if command.note is None:
                raise ValueError("material note is required")
            changed = self._materials.update_details(
                access,
                UpdateMaterialDetailsCommand(
                    project_id=access.project_id,
                    material_id=material_id,
                    expected_version=current.version,
                    note=command.note,
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            return _result(
                changed.material,
                changed.activity.id,
                f"Done. I added the note to {changed.material.name}.",
                changed.duplicate,
            )

        if command.quantity is None or command.unit is None:
            raise ValueError("delivery quantity and unit must be clarified")
        request_id = _resolved_id(
            command.material_request, EntityKind.MATERIAL_REQUEST, "material request"
        )
        delivered = self._materials.record_delivery(
            access,
            RecordMaterialDeliveryCommand(
                project_id=access.project_id,
                material_id=material_id,
                request_id=request_id,
                quantity=command.quantity,
                unit=command.unit,
                expected_material_version=current.version,
                complete_delivery=command.delivery_complete,
                reason=command.reason or "Conversational delivery record.",
                occurred_at=context.occurred_at,
            ),
            context,
        )
        return _result(
            delivered.material,
            delivered.activity.id,
            f"Done. I recorded delivery of {command.quantity} {delivered.material.unit} of {delivered.material.name}.",
            delivered.duplicate,
        )


def _quantity_and_unit(command: ConversationMaterialCommand) -> tuple[Decimal, str]:
    if command.quantity is None or command.unit is None:
        raise ValueError("material quantity and unit are required")
    return command.quantity, command.unit


def _resolved_id(resolution: EntityResolution | None, kind: EntityKind, label: str) -> str:
    if (
        resolution is None
        or resolution.kind is not kind
        or resolution.status is not EntityResolutionStatus.RESOLVED
        or not resolution.can_mutate
        or resolution.entity_id is None
    ):
        raise ValueError(f"a resolved {label} is required")
    return resolution.entity_id


def _result(
    material: Material, activity_id: str, reply: str, duplicate: bool
) -> ConversationMaterialResult:
    return ConversationMaterialResult(material, activity_id, reply, duplicate)


__all__ = [
    "ConversationMaterialResult",
    "ConversationMaterialService",
    "MaterialRiskWorkflowRequired",
]
