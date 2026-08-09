"""Typed material ledger tools."""

from __future__ import annotations

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.services.materials import MaterialChange, MaterialQuantityCommand, MaterialService


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


def update_material_quantity(
    command: MaterialQuantityCommand,
    *,
    service: MaterialService,
    access: ProjectAccessContext,
    context: MutationContext,
) -> MaterialChange:
    return service.update_quantity(access, command, context)


__all__ = [
    "MaterialTools",
    "update_material_quantity",
]
