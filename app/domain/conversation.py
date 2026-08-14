"""Typed, non-mutating contracts for conversational intent routing."""

from __future__ import annotations

from enum import StrEnum
from datetime import date, datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.enums import TaskPriority, TaskStatus


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


class MaterialContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    unit: str
    available_quantity: Decimal
    reserved_quantity: Decimal
    minimum_required_quantity: Decimal
    upcoming_requirement_quantity: Decimal | None = None


class MaterialRequestContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    material_id: str
    quantity: Decimal
    unit: str
    status: str
    needed_by: datetime | None = None
    reason: str
    approval_id: str | None = None


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


__all__ = [
    "ConversationContext",
    "ConversationMaterialCommand",
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
    "MaterialOperation",
    "ReplyKind",
    "TaskOperation",
    "ReferencedEntity",
]
