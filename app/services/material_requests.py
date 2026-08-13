"""Material shortage calculation and request service."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Self

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.domain.activity import ActivitySpec, MutationContext, WorkflowActivityAction
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import (
    ActorType,
    ApprovalActionType,
    MaterialRequestStatus,
)
from app.domain.materials import canonicalize_unit, ensure_same_unit
from app.domain.models import ActivityEvent, Approval, Material, MaterialRequest, Task
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.repositories.material_requests import MaterialRequestRepository
from app.services.activity import ActivityService
from app.services.workflow_audit import workflow_audit_activity
from app.services.materials import MaterialService


class MaterialRequestError(ValueError):
    code = "REQUEST_FAILED"


class MissingUnitError(MaterialRequestError):
    code = "MISSING_UNIT"


class MaterialShortageCommand(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    project_id: str
    material_id_or_alias: str = Field(
        min_length=1,
        max_length=300,
        validation_alias=AliasChoices("material_id_or_alias", "material_id", "material_ref"),
    )
    required_quantity: Decimal
    unit: str = Field(min_length=1, max_length=100)
    needed_by: AwareDatetime | None = None
    reason: str = Field(min_length=1, max_length=5_000)
    supplier: str | None = Field(default=None, max_length=500)
    estimated_unit_cost: Decimal | None = None
    affected_task_ids: list[str] = Field(default_factory=list, max_length=100)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_command(self) -> Self:
        if self.required_quantity <= 0:
            raise ValueError("required_quantity must be positive")
        canonicalize_unit(self.unit)
        return self


@dataclass(frozen=True, slots=True)
class ShortageResult:
    is_shortage: bool
    net_shortage: Decimal
    material_id: str
    request: MaterialRequest | None
    approval: Approval | None
    activity: ActivityEvent | None
    duplicate: bool


class MaterialRequestService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._materials = MaterialService(store)
        self._activities = ActivityService(store)

    def evaluate_shortage(
        self,
        access: ProjectAccessContext,
        command: MaterialShortageCommand,
        context: MutationContext,
    ) -> ShortageResult:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")
        if context.source_event_id is None:
            raise MaterialRequestError("a source event is required for a material request")

        material = self._materials.resolve_material(access, command.material_id_or_alias)
        try:
            canonical_unit = ensure_same_unit(material.unit, command.unit)
        except ValueError as exc:
            raise MissingUnitError(str(exc)) from exc

        available_net = material.available_quantity - material.reserved_quantity
        if available_net < 0:
            available_net = Decimal("0")

        shortage = command.required_quantity - available_net
        if shortage <= 0:
            return ShortageResult(
                is_shortage=False,
                net_shortage=Decimal("0"),
                material_id=material.id,
                request=None,
                approval=None,
                activity=None,
                duplicate=False,
            )

        total_cost = (
            (shortage * command.estimated_unit_cost)
            if command.estimated_unit_cost is not None
            else None
        )

        canonical_command = command.model_copy(
            update={"material_id_or_alias": material.id, "unit": canonical_unit}
        )

        spec = ActivitySpec(
            action="material.requested",
            entity_type="material_request",
            entity_id=_request_id(context),
            summary=f"Requested {shortage} {canonical_unit} of {material.name}",
            metadata={
                "material_id": material.id,
                "quantity": str(shortage),
                "unit": canonical_unit,
                "reason_digest": sha256(command.reason.encode("utf-8")).hexdigest()[:16],
            },
        )
        request_id = _request_id(context)
        semantic_activity = workflow_audit_activity(
            context,
            action=WorkflowActivityAction.MATERIAL_RISK_DETECTED,
            entity_type="material_request",
            entity_id=request_id,
            summary="Detected material stock below the supported project requirement.",
            metadata={
                "status": MaterialRequestStatus.AWAITING_APPROVAL.value,
                "reason_code": "available_stock_below_requirement",
                "material_id": material.id,
                "available_quantity": str(available_net),
                "required_quantity": str(command.required_quantity),
                "shortage_quantity": str(shortage),
                "unit": canonical_unit,
                "affected_task_ids": command.affected_task_ids,
                "material_request_id": request_id,
                "approval_id": _approval_id(request_id),
            },
        )

        result = self._activities.mutate(
            context,
            spec,
            lambda session: self._create_request(
                session, access, canonical_command, context, material.id, shortage, total_cost
            ),
            replay=lambda session, activity: self._replay(session, access, context),
            additional_activities=(semantic_activity,) if semantic_activity else (),
        )

        if result.value is None:
            raise RuntimeError("material request replay did not resolve persisted state")
        approval_id = result.value.approval_id
        if approval_id is None:
            raise RuntimeError("material request did not persist its required approval")
        approval = self._store.repository(Approval).require(command.project_id, approval_id)

        return ShortageResult(
            is_shortage=True,
            net_shortage=shortage,
            material_id=material.id,
            request=result.value,
            approval=approval,
            activity=result.activity,
            duplicate=result.duplicate,
        )

    def _create_request(
        self,
        session: RepositorySession,
        access: ProjectAccessContext,
        command: MaterialShortageCommand,
        context: MutationContext,
        material_id: str,
        shortage: Decimal,
        total_cost: Decimal | None,
    ) -> MaterialRequest:
        requests = MaterialRequestRepository.for_session(session, access)
        task_titles = {
            task.id: task.title for task in session.repository(Task).list(command.project_id)
        }
        affected_work = ", ".join(
            task_titles[task_id] for task_id in command.affected_task_ids if task_id in task_titles
        )
        source_event_id = context.source_event_id
        if source_event_id is None:
            raise MaterialRequestError("a source event is required for a material request")
        request_id = _request_id(context)
        approval_id = _approval_id(request_id)
        approval = Approval(
            id=approval_id,
            project_id=command.project_id,
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={
                "material_id": material_id,
                "material_name": session.repository(Material)
                .require(command.project_id, material_id)
                .name,
                "quantity": str(shortage),
                "unit": command.unit,
                "needed_by": command.needed_by.isoformat() if command.needed_by else None,
                "needed_for": affected_work or None,
                "affected_task_ids": command.affected_task_ids,
                "supplier": command.supplier,
                "estimated_total_cost": str(total_cost) if total_cost is not None else None,
            },
            reason=command.reason,
            evidence_refs=[source_event_id],
            requested_by=context.actor_id or "system",
            requested_at=command.occurred_at,
        )
        session.repository(Approval).create(approval)
        approval_context = context.model_copy(
            update={
                "idempotency_key": (
                    "approval:" + sha256(context.idempotency_key.encode("utf-8")).hexdigest()[:32]
                )
            }
        )
        session.repository(ActivityEvent).create(
            ActivityRepository.build_event(
                approval_context,
                ActivitySpec(
                    action="approval.requested",
                    entity_type="approval",
                    entity_id=approval_id,
                    summary="Purchase approval requested.",
                    metadata={
                        "material_request_id": request_id,
                        "material_id": material_id,
                    },
                ),
            )
        )
        req = MaterialRequest(
            id=request_id,
            project_id=command.project_id,
            material_id=material_id,
            quantity=shortage,
            unit=command.unit,
            needed_by=command.needed_by,
            reason=command.reason,
            source_event_id=source_event_id,
            supplier=command.supplier,
            estimated_total_cost=total_cost,
            status=MaterialRequestStatus.AWAITING_APPROVAL,
            approval_id=approval_id,
            created_at=command.occurred_at,
            updated_at=command.occurred_at,
        )
        return requests.create(req)

    def _replay(
        self,
        session: RepositorySession,
        access: ProjectAccessContext,
        context: MutationContext,
    ) -> MaterialRequest:
        return MaterialRequestRepository.for_session(session, access).require(
            access.project_id, _request_id(context)
        )


def _request_id(context: MutationContext) -> str:
    raw = f"{context.project_id}\x00{context.actor_id or 'system'}\x00{context.idempotency_key}"
    return f"mrq_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _approval_id(request_id: str) -> str:
    return f"app_{sha256(request_id.encode('utf-8')).hexdigest()[:32]}"


__all__ = [
    "MaterialRequestService",
    "MaterialShortageCommand",
    "ShortageResult",
    "MissingUnitError",
    "MaterialRequestError",
]
