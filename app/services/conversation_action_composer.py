"""Compose validated model interpretations into typed, non-executing domain commands."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.domain.authorization import ProjectAccessContext, ensure_project_scope
from app.domain.conversation import (
    ConversationIssueCommand,
    ConversationMaterialCommand,
    ConversationPurchaseCommand,
    ConversationTaskCommand,
    ConversationalProjectContext,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    IssueOperation,
    MaterialOperation,
    MutationKind,
    MutationPolicyDecision,
    MutationPolicyRequest,
    ScheduleChangeCommand,
    TaskContextItem,
    TaskOperation,
)
from app.domain.enums import IssueStatus, IssueType, Severity, TaskPriority, TaskStatus
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.entity_resolution import normalize_text


class _Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TaskActionInterpretation(_Interpretation):
    kind: Literal["task"] = "task"
    operation: TaskOperation
    task_reference: str | None = Field(default=None, min_length=1, max_length=300)
    assignee_reference: str | None = Field(default=None, min_length=1, max_length=300)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    trade: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=500)
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    due_date: AwareDatetime | None = None
    due_day: int | None = Field(default=None, ge=1, le=31)
    due_month: int | None = Field(default=None, ge=1, le=12)
    due_year: int | None = Field(default=None, ge=2000, le=2200)
    create_if_missing: bool = False
    target_status: TaskStatus | None = None
    priority: TaskPriority | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    evidence: str | None = Field(default=None, min_length=1, max_length=5_000)
    negated: bool = False
    ambiguous: bool = False


class TaskActionBatchInterpretation(_Interpretation):
    """Independent task mutations extracted from one conversational turn."""

    kind: Literal["task_batch"] = "task_batch"
    actions: tuple[TaskActionInterpretation, ...] = Field(min_length=2, max_length=20)


class MaterialActionInterpretation(_Interpretation):
    kind: Literal["material"] = "material"
    operation: MaterialOperation
    material_reference: str | None = Field(default=None, min_length=1, max_length=300)
    material_request_reference: str | None = Field(default=None, min_length=1, max_length=300)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    aliases: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    quantity: Decimal | None = Field(default=None, ge=0)
    quantity_delta: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    reason: str | None = Field(default=None, min_length=1, max_length=5_000)
    delivery_complete: bool = False
    requires_material_risk_workflow: bool = False
    inventory_creation: bool = False


class IssueActionInterpretation(_Interpretation):
    kind: Literal["issue"] = "issue"
    operation: IssueOperation
    issue_reference: str | None = Field(default=None, min_length=1, max_length=300)
    owner_reference: str | None = Field(default=None, min_length=1, max_length=300)
    issue_type: IssueType | None = None
    severity: Severity | None = None
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    target_status: IssueStatus | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    evidence: str | None = Field(default=None, min_length=1, max_length=5_000)
    negated: bool = False
    ambiguous: bool = False


class ScheduleActionInterpretation(_Interpretation):
    kind: Literal["schedule"] = "schedule"
    task_reference: str = Field(min_length=1, max_length=300)
    planned_start: AwareDatetime
    planned_end: AwareDatetime

    @model_validator(mode="after")
    def validate_dates(self) -> ScheduleActionInterpretation:
        if self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        return self


class PurchaseActionInterpretation(_Interpretation):
    kind: Literal["purchase"] = "purchase"
    material_reference: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=5_000)
    needed_by: AwareDatetime | None = None
    supplier: str | None = Field(default=None, max_length=500)
    estimated_total_cost: Decimal | None = Field(default=None, ge=0)


ActionInterpretation: TypeAlias = Annotated[
    TaskActionInterpretation
    | TaskActionBatchInterpretation
    | MaterialActionInterpretation
    | IssueActionInterpretation
    | ScheduleActionInterpretation
    | PurchaseActionInterpretation,
    Field(discriminator="kind"),
]


class ActionInterpretationEnvelope(BaseModel):
    """Structured model boundary for one action or an independent task batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    action: ActionInterpretation

    @model_validator(mode="before")
    @classmethod
    def normalize_task_batch_shape(cls, value: object) -> object:
        """Accept the public batch shape while preserving the legacy envelope."""
        if isinstance(value, dict) and "action" not in value and value.get("kind") == "task_batch":
            return {"action": value}
        return value


ActionCommand: TypeAlias = (
    ConversationTaskCommand
    | ConversationMaterialCommand
    | ConversationIssueCommand
    | ScheduleChangeCommand
    | ConversationPurchaseCommand
)


class ComposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["task", "material", "issue", "schedule", "purchase"]
    command: ActionCommand
    mutation_kind: MutationKind
    policy_decision: MutationPolicyDecision
    observed_context_at: AwareDatetime

    @model_validator(mode="after")
    def validate_command_kind(self) -> ComposedAction:
        expected = {
            "task": ConversationTaskCommand,
            "material": ConversationMaterialCommand,
            "issue": ConversationIssueCommand,
            "schedule": ScheduleChangeCommand,
            "purchase": ConversationPurchaseCommand,
        }[self.kind]
        if not isinstance(self.command, expected):
            raise ValueError("composed action kind does not match its typed command")
        return self


class ActionComposer:
    """Pure composition boundary. It never persists, audits, approves, or executes a command."""

    def __init__(self, policies: MutationPolicyService) -> None:
        self._policies = policies

    def compose(
        self,
        access: ProjectAccessContext,
        interpretation: ActionInterpretation,
        context: ConversationalProjectContext,
        resolutions: tuple[EntityResolution, ...],
        policy_request: MutationPolicyRequest,
    ) -> ComposedAction:
        ensure_project_scope(access, context.project_id)
        ensure_project_scope(access, policy_request.project_id)
        command: ActionCommand
        mutation: MutationKind
        if isinstance(interpretation, TaskActionInterpretation):
            command, mutation = self._task(interpretation, context, resolutions)
        elif isinstance(interpretation, MaterialActionInterpretation):
            command, mutation = self._material(interpretation, context, resolutions)
        elif isinstance(interpretation, IssueActionInterpretation):
            command, mutation = self._issue(interpretation, context, resolutions)
        elif isinstance(interpretation, ScheduleActionInterpretation):
            command, mutation = self._schedule(access, interpretation, context, resolutions)
        else:
            command, mutation = self._purchase(interpretation, context, resolutions)
        allowed_policy_kinds = (
            {MutationKind.SCHEDULE_DATES, MutationKind.MAJOR_SCHEDULE_CHANGE}
            if interpretation.kind == "schedule"
            else {mutation}
        )
        if (
            isinstance(interpretation, MaterialActionInterpretation)
            and interpretation.inventory_creation
        ):
            allowed_policy_kinds.add(MutationKind.MATERIAL_QUANTITY)
        if policy_request.kind not in allowed_policy_kinds:
            raise ValueError("mutation policy does not match the composed command")
        mutation = policy_request.kind
        return ComposedAction(
            kind=interpretation.kind,
            command=command,
            mutation_kind=mutation,
            policy_decision=self._policies.classify(access, policy_request),
            observed_context_at=context.retrieved_at,
        )

    def _task(
        self,
        value: TaskActionInterpretation,
        context: ConversationalProjectContext,
        resolutions: tuple[EntityResolution, ...],
    ) -> tuple[ConversationTaskCommand, MutationKind]:
        task = (
            None
            if value.operation is TaskOperation.CREATE
            else self._optional_resolution(value.task_reference, EntityKind.TASK, resolutions)
        )
        assignee = self._optional_resolution(
            value.assignee_reference, EntityKind.PROJECT_MEMBER, resolutions
        )
        if assignee is not None:
            _ensure_context_member(assignee, context)
        version = (
            None if task is None else _context_version(task, (*context.tasks, *context.schedule))
        )
        reopening = False
        if task is not None and value.operation is TaskOperation.CHANGE_STATUS:
            task_item = _context_task(task, context)
            reopening = (
                task_item.status == TaskStatus.COMPLETED.value
                and value.target_status
                not in {
                    None,
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                }
            )
        command = ConversationTaskCommand(
            operation=value.operation,
            task=task,
            assignee=assignee,
            title=value.title or (value.task_reference if value.operation is TaskOperation.CREATE else None),
            description=value.description,
            trade=value.trade,
            location=value.location,
            planned_start=value.planned_start,
            planned_end=value.planned_end or value.due_date,
            target_status=value.target_status,
            priority=value.priority,
            note=value.note,
            evidence=value.evidence,
            negated=value.negated,
            ambiguous=value.ambiguous,
            reopening=reopening,
            expected_version=version,
        )
        if (
            value.operation is TaskOperation.CHANGE_DUE_DATE
            and task is not None
            and value.planned_end is not None
        ):
            task_item = _context_task(task, context)
            if task_item.planned_start and value.planned_end < task_item.planned_start:
                raise ValueError("planned_end cannot be before planned_start")
        _validate_task(command)
        return command, _task_mutation(command)

    def _material(
        self,
        value: MaterialActionInterpretation,
        context: ConversationalProjectContext,
        resolutions: tuple[EntityResolution, ...],
    ) -> tuple[ConversationMaterialCommand, MutationKind]:
        material = self._optional_resolution(
            value.material_reference, EntityKind.MATERIAL, resolutions
        )
        request = self._optional_resolution(
            value.material_request_reference, EntityKind.MATERIAL_REQUEST, resolutions
        )
        version = None if material is None else _context_version(material, context.materials)
        request_version = None
        if request is not None:
            request_version = _context_version(request, context.material_requests)
            request_item = next(
                item for item in context.material_requests if item.id == request.entity_id
            )
            if material is None or request_item.material_id != material.entity_id:
                raise ValueError("material request does not belong to the resolved material")
            if normalize_text(request_item.unit) != normalize_text(value.unit or ""):
                raise ValueError("delivery unit does not match authorized request context")
            if request_item.status not in {"confirmed", "delayed"}:
                raise ValueError("material request is not ready to receive a delivery")
            assert value.quantity is not None
            remaining = request_item.quantity - request_item.delivered_quantity
            if value.quantity > remaining:
                raise ValueError("delivery quantity exceeds the material request remainder")
            if value.delivery_complete and value.quantity != remaining:
                raise ValueError("complete delivery must fulfill the material request remainder")
        command = ConversationMaterialCommand(
            operation=value.operation,
            material=material,
            material_request=request,
            name=value.name,
            aliases=value.aliases,
            quantity=value.quantity,
            quantity_delta=value.quantity_delta,
            unit=value.unit,
            note=value.note,
            reason=value.reason,
            delivery_complete=value.delivery_complete,
            requires_material_risk_workflow=value.requires_material_risk_workflow,
            inventory_creation=value.inventory_creation,
            expected_version=version,
            expected_material_request_version=request_version,
        )
        _validate_material(command)
        if material is not None and value.unit is not None:
            _ensure_context_unit(material, value.unit, context)
        return command, _material_mutation(command)

    def _issue(
        self,
        value: IssueActionInterpretation,
        context: ConversationalProjectContext,
        resolutions: tuple[EntityResolution, ...],
    ) -> tuple[ConversationIssueCommand, MutationKind]:
        issue = self._optional_resolution(value.issue_reference, EntityKind.ISSUE, resolutions)
        owner = self._optional_resolution(
            value.owner_reference, EntityKind.PROJECT_MEMBER, resolutions
        )
        if owner is not None:
            _ensure_context_member(owner, context)
        version = None if issue is None else _context_version(issue, context.issues)
        command = ConversationIssueCommand(
            operation=value.operation,
            issue=issue,
            owner=owner,
            issue_type=value.issue_type,
            severity=value.severity,
            description=value.description,
            target_status=value.target_status,
            note=value.note,
            evidence=value.evidence,
            negated=value.negated,
            ambiguous=value.ambiguous,
            expected_version=version,
        )
        _validate_issue(command)
        return command, _issue_mutation(command)

    def _schedule(
        self,
        access: ProjectAccessContext,
        value: ScheduleActionInterpretation,
        context: ConversationalProjectContext,
        resolutions: tuple[EntityResolution, ...],
    ) -> tuple[ScheduleChangeCommand, MutationKind]:
        task = self._resolution(value.task_reference, EntityKind.TASK, resolutions)
        version = _context_version(task, (*context.tasks, *context.schedule))
        return ScheduleChangeCommand(
            project_id=access.project_id,
            task=task,
            planned_start=value.planned_start,
            planned_end=value.planned_end,
            expected_version=version,
            confirmed=False,
        ), MutationKind.SCHEDULE_DATES

    def _purchase(
        self,
        value: PurchaseActionInterpretation,
        context: ConversationalProjectContext,
        resolutions: tuple[EntityResolution, ...],
    ) -> tuple[ConversationPurchaseCommand, MutationKind]:
        material = self._resolution(value.material_reference, EntityKind.MATERIAL, resolutions)
        version = _context_version(material, context.materials)
        _ensure_context_unit(material, value.unit, context)
        return ConversationPurchaseCommand(
            material=material,
            quantity=value.quantity,
            unit=value.unit,
            reason=value.reason,
            needed_by=value.needed_by,
            supplier=value.supplier,
            estimated_total_cost=value.estimated_total_cost,
            expected_material_version=version,
        ), MutationKind.MATERIAL_PURCHASE

    def _optional_resolution(
        self, reference: str | None, kind: EntityKind, resolutions: tuple[EntityResolution, ...]
    ) -> EntityResolution | None:
        return None if reference is None else self._resolution(reference, kind, resolutions)

    def _resolution(
        self, reference: str, kind: EntityKind, resolutions: tuple[EntityResolution, ...]
    ) -> EntityResolution:
        matches = [
            item
            for item in resolutions
            if item.kind is kind and normalize_text(item.reference) == normalize_text(reference)
        ]
        if len(matches) != 1:
            raise ValueError(f"exactly one resolved {kind.value.replace('_', ' ')} is required")
        result = matches[0]
        if (
            result.status is not EntityResolutionStatus.RESOLVED
            or not result.can_mutate
            or result.entity_id is None
        ):
            raise ValueError(f"a mutation-safe resolved {kind.value.replace('_', ' ')} is required")
        return result


def _context_version(resolution: EntityResolution, items: tuple[object, ...]) -> int:
    matches = [item for item in items if getattr(item, "id", None) == resolution.entity_id]
    if not matches:
        raise ValueError("resolved entity is absent from authorized project context")
    versions = {int(getattr(item, "version")) for item in matches}
    if len(versions) != 1:
        raise ValueError("authorized project context contains conflicting entity versions")
    return versions.pop()


def _context_task(
    resolution: EntityResolution,
    context: ConversationalProjectContext,
) -> TaskContextItem:
    matches = [
        item for item in (*context.tasks, *context.schedule) if item.id == resolution.entity_id
    ]
    if not matches:
        raise ValueError("resolved entity is absent from authorized project context")
    statuses = {item.status for item in matches}
    if len(statuses) != 1:
        raise ValueError("authorized project context contains conflicting task states")
    return matches[0]


def _ensure_context_member(
    resolution: EntityResolution,
    context: ConversationalProjectContext,
) -> None:
    if not any(item.user_id == resolution.entity_id for item in context.members):
        raise ValueError("resolved project member is absent from authorized project context")


def _ensure_context_unit(
    material: EntityResolution,
    unit: str,
    context: ConversationalProjectContext,
) -> None:
    item = next(item for item in context.materials if item.id == material.entity_id)
    if normalize_text(item.unit) != normalize_text(unit):
        raise ValueError("material unit does not match authorized material context")


def _task_mutation(command: ConversationTaskCommand) -> MutationKind:
    if command.operation is TaskOperation.CREATE:
        return MutationKind.TASK_CREATE
    if command.operation is TaskOperation.COMPLETE:
        return MutationKind.TASK_COMPLETE
    if command.operation in {TaskOperation.ASSIGN, TaskOperation.REASSIGN}:
        return MutationKind.TASK_ASSIGN
    if command.target_status is TaskStatus.CANCELLED:
        return MutationKind.TASK_CANCEL
    if command.reopening:
        return MutationKind.TASK_REOPEN
    return (
        MutationKind.ADD_NOTE
        if command.operation is TaskOperation.ADD_NOTE
        else MutationKind.TASK_UPDATE
    )


def _material_mutation(command: ConversationMaterialCommand) -> MutationKind:
    if command.requires_material_risk_workflow:
        raise ValueError("material risk or purchase intent requires a typed purchase command")
    if command.operation is MaterialOperation.CREATE:
        return MutationKind.MATERIAL_CREATE
    if command.operation is MaterialOperation.RECORD_DELIVERY:
        return MutationKind.MATERIAL_DELIVERY
    if command.operation in {
        MaterialOperation.SET_ON_SITE,
        MaterialOperation.ADJUST_ON_SITE,
        MaterialOperation.SET_REQUIRED,
    }:
        return MutationKind.MATERIAL_QUANTITY
    return MutationKind.ADD_NOTE


def _issue_mutation(command: ConversationIssueCommand) -> MutationKind:
    if command.operation is IssueOperation.CREATE:
        return MutationKind.ISSUE_CREATE
    if command.operation is IssueOperation.RESOLVE:
        return MutationKind.ISSUE_RESOLVE
    return (
        MutationKind.ADD_NOTE
        if command.operation is IssueOperation.ADD_NOTE
        else MutationKind.ISSUE_UPDATE
    )


def _validate_task(command: ConversationTaskCommand) -> None:
    if command.ambiguous:
        raise ValueError("ambiguous language cannot produce a task command")
    allowed = {
        TaskOperation.CREATE: {
            "operation",
            "assignee",
            "title",
            "description",
            "trade",
            "location",
            "planned_start",
            "planned_end",
            "due_date",
            "due_day",
            "due_month",
            "due_year",
            "create_if_missing",
            "priority",
        },
        TaskOperation.CHANGE_DUE_DATE: {
            "operation",
            "task",
            "planned_end",
            "due_date",
            "due_day",
            "due_month",
            "due_year",
            "expected_version",
        },
        TaskOperation.COMPLETE: {
            "operation",
            "task",
            "evidence",
            "negated",
            "ambiguous",
            "expected_version",
        },
        TaskOperation.CHANGE_STATUS: {
            "operation",
            "task",
            "target_status",
            "reopening",
            "expected_version",
        },
        TaskOperation.ASSIGN: {"operation", "task", "assignee", "expected_version"},
        TaskOperation.REASSIGN: {"operation", "task", "assignee", "expected_version"},
        TaskOperation.CHANGE_PRIORITY: {"operation", "task", "priority", "expected_version"},
        TaskOperation.ADD_NOTE: {"operation", "task", "note", "expected_version"},
    }[command.operation]
    _reject_operation_fields(command, allowed)
    if command.operation is TaskOperation.CREATE:
        if command.title is None:
            raise ValueError("task creation requires a title")
        if (
            command.planned_start is not None
            and command.planned_end is not None
            and command.planned_end < command.planned_start
        ):
            raise ValueError("planned_end cannot be before planned_start")
        return
    if command.task is None or command.expected_version is None:
        raise ValueError("task mutation requires an authorized versioned task")
    if command.operation is TaskOperation.COMPLETE and (
        not command.evidence or command.negated or command.ambiguous
    ):
        raise ValueError("task completion requires clear positive evidence")
    if command.operation is TaskOperation.CHANGE_STATUS and command.target_status is None:
        raise ValueError("task status change requires target_status")
    if (
        command.operation is TaskOperation.CHANGE_STATUS
        and command.target_status is TaskStatus.COMPLETED
    ):
        raise ValueError("task completion requires the typed complete operation")
    if command.reopening and command.operation is not TaskOperation.CHANGE_STATUS:
        raise ValueError("reopening is valid only for a task status change")
    if command.reopening and command.target_status not in {
        TaskStatus.PLANNED,
        TaskStatus.IN_PROGRESS,
    }:
        raise ValueError("reopening requires a planned or in-progress target status")
    if (
        command.operation in {TaskOperation.ASSIGN, TaskOperation.REASSIGN}
        and command.assignee is None
    ):
        raise ValueError("task assignment requires a resolved assignee")
    if command.operation is TaskOperation.CHANGE_PRIORITY and command.priority is None:
        raise ValueError("priority change requires priority")
    if command.operation is TaskOperation.CHANGE_DUE_DATE and command.planned_end is None:
        raise ValueError("task due date change requires planned_end")
    if command.operation is TaskOperation.ADD_NOTE and command.note is None:
        raise ValueError("task note requires note text")


def _validate_material(command: ConversationMaterialCommand) -> None:
    allowed = {
        MaterialOperation.CREATE: {
            "operation",
            "name",
            "aliases",
            "quantity",
            "unit",
            "inventory_creation",
        },
        MaterialOperation.SET_ON_SITE: {
            "operation",
            "material",
            "quantity",
            "unit",
            "reason",
            "expected_version",
        },
        MaterialOperation.ADJUST_ON_SITE: {
            "operation",
            "material",
            "quantity_delta",
            "unit",
            "reason",
            "expected_version",
        },
        MaterialOperation.SET_REQUIRED: {
            "operation",
            "material",
            "quantity",
            "unit",
            "expected_version",
        },
        MaterialOperation.RECORD_DELIVERY: {
            "operation",
            "material",
            "material_request",
            "quantity",
            "unit",
            "reason",
            "delivery_complete",
            "expected_version",
            "expected_material_request_version",
        },
        MaterialOperation.ADD_NOTE: {"operation", "material", "note", "expected_version"},
    }[command.operation]
    _reject_operation_fields(command, allowed)
    if command.operation is MaterialOperation.CREATE:
        if command.name is None or command.unit is None:
            raise ValueError("material creation requires name and unit")
        return
    if command.material is None or command.expected_version is None:
        raise ValueError("material mutation requires an authorized versioned material")
    if command.operation in {MaterialOperation.SET_ON_SITE, MaterialOperation.SET_REQUIRED} and (
        command.quantity is None or command.unit is None
    ):
        raise ValueError("material quantity change requires quantity and unit")
    if command.operation is MaterialOperation.ADJUST_ON_SITE and (
        command.quantity_delta is None or command.quantity_delta == 0 or command.unit is None
    ):
        raise ValueError("material stock adjustment requires a non-zero delta and unit")
    if command.operation is MaterialOperation.RECORD_DELIVERY and (
        command.material_request is None or command.quantity is None or command.unit is None
    ):
        raise ValueError("material delivery requires request, quantity, and unit")
    if command.operation is MaterialOperation.RECORD_DELIVERY:
        assert command.quantity is not None
        if command.quantity <= 0:
            raise ValueError("material delivery quantity must be greater than zero")
    if command.operation is MaterialOperation.ADD_NOTE and command.note is None:
        raise ValueError("material note requires note text")


def _validate_issue(command: ConversationIssueCommand) -> None:
    if command.ambiguous:
        raise ValueError("ambiguous language cannot produce an issue command")
    allowed = {
        IssueOperation.CREATE: {"operation", "issue_type", "severity", "description"},
        IssueOperation.ASSIGN: {"operation", "issue", "owner", "expected_version"},
        IssueOperation.CHANGE_STATUS: {"operation", "issue", "target_status", "expected_version"},
        IssueOperation.RESOLVE: {
            "operation",
            "issue",
            "evidence",
            "negated",
            "ambiguous",
            "expected_version",
        },
        IssueOperation.ADD_NOTE: {"operation", "issue", "note", "expected_version"},
    }[command.operation]
    _reject_operation_fields(command, allowed)
    if command.operation is IssueOperation.CREATE:
        if command.issue_type is None or command.severity is None or command.description is None:
            raise ValueError("issue creation requires type, severity, and description")
        return
    if command.issue is None or command.expected_version is None:
        raise ValueError("issue mutation requires an authorized versioned issue")
    if command.operation is IssueOperation.RESOLVE and (
        not command.evidence or command.negated or command.ambiguous
    ):
        raise ValueError("issue resolution requires clear positive evidence")
    if command.operation is IssueOperation.CHANGE_STATUS and command.target_status is None:
        raise ValueError("issue status change requires target_status")
    if (
        command.operation is IssueOperation.CHANGE_STATUS
        and command.target_status is IssueStatus.RESOLVED
    ):
        raise ValueError("issue resolution requires the typed resolve operation")
    if command.operation is IssueOperation.ASSIGN and command.owner is None:
        raise ValueError("issue assignment requires a resolved owner")
    if command.operation is IssueOperation.ADD_NOTE and command.note is None:
        raise ValueError("issue note requires note text")


def _reject_operation_fields(command: BaseModel, allowed: set[str]) -> None:
    supplied = set(command.model_dump(exclude_none=True, exclude_defaults=True)) | {"operation"}
    invalid = sorted(supplied - allowed)
    if invalid:
        operation = getattr(command, "operation")
        raise ValueError(f"{operation.value} does not accept fields: {', '.join(invalid)}")


_AMBIGUOUS_MATERIAL_QUANTITY = re.compile(
    r"^add\s+(?P<quantity>\d+(?:\.\d+)?)\s+(?P<unit>[a-z]+)\s+of\s+"
    r"(?P<material>[a-z][a-z -]*?)(?:\s+to\s+stock)?$",
    re.IGNORECASE,
)


def ambiguous_material_quantity_phrase(message: str) -> tuple[str, str, str] | None:
    """Extract quantity and unit from additive stock wording lacking clear semantics."""

    normalized = " ".join(message.casefold().split()).rstrip("?!. ")
    match = _AMBIGUOUS_MATERIAL_QUANTITY.fullmatch(normalized)
    if match is None:
        return None
    padded = f" {normalized} "
    if (
        " additional " in padded
        or " more " in padded
        or " to inventory " in padded
        or " to our inventory " in padded
        or " to stock " in padded
        or " in stock " in padded
        or " on site " in padded
        or " to the request " in padded
        or " arrived " in padded
        or " delivered " in padded
        or " received " in padded
    ):
        return None
    return match.group("quantity"), match.group("unit"), match.group("material")


__all__ = [
    "ActionComposer",
    "ActionInterpretation",
    "ActionInterpretationEnvelope",
    "ambiguous_material_quantity_phrase",
    "ComposedAction",
    "IssueActionInterpretation",
    "MaterialActionInterpretation",
    "PurchaseActionInterpretation",
    "ScheduleActionInterpretation",
    "TaskActionInterpretation",
    "TaskActionBatchInterpretation",
]
