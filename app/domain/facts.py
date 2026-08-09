from enum import StrEnum

from pydantic import BaseModel, Field

from app.domain.enums import IssueType, Severity


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BaseFact(BaseModel):
    evidence: str = Field(description="Exact quote or clear basis from the source text.")
    confidence: ConfidenceLevel = Field(description="Confidence level in the extraction.")
    is_negated: bool = Field(
        default=False,
        description="True if the text explicitly states this did NOT happen or is absent.",
    )
    clarification_needed: str | None = Field(
        default=None,
        description="If the statement is ambiguous, what question needs to be asked to clarify it?",
    )


class TaskCompletionFact(BaseFact):
    task_name: str = Field(description="The name or description of the task.")
    is_completed: bool = Field(description="Whether the task was completed.")


class MaterialQuantityFact(BaseFact):
    material_name: str = Field(description="The name of the material.")
    quantity: float | None = Field(
        default=None, description="The numerical quantity mentioned, if any."
    )
    unit: str | None = Field(default=None, description="The unit of the material, if specified.")


class SafetyIssueFact(BaseFact):
    description: str = Field(description="Description of the safety or structural issue.")
    severity: str = Field(description="Perceived severity (e.g., high, medium, low).")


class IssueFact(BaseFact):
    issue_type: IssueType = Field(description="The durable issue classification.")
    description: str = Field(min_length=1, max_length=10_000)
    severity: Severity
    task_name: str | None = Field(default=None, min_length=1, max_length=300)


class NextFocusFact(BaseFact):
    description: str = Field(min_length=1, max_length=5_000)
    task_name: str | None = Field(default=None, min_length=1, max_length=300)


class ExtractedFactSet(BaseModel):
    tasks: list[TaskCompletionFact] = Field(default_factory=list)
    materials: list[MaterialQuantityFact] = Field(default_factory=list)
    issues: list[IssueFact] = Field(default_factory=list)
    next_focus: list[NextFocusFact] = Field(default_factory=list)
    safety_issues: list[SafetyIssueFact] = Field(default_factory=list)
