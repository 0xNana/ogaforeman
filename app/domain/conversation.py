"""Typed, non-mutating contracts for conversational intent routing."""

from __future__ import annotations

from enum import StrEnum
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import IssueStatus, IssueType, Severity, TaskPriority, TaskStatus


class IntentType(StrEnum):
    CASUAL = "casual"
    PROJECT_QUERY = "project_query"
    PROJECT_ADVICE = "project_advice"
    PROJECT_MUTATION = "project_mutation"
    SITE_UPDATE = "site_update"
    CLARIFICATION_RESPONSE = "clarification_response"
    CONFIRMATION_RESPONSE = "confirmation_response"
    UNKNOWN = "unknown"


class IntentDestination(StrEnum):
    CASUAL_RESPONSE = "casual_response"
    PROJECT_CONTEXT = "project_context"
    PROJECT_ADVICE = "project_advice"
    PROJECT_ACTION = "project_action"
    GOLDEN_SITE_UPDATE = "golden_site_update"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"


class ConfirmationDisposition(StrEnum):
    ACCEPT = "accept"
    CANCEL = "cancel"


class ContextDomain(StrEnum):
    PROJECT = "project"
    TASKS = "tasks"
    ISSUES = "issues"
    MATERIALS = "materials"
    MATERIAL_REQUESTS = "material_requests"
    APPROVALS = "approvals"
    SCHEDULE = "schedule"
    DAILY_LOGS = "daily_logs"
    RECENT_ACTIVITY = "recent_activity"
    PROJECT_MEMBERS = "project_members"


class ContextFocus(StrEnum):
    CURRENT = "current"
    TODAY = "today"
    TOMORROW = "tomorrow"
    OVERDUE = "overdue"
    LOW_STOCK = "low_stock"
    PENDING = "pending"


class ReplyKind(StrEnum):
    CASUAL = "casual"
    PROJECT = "project"
    CLARIFICATION = "clarification"
    ADVICE = "advice"


class EntityKind(StrEnum):
    TASK = "task"
    ISSUE = "issue"
    MATERIAL = "material"
    MATERIAL_REQUEST = "material_request"
    SCHEDULE_ACTIVITY = "schedule_activity"
    PROJECT_MEMBER = "project_member"
    DAILY_LOG = "daily_log"


class EntityResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class TaskOperation(StrEnum):
    CREATE = "create"
    COMPLETE = "complete"
    CHANGE_STATUS = "change_status"
    ASSIGN = "assign"
    REASSIGN = "reassign"
    CHANGE_PRIORITY = "change_priority"
    ADD_NOTE = "add_note"


class MaterialOperation(StrEnum):
    CREATE = "create"
    SET_ON_SITE = "set_on_site"
    SET_REQUIRED = "set_required"
    RECORD_DELIVERY = "record_delivery"
    ADD_NOTE = "add_note"


class IssueOperation(StrEnum):
    CREATE = "create"
    ASSIGN = "assign"
    CHANGE_STATUS = "change_status"
    RESOLVE = "resolve"
    ADD_NOTE = "add_note"


class MutationPolicyClass(StrEnum):
    AUTO_EXECUTE = "auto_execute"
    CONFIRM_FIRST = "confirm_first"
    APPROVAL_REQUIRED = "approval_required"
    DENY_OR_ESCALATE = "deny_or_escalate"


class MutationKind(StrEnum):
    TASK_CREATE = "task_create"
    TASK_COMPLETE = "task_complete"
    TASK_ASSIGN = "task_assign"
    TASK_UPDATE = "task_update"
    MATERIAL_CREATE = "material_create"
    MATERIAL_QUANTITY = "material_quantity"
    MATERIAL_DELIVERY = "material_delivery"
    MATERIAL_UPDATE = "material_update"
    ISSUE_CREATE = "issue_create"
    ISSUE_RESOLVE = "issue_resolve"
    ISSUE_UPDATE = "issue_update"
    ADD_NOTE = "add_note"
    SCHEDULE_DATES = "schedule_dates"
    TASK_DEPENDENCIES = "task_dependencies"
    BULK_TASK_UPDATE = "bulk_task_update"
    TASK_REOPEN = "task_reopen"
    TASK_CANCEL = "task_cancel"
    RECORD_DELETE = "record_delete"
    MATERIAL_PURCHASE = "material_purchase"
    FINANCIAL_COMMITMENT = "financial_commitment"
    EXTERNAL_COMMITMENT = "external_commitment"
    MAJOR_SCHEDULE_CHANGE = "major_schedule_change"
    STRUCTURAL_CERTIFICATION = "structural_certification"
    UNSAFE_ENGINEERING_JUDGMENT = "unsafe_engineering_judgment"
    CONCEAL_SAFETY_RISK = "conceal_safety_risk"


class ReferencedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=160)


class IntentDecision(BaseModel):
    """Observable classification output; private model reasoning is forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    requested_action: str | None = Field(default=None, max_length=160)
    referenced_entities: tuple[ReferencedEntity, ...] = Field(default_factory=tuple)
    requires_project_context: bool = False
    requires_mutation: bool = False
    ambiguity: str | None = Field(default=None, max_length=240)
    reason_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    confirmation_disposition: ConfirmationDisposition | None = None

    @model_validator(mode="after")
    def validate_confirmation_disposition(self) -> Self:
        if (
            self.intent is IntentType.CONFIRMATION_RESPONSE
            and self.confirmation_disposition is None
        ):
            raise ValueError("confirmation responses require an accept or cancel disposition")
        if (
            self.intent is not IntentType.CONFIRMATION_RESPONSE
            and self.confirmation_disposition is not None
        ):
            raise ValueError("only confirmation responses may include a disposition")
        return self


class ConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    has_active_project: bool = False
    has_pending_clarification: bool = False
    has_pending_confirmation: bool = False


class IntentRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: IntentDecision
    destination: IntentDestination
    mutation_allowed: bool = False


class ContextQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domains: tuple[ContextDomain, ...] = Field(min_length=1, max_length=10)
    search_terms: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    focus: ContextFocus = ContextFocus.CURRENT


class ProjectContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    location: str
    timezone: str
    status: str


class TaskContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    status: str
    priority: str
    assignee_id: str | None = None
    assignee_name: str | None = None
    trade: str | None = None
    location: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    actual_completion: datetime | None = None
    dependency_ids: tuple[str, ...] = ()
    version: int = Field(default=0, ge=0)


class IssueContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    type: str
    severity: str
    description: str
    status: str
    task_ids: tuple[str, ...] = ()
    owner_id: str | None = None
    owner_name: str | None = None
    due_at: datetime | None = None
    version: int = Field(default=0, ge=0)


class MaterialContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    unit: str
    available_quantity: Decimal
    reserved_quantity: Decimal
    minimum_required_quantity: Decimal
    upcoming_requirement_quantity: Decimal | None = None
    version: int = Field(default=0, ge=0)


class MaterialRequestContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    material_id: str
    quantity: Decimal
    delivered_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    unit: str
    status: str
    needed_by: datetime | None = None
    reason: str
    approval_id: str | None = None
    version: int = Field(default=0, ge=0)


class ApprovalContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    action_type: str
    status: str
    reason: str
    requested_at: datetime


class DailyLogContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    report_date: date
    summary: str
    active_blockers: tuple[str, ...] = ()
    material_risks: tuple[str, ...] = ()
    next_focus: tuple[str, ...] = ()


class ActivityContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    created_at: datetime


class MemberContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    display_name: str
    role: str


class ConversationalProjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    retrieved_at: datetime
    query: ContextQuery
    project: ProjectContextItem | None = None
    tasks: tuple[TaskContextItem, ...] = ()
    issues: tuple[IssueContextItem, ...] = ()
    materials: tuple[MaterialContextItem, ...] = ()
    material_requests: tuple[MaterialRequestContextItem, ...] = ()
    approvals: tuple[ApprovalContextItem, ...] = ()
    schedule: tuple[TaskContextItem, ...] = ()
    daily_logs: tuple[DailyLogContextItem, ...] = ()
    recent_activity: tuple[ActivityContextItem, ...] = ()
    members: tuple[MemberContextItem, ...] = ()


class ConversationReply(BaseModel):
    """Concise user-facing text plus internal grounding references."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ReplyKind
    text: str = Field(min_length=1, max_length=1_000)
    cited_record_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)


class AdviceReply(BaseModel):
    """A grounded recommendation that cannot itself authorize a mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=1_000)
    recommendation: str = Field(pattern=r"^(proceed|hold|review)$")
    cited_record_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    mutation_performed: bool = False


class EntityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str
    kind: EntityKind
    display_name: str = Field(min_length=1, max_length=300)
    match_score: float = Field(ge=0.0, le=1.0)


class EntityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EntityKind
    reference: str = Field(min_length=1, max_length=300)
    status: EntityResolutionStatus
    entity_id: str | None = None
    display_name: str | None = None
    match_method: str | None = Field(default=None, max_length=32)
    candidates: tuple[EntityCandidate, ...] = Field(default_factory=tuple, max_length=5)
    clarification: str | None = Field(default=None, max_length=500)
    can_mutate: bool = False


class ConversationTaskCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: TaskOperation
    task: EntityResolution | None = None
    assignee: EntityResolution | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    trade: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=500)
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    target_status: TaskStatus | None = None
    priority: TaskPriority | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    evidence: str | None = Field(default=None, min_length=1, max_length=5_000)
    negated: bool = False
    ambiguous: bool = False
    reopening: bool = False
    expected_version: int | None = Field(default=None, ge=0)


class ConversationMaterialCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: MaterialOperation
    material: EntityResolution | None = None
    material_request: EntityResolution | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    aliases: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    reason: str | None = Field(default=None, min_length=1, max_length=5_000)
    delivery_complete: bool = False
    requires_material_risk_workflow: bool = False
    expected_version: int | None = Field(default=None, ge=0)
    expected_material_request_version: int | None = Field(default=None, ge=0)


class ConversationIssueCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    operation: IssueOperation
    issue: EntityResolution | None = None
    owner: EntityResolution | None = None
    issue_type: IssueType | None = None
    severity: Severity | None = None
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    target_status: IssueStatus | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    evidence: str | None = Field(default=None, min_length=1, max_length=5_000)
    negated: bool = False
    ambiguous: bool = False
    expected_version: int | None = Field(default=None, ge=0)


class ConversationPurchaseCommand(BaseModel):
    """A purchase proposal only; execution always belongs to the approval workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    material: EntityResolution
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=5_000)
    needed_by: AwareDatetime | None = None
    supplier: str | None = Field(default=None, max_length=500)
    estimated_total_cost: Decimal | None = Field(default=None, ge=0)
    expected_material_version: int = Field(ge=0)


class MutationPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: str
    kind: MutationKind
    affected_entity_count: int = Field(default=1, ge=1, le=100)
    dependent_entity_count: int = Field(default=0, ge=0, le=100)


class MutationPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy: MutationPolicyClass
    reason_code: str = Field(pattern=r"^[a-z0-9_]+$")
    use_existing_approval: bool = False


class PendingCommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    proposal_id: str = Field(
        pattern=r"^cpr_[a-z0-9][a-z0-9_-]{0,127}$",
        max_length=132,
    )
    project_id: str
    actor_id: str
    policy_decision: MutationPolicyDecision
    idempotency_key: str = Field(min_length=1, max_length=240)
    requested_action: str = Field(min_length=1, max_length=500)
    created_at: AwareDatetime


class PendingTaskCommand(PendingCommandBase):
    kind: Literal["task"] = "task"
    command: ConversationTaskCommand


class PendingMaterialCommand(PendingCommandBase):
    kind: Literal["material"] = "material"
    command: ConversationMaterialCommand


class PendingIssueCommand(PendingCommandBase):
    kind: Literal["issue"] = "issue"
    command: ConversationIssueCommand


class ScheduleTaskVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str
    version: int = Field(ge=0)


class ScheduleProposalToken(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: str
    actor_id: str
    target_task_id: str
    planned_start: AwareDatetime
    planned_end: AwareDatetime
    affected_versions: tuple[ScheduleTaskVersion, ...]
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_token(self) -> Self:
        task_ids = [item.task_id for item in self.affected_versions]
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise ValueError("schedule proposal task versions must be non-empty and unique")
        if self.target_task_id not in task_ids:
            raise ValueError("schedule proposal must include its target task")
        if self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        return self


class ScheduleChangeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: str
    task: EntityResolution
    planned_start: AwareDatetime
    planned_end: AwareDatetime
    expected_version: int | None = Field(default=None, ge=0)
    confirmed: bool = False
    proposal: ScheduleProposalToken | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        if self.confirmed and self.proposal is None:
            raise ValueError("confirmed schedule changes require the reviewed proposal")
        return self


class PendingScheduleCommand(PendingCommandBase):
    kind: Literal["schedule"] = "schedule"
    command: ScheduleChangeCommand

    @model_validator(mode="after")
    def validate_nested_scope(self) -> Self:
        if self.command.project_id != self.project_id:
            raise ValueError("schedule command project must match its pending envelope")
        proposal = self.command.proposal
        if proposal is not None and (
            proposal.project_id != self.project_id or proposal.actor_id != self.actor_id
        ):
            raise ValueError("schedule proposal scope must match its pending envelope")
        return self


PendingConversationCommand = Annotated[
    PendingTaskCommand | PendingMaterialCommand | PendingIssueCommand | PendingScheduleCommand,
    Field(discriminator="kind"),
]


class SiteUpdateRouteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    project_id: str
    text: str = Field(min_length=1, max_length=1_000_000)
    idempotency_key: str = Field(min_length=1, max_length=256)
    occurred_at: AwareDatetime | None = None


__all__ = [
    "AdviceReply",
    "ConversationContext",
    "ConversationIssueCommand",
    "ConversationMaterialCommand",
    "ConversationPurchaseCommand",
    "ConversationReply",
    "ConversationTaskCommand",
    "ContextDomain",
    "ContextFocus",
    "ContextQuery",
    "ConversationalProjectContext",
    "EntityCandidate",
    "EntityKind",
    "EntityResolution",
    "EntityResolutionStatus",
    "IntentDecision",
    "IntentDestination",
    "IntentRoute",
    "IntentType",
    "IssueOperation",
    "MaterialOperation",
    "MutationKind",
    "MutationPolicyClass",
    "MutationPolicyDecision",
    "MutationPolicyRequest",
    "ReplyKind",
    "ScheduleChangeCommand",
    "SiteUpdateRouteCommand",
    "TaskOperation",
    "ReferencedEntity",
]
