"""Canonical, transaction-safe material quantity mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Self

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType
from app.domain.materials import (
    MaterialLedgerEntry,
    canonicalize_unit,
    ensure_same_unit,
    normalize_material_name,
)
from app.domain.models import ActivityEvent, CanonicalId, Material
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.interfaces import VersionConflictError
from app.repositories.materials import MaterialLedgerRepository, MaterialRepository
from app.services.activity import ActivityService


class MaterialMutationError(ValueError):
    code = "VALIDATION_FAILED"


class NegativeMaterialStockError(MaterialMutationError):
    """A quantity change would make available or unreserved stock negative."""


class MaterialQuantityCommand(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    project_id: CanonicalId
    material_id_or_alias: str = Field(
        min_length=1,
        max_length=300,
        validation_alias=AliasChoices("material_id_or_alias", "material_id", "material_ref"),
    )
    quantity_delta: Decimal = Field(validation_alias=AliasChoices("quantity_delta", "delta"))
    unit: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=5_000)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_delta(self) -> Self:
        if self.quantity_delta == 0:
            raise ValueError("quantity_delta cannot be zero")
        canonicalize_unit(self.unit)
        return self


UpdateMaterialQuantityCommand = MaterialQuantityCommand


class CreateMaterialCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    name: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    available_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_required_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    upcoming_requirement_quantity: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        canonicalize_unit(self.unit)
        normalized_name = normalize_material_name(self.name)
        normalized_aliases = [normalize_material_name(alias) for alias in self.aliases]
        if normalized_name in normalized_aliases or len(normalized_aliases) != len(
            set(normalized_aliases)
        ):
            raise ValueError("material aliases must be unique and distinct from its name")
        return self


@dataclass(frozen=True, slots=True)
class MaterialChange:
    material: Material
    ledger_entry: MaterialLedgerEntry
    activity: ActivityEvent
    duplicate: bool = False

    @property
    def replayed(self) -> bool:
        return self.duplicate


@dataclass(frozen=True, slots=True)
class _MaterialMutationValue:
    material: Material
    ledger_entry: MaterialLedgerEntry | None


@dataclass(frozen=True, slots=True)
class MaterialCreation:
    material: Material
    activity: ActivityEvent
    duplicate: bool = False


class MaterialService:
    def __init__(self, store: RepositoryStore) -> None:
        self._materials = MaterialRepository(store)
        self._activities = ActivityService(store)

    def create_material(
        self,
        access: ProjectAccessContext,
        command: CreateMaterialCommand,
        context: MutationContext,
    ) -> MaterialCreation:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.MANAGE)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("material setup requires the authorized user actor")
        normalized_name = normalize_material_name(command.name)
        normalized_aliases = [normalize_material_name(alias) for alias in command.aliases]
        material_id = _created_material_id(context)
        canonical_unit = canonicalize_unit(command.unit)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="material.created",
                entity_type="material",
                entity_id=material_id,
                summary=f"Created material {command.name}.",
                metadata={"unit": canonical_unit},
            ),
            lambda session: _create_material(
                session,
                command,
                context,
                material_id,
                normalized_name,
                normalized_aliases,
                canonical_unit,
            ),
            replay=lambda session, activity: _replay_created_material(
                session, access, context, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("material creation replay did not resolve persisted state")
        return MaterialCreation(
            material=result.value.material,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    def resolve_material(
        self,
        access: ProjectAccessContext,
        material_id_or_alias: str,
    ) -> Material:
        ensure_permission(access, ProjectPermission.READ)
        material = self._materials.resolve(access, material_id_or_alias)
        _validate_material_identity(material)
        return material

    def update_quantity(
        self,
        access: ProjectAccessContext,
        command: MaterialQuantityCommand,
        context: MutationContext,
    ) -> MaterialChange:
        self._authorize(access, command, context)
        resolved = self.resolve_material(access, command.material_id_or_alias)
        canonical_unit = ensure_same_unit(resolved.unit, command.unit)
        canonical_command = command.model_copy(
            update={"material_id_or_alias": resolved.id, "unit": canonical_unit}
        )
        spec = _activity_spec(canonical_command, resolved.id)

        result = self._activities.mutate(
            context,
            spec,
            lambda session: self._apply_quantity(
                session, access, canonical_command, context, resolved.id
            ),
            replay=lambda session, activity: self._replay(
                session, access, context, activity.entity_id
            ),
        )
        if result.value is None:
            raise RuntimeError("material replay did not resolve persisted state")
        if result.value.ledger_entry is None:
            raise RuntimeError("material quantity replay did not resolve its ledger entry")
        return MaterialChange(
            material=result.value.material,
            ledger_entry=result.value.ledger_entry,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    adjust_quantity = update_quantity

    @staticmethod
    def _authorize(
        access: ProjectAccessContext,
        command: MaterialQuantityCommand,
        context: MutationContext,
    ) -> None:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")

    @staticmethod
    def _apply_quantity(
        session: RepositorySession,
        access: ProjectAccessContext,
        command: MaterialQuantityCommand,
        context: MutationContext,
        material_id: str,
    ) -> _MaterialMutationValue:
        materials = MaterialRepository.for_session(session, access)
        ledgers = MaterialLedgerRepository.for_session(session, access)
        current = materials.require(command.project_id, material_id)
        _validate_material_identity(current)
        if current.version != command.expected_version:
            raise VersionConflictError(
                f"expected_version {command.expected_version} does not match current version {current.version}"
            )
        unit = ensure_same_unit(current.unit, command.unit)
        balance = current.available_quantity + command.quantity_delta
        if balance < 0:
            raise NegativeMaterialStockError("material quantity cannot become negative")
        if balance < current.reserved_quantity:
            raise NegativeMaterialStockError(
                "material quantity cannot fall below the reserved quantity"
            )
        updated = materials.save(
            current.model_copy(
                update={
                    "available_quantity": balance,
                    "unit": unit,
                    "updated_at": command.occurred_at,
                }
            ),
            expected_version=command.expected_version,
        )
        ledger = ledgers.create(
            MaterialLedgerEntry(
                id=_ledger_id(context),
                project_id=command.project_id,
                material_id=material_id,
                quantity_delta=command.quantity_delta,
                unit=unit,
                balance_after=balance,
                reason=command.reason,
                source_event_id=context.source_event_id,
                agent_run_id=context.agent_run_id,
                actor_id=context.actor_id or "system",
                idempotency_key=context.idempotency_key,
                created_at=command.occurred_at,
            )
        )
        return _MaterialMutationValue(material=updated, ledger_entry=ledger)

    @staticmethod
    def _replay(
        session: RepositorySession,
        access: ProjectAccessContext,
        context: MutationContext,
        material_id: str,
    ) -> _MaterialMutationValue:
        material = MaterialRepository.for_session(session, access).require(
            access.project_id, material_id
        )
        ledger = MaterialLedgerRepository.for_session(session, access).require(
            access.project_id, _ledger_id(context)
        )
        return _MaterialMutationValue(material=material, ledger_entry=ledger)


def _validate_material_identity(material: Material) -> None:
    normalized_name = normalize_material_name(material.name)
    if material.normalized_name != normalized_name:
        raise MaterialMutationError(
            "stored normalized_name does not match the canonical material name"
        )
    aliases = [normalize_material_name(alias) for alias in material.aliases]
    if normalized_name in aliases or len(aliases) != len(set(aliases)):
        raise MaterialMutationError("material aliases must be unique and distinct from its name")
    canonical = canonicalize_unit(material.unit)
    if canonical != material.unit:
        raise MaterialMutationError("stored material unit must be canonical")


def _ledger_id(context: MutationContext) -> str:
    raw = f"{context.project_id}\x00{context.actor_id or 'system'}\x00{context.idempotency_key}"
    return f"mle_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _created_material_id(context: MutationContext) -> str:
    raw = f"{context.project_id}\x00{context.actor_id}\x00{context.idempotency_key}"
    return f"mat_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _create_material(
    session: RepositorySession,
    command: CreateMaterialCommand,
    context: MutationContext,
    material_id: str,
    normalized_name: str,
    normalized_aliases: list[str],
    canonical_unit: str,
) -> _MaterialMutationValue:
    materials = session.repository(Material)
    requested_names = {normalized_name, *normalized_aliases}
    for existing in materials.list(command.project_id):
        existing_names = {existing.normalized_name, *existing.aliases}
        if requested_names & {normalize_material_name(value) for value in existing_names}:
            raise MaterialMutationError("material name or alias already exists")
    material = materials.create(
        Material(
            id=material_id,
            project_id=command.project_id,
            name=command.name,
            normalized_name=normalized_name,
            aliases=normalized_aliases,
            unit=canonical_unit,
            available_quantity=command.available_quantity,
            minimum_required_quantity=command.minimum_required_quantity,
            upcoming_requirement_quantity=command.upcoming_requirement_quantity,
            updated_at=context.occurred_at,
        )
    )
    ledger = None
    if command.available_quantity > 0:
        ledger = session.repository(MaterialLedgerEntry).create(
            MaterialLedgerEntry(
                id=_ledger_id(context),
                project_id=command.project_id,
                material_id=material_id,
                quantity_delta=command.available_quantity,
                unit=canonical_unit,
                balance_after=command.available_quantity,
                reason="Initial project material stock.",
                actor_id=context.actor_id or "system",
                idempotency_key=context.idempotency_key,
                created_at=context.occurred_at,
            )
        )
    return _MaterialMutationValue(material=material, ledger_entry=ledger)


def _replay_created_material(
    session: RepositorySession,
    access: ProjectAccessContext,
    context: MutationContext,
    material_id: str,
) -> _MaterialMutationValue:
    material = session.repository(Material).require(access.project_id, material_id)
    ledger = session.repository(MaterialLedgerEntry).get(access.project_id, _ledger_id(context))
    return _MaterialMutationValue(
        material=material,
        ledger_entry=ledger,
    )


def _activity_spec(command: MaterialQuantityCommand, material_id: str) -> ActivitySpec:
    return ActivitySpec(
        action="material.quantity_updated",
        entity_type="material",
        entity_id=material_id,
        summary="Material stock quantity updated",
        metadata={
            "quantity_delta": str(command.quantity_delta),
            "unit": command.unit,
            "reason_digest": sha256(command.reason.encode("utf-8")).hexdigest()[:16],
        },
    )


__all__ = [
    "CreateMaterialCommand",
    "MaterialCreation",
    "MaterialChange",
    "MaterialMutationError",
    "MaterialQuantityCommand",
    "MaterialService",
    "NegativeMaterialStockError",
    "UpdateMaterialQuantityCommand",
]
