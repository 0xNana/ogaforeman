"""Versioned, model-independent contracts for project initialization drafts.

These objects are candidates produced by an extraction boundary. They contain
draft-only temporary references and never expose canonical task/material IDs to
the model. Deterministic validation and import services own canonicalization and
all persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from .enums import ProjectStatus
from .materials import canonicalize_unit
from .models import CanonicalId, DomainModel, utc_now


DraftTempId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^tmp_[a-z0-9][a-z0-9_-]{2,127}$",
    ),
]
StrictText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProjectImportStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    DRAFT = "draft"
    VALIDATING = "validating"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    IMPORTING = "importing"
    IMPORTED = "imported"
    EXTRACTION_FAILED = "extraction_failed"
    VALIDATION_FAILED = "validation_failed"
    IMPORT_FAILED = "import_failed"
    CANCELLED = "cancelled"


PROJECT_IMPORT_STATUS_TRANSITIONS: Final[
    Mapping[ProjectImportStatus, frozenset[ProjectImportStatus]]
] = MappingProxyType(
    {
        ProjectImportStatus.UPLOADED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.EXTRACTING: frozenset(
            {
                ProjectImportStatus.DRAFT,
                ProjectImportStatus.EXTRACTION_FAILED,
                ProjectImportStatus.CANCELLED,
            }
        ),
        ProjectImportStatus.DRAFT: frozenset(
            {ProjectImportStatus.VALIDATING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.VALIDATING: frozenset(
            {
                ProjectImportStatus.NEEDS_REVIEW,
                ProjectImportStatus.VALIDATION_FAILED,
                ProjectImportStatus.CANCELLED,
            }
        ),
        ProjectImportStatus.NEEDS_REVIEW: frozenset(
            {ProjectImportStatus.CONFIRMED, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.CONFIRMED: frozenset({ProjectImportStatus.IMPORTING}),
        ProjectImportStatus.IMPORTING: frozenset(
            {ProjectImportStatus.IMPORTED, ProjectImportStatus.IMPORT_FAILED}
        ),
        ProjectImportStatus.EXTRACTION_FAILED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.VALIDATION_FAILED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.IMPORT_FAILED: frozenset(
            {ProjectImportStatus.IMPORTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.IMPORTED: frozenset(),
        ProjectImportStatus.CANCELLED: frozenset(),
    }
)


def ensure_project_import_transition(
    current: ProjectImportStatus,
    target: ProjectImportStatus,
) -> None:
    if target not in PROJECT_IMPORT_STATUS_TRANSITIONS[current]:
        raise ValueError(f"project import cannot transition from {current.value} to {target.value}")


class SourceType(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    FILE = "file"
    SPREADSHEET = "spreadsheet"
    EXTERNAL = "external"


class DependencyType(StrEnum):
    FINISH_TO_START = "finish_to_start"


class DraftTaskStatus(StrEnum):
    PROPOSED = "proposed"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class SourceReference(DomainModel):
    """Provenance for one extracted fact."""

    model_config = {"strict": True}

    source_id: CanonicalId
    source_type: SourceType
    source_name: StrictText = Field(max_length=500)
    section: StrictText | None = Field(default=None, max_length=500)
    external_reference: StrictText | None = Field(default=None, max_length=1_000)
    imported_at: AwareDatetime = Field(default_factory=utc_now)


class ProjectDraft(DomainModel):
    model_config = {"strict": True}

    name: StrictText = Field(max_length=200)
    description: StrictText | None = Field(default=None, max_length=5_000)
    type: StrictText | None = Field(default=None, max_length=200)
    location: StrictText | None = Field(default=None, max_length=500)
    start_date: date | None = None
    target_end_date: date | None = None
    status: ProjectStatus = ProjectStatus.PLANNING

    @model_validator(mode="after")
    def validate_dates(self) -> ProjectDraft:
        if self.start_date and self.target_end_date and self.target_end_date < self.start_date:
            raise ValueError("target_end_date cannot be before start_date")
        return self


class PhaseDraft(DomainModel):
    model_config = {"strict": True}

    temp_id: DraftTempId
    name: StrictText = Field(max_length=300)
    sequence: int = Field(ge=1)
    description: StrictText | None = Field(default=None, max_length=5_000)


class TaskDraft(DomainModel):
    model_config = {"strict": True}

    temp_id: DraftTempId
    name: StrictText = Field(max_length=300)
    description: StrictText | None = Field(default=None, max_length=10_000)
    phase_temp_id: DraftTempId | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_completion: date | None = None
    duration: Decimal | None = Field(default=None, ge=0)
    initial_status: DraftTaskStatus = DraftTaskStatus.PROPOSED
    location: StrictText | None = Field(default=None, max_length=500)
    trade: StrictText | None = Field(default=None, max_length=200)
    assignee_reference: StrictText | None = Field(default=None, max_length=300)
    source_reference: SourceReference | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> TaskDraft:
        if self.planned_start and self.planned_finish and self.planned_finish < self.planned_start:
            raise ValueError("planned_finish cannot be before planned_start")
        if (
            self.actual_completion
            and self.planned_start
            and self.actual_completion < self.planned_start
        ):
            raise ValueError("actual_completion cannot be before planned_start")
        return self


class DependencyDraft(DomainModel):
    model_config = {"strict": True}

    predecessor_temp_id: DraftTempId
    successor_temp_id: DraftTempId
    type: DependencyType = DependencyType.FINISH_TO_START
    source_reference: SourceReference | None = None


class MaterialDraft(DomainModel):
    model_config = {"strict": True}

    temp_id: DraftTempId
    name: StrictText = Field(max_length=300)
    canonical_unit: StrictText = Field(max_length=100)
    initial_on_hand_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    location: StrictText | None = Field(default=None, max_length=500)
    source_reference: SourceReference | None = None

    @field_validator("canonical_unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        canonical = canonicalize_unit(value)
        if canonical != value:
            raise ValueError("canonical_unit must already be canonical")
        return value


class ExtractedMaterialDraft(DomainModel):
    """Material shape accepted from the schema-constrained extraction boundary.

    Units are intentionally not canonical here: deterministic normalization owns
    alias resolution before a value can enter ``MaterialDraft``.
    """

    model_config = {"strict": True}

    temp_id: DraftTempId
    name: StrictText = Field(max_length=300)
    canonical_unit: StrictText = Field(max_length=100)
    initial_on_hand_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    location: StrictText | None = Field(default=None, max_length=500)
    source_reference: SourceReference | None = None


class MaterialRequirementDraft(DomainModel):
    model_config = {"strict": True}

    task_temp_id: DraftTempId
    material_temp_id: DraftTempId
    required_quantity: Decimal = Field(ge=Decimal("0.001"))
    unit: StrictText = Field(max_length=100)
    required_by: date | None = None
    source_reference: SourceReference | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        canonical = canonicalize_unit(value)
        if canonical != value:
            raise ValueError("requirement unit must already be canonical")
        return value


class ExtractedMaterialRequirementDraft(DomainModel):
    """Material requirement shape before deterministic unit normalization."""

    model_config = {"strict": True}

    task_temp_id: DraftTempId
    material_temp_id: DraftTempId
    required_quantity: Decimal = Field(ge=Decimal("0.001"))
    unit: StrictText = Field(max_length=100)
    required_by: date | None = None
    source_reference: SourceReference | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)


class MilestoneDraft(DomainModel):
    model_config = {"strict": True}

    temp_id: DraftTempId
    name: StrictText = Field(max_length=300)
    planned_date: date | None = None
    source_reference: SourceReference | None = None


class ImportWarning(DomainModel):
    model_config = {"strict": True}

    code: StrictText = Field(max_length=100)
    message: StrictText = Field(max_length=2_000)
    field: StrictText | None = Field(default=None, max_length=200)
    source_reference: SourceReference | None = None


class ImportConflict(DomainModel):
    model_config = {"strict": True}

    code: StrictText = Field(max_length=100)
    message: StrictText = Field(max_length=2_000)
    entity_temp_id: DraftTempId | None = None
    existing_reference: StrictText | None = Field(default=None, max_length=500)
    source_reference: SourceReference | None = None


class ProjectImportDraft(DomainModel):
    """Complete extraction result awaiting deterministic validation/review."""

    model_config = {"strict": True}

    schema_version: Literal[1] = 1
    id: CanonicalId
    project_id: CanonicalId
    source_id: CanonicalId
    status: ProjectImportStatus = ProjectImportStatus.DRAFT
    project: ProjectDraft
    phases: list[PhaseDraft] = Field(default_factory=list, max_length=100)
    tasks: list[TaskDraft] = Field(default_factory=list, max_length=300)
    dependencies: list[DependencyDraft] = Field(default_factory=list, max_length=900)
    materials: list[MaterialDraft] = Field(default_factory=list, max_length=200)
    material_requirements: list[MaterialRequirementDraft] = Field(
        default_factory=list, max_length=600
    )
    milestones: list[MilestoneDraft] = Field(default_factory=list, max_length=100)
    warnings: list[ImportWarning] = Field(default_factory=list, max_length=200)
    conflicts: list[ImportConflict] = Field(default_factory=list, max_length=200)
    unresolved_references: list[StrictText] = Field(default_factory=list, max_length=200)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    reviewed_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None


__all__ = [
    "PROJECT_IMPORT_STATUS_TRANSITIONS",
    "DependencyDraft",
    "DependencyType",
    "DraftTaskStatus",
    "ExtractedMaterialDraft",
    "ExtractedMaterialRequirementDraft",
    "ImportConflict",
    "ImportWarning",
    "MaterialDraft",
    "MaterialRequirementDraft",
    "MilestoneDraft",
    "PhaseDraft",
    "ProjectDraft",
    "ProjectImportDraft",
    "ProjectImportStatus",
    "SourceReference",
    "SourceType",
    "TaskDraft",
    "ensure_project_import_transition",
]
