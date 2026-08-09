from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    AttachmentUploadStatus,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    ProcessedEventStatus,
    ProcessingStatus,
    ProjectStatus,
    ReportStatus,
    Severity,
    SiteUpdateInputType,
    TaskPriority,
    TaskSource,
    TaskStatus,
    UserStatus,
    WorkflowName,
    OutboxStatus,
)


CanonicalId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^[a-z][a-z0-9]{1,15}_[a-z0-9][a-z0-9_-]{2,127}$",
    ),
]
IdempotencyKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    ),
]
EmailAddress = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        max_length=320,
    ),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class Project(DomainModel):
    id: CanonicalId
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5_000)
    timezone: str
    start_date: date | None = None
    target_end_date: date | None = None
    status: ProjectStatus = ProjectStatus.PLANNING
    created_by: CanonicalId
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if (
            self.start_date is not None
            and self.target_end_date is not None
            and self.target_end_date < self.start_date
        ):
            raise ValueError("target_end_date cannot be before start_date")
        return self


class Task(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus = TaskStatus.PROPOSED
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: CanonicalId | None = None
    planned_start: AwareDatetime | None = None
    planned_end: AwareDatetime | None = None
    actual_start: AwareDatetime | None = None
    actual_completion: AwareDatetime | None = None
    dependency_ids: list[CanonicalId] = Field(default_factory=list)
    completion_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    source: TaskSource = TaskSource.MANUAL
    version: int = Field(default=0, ge=0)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_task_invariants(self) -> Self:
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")

        if (
            self.actual_start
            and self.actual_completion
            and self.actual_completion < self.actual_start
        ):
            raise ValueError("actual_completion cannot be before actual_start")

        if self.status is TaskStatus.COMPLETED and self.completion_percent != Decimal("100"):
            raise ValueError("completion_percent must be 100 when status is completed")

        if self.status is TaskStatus.COMPLETED and self.actual_completion is None:
            raise ValueError("actual_completion is required when status is completed")

        if self.id in self.dependency_ids:
            raise ValueError("a task cannot depend on itself")

        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ValueError("dependency_ids cannot contain duplicate task IDs")

        return self


class User(DomainModel):
    id: CanonicalId
    identity_subject: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    email: EmailAddress
    avatar_url: str | None = Field(default=None, max_length=2_000)
    status: UserStatus = UserStatus.ACTIVE
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)


class ProjectMember(DomainModel):
    project_id: CanonicalId
    user_id: CanonicalId
    role: MemberRole
    status: MemberStatus = MemberStatus.INVITED
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @property
    def id(self) -> str:
        return self.user_id


class SiteUpdate(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    submitted_by: CanonicalId
    input_type: SiteUpdateInputType
    raw_text: NonEmptyText | None = Field(default=None, max_length=1_000_000)
    submitted_transcript: NonEmptyText | None = Field(default=None, max_length=1_000_000)
    transcript: NonEmptyText | None = Field(default=None, max_length=1_000_000)
    attachment_ids: list[CanonicalId] = Field(default_factory=list)
    transcribed_attachment_ids: list[CanonicalId] = Field(default_factory=list)
    client_event_id: str = Field(min_length=1, max_length=256)
    processing_status: ProcessingStatus = ProcessingStatus.RECEIVED
    submitted_at: AwareDatetime = Field(default_factory=utc_now)
    processed_at: AwareDatetime | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if not self.raw_text and not self.transcript and not self.attachment_ids:
            raise ValueError(
                "site update requires at least one text, transcript, or attachment input"
            )
        if len(self.attachment_ids) != len(set(self.attachment_ids)):
            raise ValueError("attachment_ids cannot contain duplicates")
        if len(self.transcribed_attachment_ids) != len(set(self.transcribed_attachment_ids)):
            raise ValueError("transcribed_attachment_ids cannot contain duplicates")
        if not set(self.transcribed_attachment_ids).issubset(self.attachment_ids):
            raise ValueError("transcribed attachments must belong to the site update")
        if self.transcribed_attachment_ids and not self.transcript:
            raise ValueError("transcript is required for transcribed attachments")

        terminal_statuses = {ProcessingStatus.COMPLETED, ProcessingStatus.FAILED}
        if self.processing_status in terminal_statuses and self.processed_at is None:
            raise ValueError("processed_at is required for a terminal site update")
        if self.processing_status not in terminal_statuses and self.processed_at is not None:
            raise ValueError("processed_at is only valid for a terminal site update")
        if self.processed_at is not None and self.processed_at < self.submitted_at:
            raise ValueError("processed_at cannot be before submitted_at")
        return self


class Attachment(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    site_update_id: CanonicalId | None = None
    object_path: str = Field(min_length=1, max_length=2_000)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    upload_status: AttachmentUploadStatus = AttachmentUploadStatus.INITIATED
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class Issue(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    type: IssueType
    severity: Severity
    description: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[NonEmptyText] = Field(default_factory=list)
    task_ids: list[CanonicalId] = Field(default_factory=list)
    status: IssueStatus = IssueStatus.OPEN
    detected_by: IssueDetectedBy
    owner_id: CanonicalId | None = None
    due_at: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_issue(self) -> Self:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs cannot contain duplicates")
        if len(self.task_ids) != len(set(self.task_ids)):
            raise ValueError("task_ids cannot contain duplicates")
        terminal_statuses = {IssueStatus.RESOLVED, IssueStatus.DISMISSED}
        if self.status in terminal_statuses and self.resolved_at is None:
            raise ValueError("resolved_at is required when an issue is resolved or dismissed")
        if self.status not in terminal_statuses and self.resolved_at is not None:
            raise ValueError("resolved_at is only valid for a resolved or dismissed issue")
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("resolved_at cannot be before created_at")
        return self


class Material(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    name: str = Field(min_length=1, max_length=300)
    normalized_name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list)
    unit: str = Field(min_length=1, max_length=100)
    available_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    reserved_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_required_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    upcoming_requirement_quantity: Decimal | None = Field(default=None, ge=0)
    estimated_unit_cost: Decimal | None = Field(default=None, ge=0)
    default_supplier: str | None = Field(default=None, max_length=500)
    version: int = Field(default=0, ge=0)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_stock(self) -> Self:
        if self.reserved_quantity > self.available_quantity:
            raise ValueError("reserved_quantity cannot exceed available_quantity")
        if len(self.aliases) != len(set(alias.casefold() for alias in self.aliases)):
            raise ValueError("material aliases cannot contain duplicates")
        return self


class MaterialRequest(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    material_id: CanonicalId
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=100)
    needed_by: AwareDatetime | None = None
    reason: str = Field(min_length=1, max_length=5_000)
    source_event_id: CanonicalId
    supplier: str | None = Field(default=None, max_length=500)
    estimated_total_cost: Decimal | None = Field(default=None, ge=0)
    status: MaterialRequestStatus = MaterialRequestStatus.PROPOSED
    approval_id: CanonicalId | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_approval_link(self) -> Self:
        if (
            self.status
            not in {
                MaterialRequestStatus.PROPOSED,
                MaterialRequestStatus.CANCELLED,
            }
            and self.approval_id is None
        ):
            raise ValueError("approval_id is required after a material request is proposed")
        return self


class Approval(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    action_type: ApprovalActionType
    proposed_action: dict[str, Any] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=5_000)
    evidence_refs: list[NonEmptyText] = Field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_by: CanonicalId | Literal["system"]
    requested_at: AwareDatetime = Field(default_factory=utc_now)
    resolved_at: AwareDatetime | None = None
    resolved_by: CanonicalId | None = None
    resolution_notes: str | None = Field(default=None, max_length=5_000)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.status is ApprovalStatus.PENDING and any(
            (self.resolved_at, self.resolved_by, self.resolution_notes)
        ):
            raise ValueError("resolution fields must be empty while approval is pending")

        if self.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED} and (
            self.resolved_at is None or self.resolved_by is None
        ):
            raise ValueError("resolved_at and resolved_by are required for an approval decision")
        if self.resolved_at is not None and self.resolved_at < self.requested_at:
            raise ValueError("resolved_at cannot be before requested_at")
        return self


class ReportFact(DomainModel):
    summary: str = Field(min_length=1, max_length=5_000)
    source_refs: list[NonEmptyText] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DailyReport(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    report_date: date
    summary: str = Field(min_length=1, max_length=20_000)
    completed_work: list[ReportFact] = Field(default_factory=list)
    active_blockers: list[ReportFact] = Field(default_factory=list)
    material_risks: list[ReportFact] = Field(default_factory=list)
    next_focus: list[ReportFact] = Field(default_factory=list)
    source_update_ids: list[CanonicalId] = Field(default_factory=list)
    status: ReportStatus = ReportStatus.DRAFT
    version: int = Field(default=0, ge=0)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)


class AgentRun(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    trigger_event_id: CanonicalId
    workflow: WorkflowName
    status: AgentRunStatus = AgentRunStatus.QUEUED
    attempt: int = Field(default=1, ge=1)
    step: str | None = Field(default=None, max_length=300)
    started_at: AwareDatetime = Field(default_factory=utc_now)
    completed_at: AwareDatetime | None = None
    trace_id: str = Field(min_length=1, max_length=256)
    result_summary: str | None = Field(default=None, max_length=5_000)
    pending_actions: list[NonEmptyText] = Field(default_factory=list, max_length=200)
    error_code: str | None = Field(default=None, max_length=128)
    error_summary: str | None = Field(default=None, max_length=5_000)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        terminal_statuses = {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.DEAD_LETTERED,
        }
        if self.status in terminal_statuses and self.completed_at is None:
            raise ValueError("completed_at is required for a terminal agent run")
        if self.status not in terminal_statuses and self.completed_at is not None:
            raise ValueError("completed_at is only valid for a terminal agent run")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be before started_at")

        if self.status in {AgentRunStatus.FAILED, AgentRunStatus.DEAD_LETTERED} and not (
            self.error_code and self.error_summary
        ):
            raise ValueError("error_code and error_summary are required for a failed agent run")
        return self


class ActivityEvent(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    actor_type: ActorType
    actor_id: CanonicalId | None = None
    action: str = Field(min_length=1, max_length=300)
    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: CanonicalId
    summary: str = Field(min_length=1, max_length=5_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_event_id: CanonicalId | None = None
    agent_run_id: CanonicalId | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_actor(self) -> Self:
        if self.actor_type in {ActorType.USER, ActorType.AGENT} and self.actor_id is None:
            raise ValueError("actor_id is required for user and agent activities")
        return self


class ProcessedEvent(DomainModel):
    id: IdempotencyKey
    project_id: CanonicalId
    event_id: CanonicalId
    schema_version: str = Field(default="1.0", min_length=1, max_length=16)
    event_type: str = Field(min_length=1, max_length=128)
    status: ProcessedEventStatus = ProcessedEventStatus.CLAIMED
    event_fingerprint: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    claim_token: str | None = Field(default=None, min_length=1, max_length=256)
    lease_expires_at: AwareDatetime | None = None
    result_ref: str | None = Field(default=None, max_length=1_000)
    first_seen_at: AwareDatetime = Field(default_factory=utc_now)
    completed_at: AwareDatetime | None = None
    attempts: int = Field(default=1, ge=1)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_summary: str | None = Field(default=None, max_length=5_000)
    dead_lettered_at: AwareDatetime | None = None
    dead_letter_reason: str | None = Field(default=None, max_length=5_000)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        if self.status is ProcessedEventStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed_at is required for a completed processed event")
        if self.status is not ProcessedEventStatus.COMPLETED and self.completed_at is not None:
            raise ValueError("completed_at is only valid for a completed processed event")
        if self.completed_at is not None and self.completed_at < self.first_seen_at:
            raise ValueError("completed_at cannot be before first_seen_at")
        if self.lease_expires_at is not None and self.lease_expires_at <= self.first_seen_at:
            raise ValueError("lease_expires_at must be after first_seen_at")
        if self.dead_lettered_at is not None and self.dead_lettered_at < self.first_seen_at:
            raise ValueError("dead_lettered_at cannot be before first_seen_at")

        if self.status is ProcessedEventStatus.CLAIMED:
            if self.claim_token is None or self.lease_expires_at is None:
                raise ValueError(
                    "claim_token and lease_expires_at are required for a claimed event"
                )
            if self.dead_lettered_at is not None or self.dead_letter_reason is not None:
                raise ValueError("dead-letter metadata is only valid for a dead-lettered event")
        elif self.status is ProcessedEventStatus.DEAD_LETTERED:
            if self.dead_lettered_at is None or not self.dead_letter_reason:
                raise ValueError("dead_lettered_at and dead_letter_reason are required")
            if not self.last_error_code or not self.last_error_summary:
                raise ValueError("dead-lettered events require error metadata")
            if self.claim_token is not None or self.lease_expires_at is not None:
                raise ValueError("a dead-lettered event cannot retain an active claim")
        else:
            if self.claim_token is not None or self.lease_expires_at is not None:
                raise ValueError("only claimed events may have an active lease")
            if self.dead_lettered_at is not None or self.dead_letter_reason is not None:
                raise ValueError("dead-letter metadata is only valid for a dead-lettered event")
            if self.status is ProcessedEventStatus.COMPLETED and not self.result_ref:
                raise ValueError("result_ref is required for a completed processed event")
            if self.status is ProcessedEventStatus.FAILED and not (
                self.last_error_code and self.last_error_summary
            ):
                raise ValueError("failed processed events require error metadata")
        if self.status is not ProcessedEventStatus.COMPLETED and self.result_ref is not None:
            raise ValueError("result_ref is only valid for a completed processed event")
        return self


class OutboxMessage(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    message_type: str = Field(min_length=1, max_length=128)
    deduplication_key: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    last_error: str | None = Field(default=None, max_length=5_000)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    processed_at: AwareDatetime | None = None
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_outbox(self) -> Self:
        terminal_statuses = {OutboxStatus.COMPLETED, OutboxStatus.DEAD_LETTERED}
        if self.status in terminal_statuses and self.processed_at is None:
            raise ValueError("processed_at is required for terminal outbox statuses")
        if self.status not in terminal_statuses and self.processed_at is not None:
            raise ValueError("processed_at is only valid for terminal outbox statuses")
        if self.processed_at is not None and self.processed_at < self.created_at:
            raise ValueError("processed_at cannot be before created_at")
        return self
