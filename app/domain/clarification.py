from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ClarificationResolutionType(StrEnum):
    INVENTORY_INCREMENT = "inventory_increment"
    MATERIAL_REQUEST = "material_request"
    AMBIGUOUS = "ambiguous"


class ClarificationKind(StrEnum):
    MATERIAL_OPERATION = "material_operation"
    TASK_BATCH = "task_batch"


class ClarificationStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PendingClarification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    kind: ClarificationKind
    entity_reference: str = Field(min_length=1, max_length=300)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=100)
    allowed_resolutions: tuple[ClarificationResolutionType, ...] = Field(default_factory=tuple)
    status: ClarificationStatus = ClarificationStatus.PENDING
    created_at: AwareDatetime
    expires_at: AwareDatetime | None = None
    # Serialized, typed task-batch interpretation retained across refreshes.
    # The action schema is validated again before execution; this is not project truth.
    action_json: str | None = Field(default=None, max_length=100_000)
