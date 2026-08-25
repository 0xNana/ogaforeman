from enum import StrEnum


class ProjectStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(StrEnum):
    PROPOSED = "proposed"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskSource(StrEnum):
    MANUAL = "manual"
    SITE_UPDATE = "site_update"
    WORKFLOW = "workflow"
    IMPORT = "import"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class MemberRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    FOREMAN = "foreman"
    VIEWER = "viewer"


class MemberStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    REMOVED = "removed"


class SiteUpdateInputType(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    PHOTO = "photo"
    MIXED = "mixed"
    FILE = "file"


class ProcessingStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    COMPLETED = "completed"
    FAILED = "failed"


class AttachmentUploadStatus(StrEnum):
    INITIATED = "initiated"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DELETED = "deleted"


class IssueType(StrEnum):
    BLOCKER = "blocker"
    DELAY_RISK = "delay_risk"
    SAFETY = "safety"
    QUALITY = "quality"
    OBSERVATION = "observation"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class IssueDetectedBy(StrEnum):
    SITE_UPDATE = "site_update"
    OVERDUE_CHECK = "overdue_check"
    DELIVERY_EVENT = "delivery_event"
    USER = "user"


class MaterialRequestStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    DELAYED = "delayed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ApprovalActionType(StrEnum):
    PURCHASE = "purchase"
    SCHEDULE_CHANGE = "schedule_change"
    EXTERNAL_COMMITMENT = "external_commitment"
    TASK_CANCEL = "task_cancel"
    HIGH_IMPACT_CHANGE = "high_impact_change"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class ActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class WorkflowName(StrEnum):
    DAILY_SITE_UPDATE = "daily_site_update"
    MATERIAL_SHORTAGE = "material_shortage"
    BLOCKER_DELAY = "blocker_delay"
    DAILY_BRIEF = "daily_brief"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class ProcessedEventStatus(StrEnum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
