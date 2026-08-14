"""Typed material ledger tools."""

from __future__ import annotations

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.services.materials import (
    CreateMaterialCommand,
    MaterialChange,
    MaterialCreation,
    MaterialOperationChange,
    MaterialQuantityCommand,
    MaterialService,
    RecordMaterialDeliveryCommand,
    SetMaterialQuantityCommand,
    UpdateMaterialDetailsCommand,
)


class MaterialTools:
    def __init__(self, service: MaterialService, access: ProjectAccessContext) -> None:
        self._service = service
        self._access = access

    def update_material_quantity(
        self,
        command: MaterialQuantityCommand,
        context: MutationContext,
    ) -> MaterialChange:
        return self._service.update_quantity(self._access, command, context)

    def create_material(
        self, command: CreateMaterialCommand, context: MutationContext
    ) -> MaterialCreation:
        return self._service.create_material(self._access, command, context)

    def set_material_quantity(
        self, command: SetMaterialQuantityCommand, context: MutationContext
    ) -> MaterialOperationChange:
        return self._service.set_quantity(self._access, command, context)

    def update_material_details(
        self, command: UpdateMaterialDetailsCommand, context: MutationContext
    ) -> MaterialOperationChange:
        return self._service.update_details(self._access, command, context)

    def record_material_delivery(
        self, command: RecordMaterialDeliveryCommand, context: MutationContext
    ) -> MaterialOperationChange:
        return self._service.record_delivery(self._access, command, context)


def update_material_quantity(
    command: MaterialQuantityCommand,
    *,
    service: MaterialService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> MaterialChange:
    return service.update_quantity(access, command, context)


def create_material(
    command: CreateMaterialCommand,
    *,
    service: MaterialService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> MaterialCreation:
    return service.create_material(access, command, context)


def set_material_quantity(
    command: SetMaterialQuantityCommand,
    *,
    service: MaterialService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> MaterialOperationChange:
    return service.set_quantity(access, command, context)


def update_material_details(
    command: UpdateMaterialDetailsCommand,
    *,
    service: MaterialService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> MaterialOperationChange:
    return service.update_details(access, command, context)


def record_material_delivery(
    command: RecordMaterialDeliveryCommand,
    *,
    service: MaterialService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> MaterialOperationChange:
    return service.record_delivery(access, command, context)


__all__ = [
    "MaterialTools",
    "create_material",
    "record_material_delivery",
    "set_material_quantity",
    "update_material_details",
    "update_material_quantity",
]
