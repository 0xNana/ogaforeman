"""Typed, non-mutating contracts for conversational intent routing."""

from __future__ import annotations

from enum import StrEnum
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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


__all__ = [
    "ConversationContext",
    "ContextDomain",
    "ContextFocus",
    "ContextQuery",
    "ConversationalProjectContext",
    "IntentDecision",
    "IntentDestination",
    "IntentRoute",
    "IntentType",
    "ReferencedEntity",
]
