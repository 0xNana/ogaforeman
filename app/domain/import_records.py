"""Canonical records created by a confirmed project import."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from pydantic import AwareDatetime, Field

from .models import CanonicalId, DomainModel, IdempotencyKey, utc_now
from .project_import import ProjectImportDraft, ProjectImportStatus, SourceType


class ProjectSourceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ImportProvenanceTargetType(StrEnum):
    PROJECT_PHASE = "project_phase"
    TASK = "task"
    DEPENDENCY = "dependency"
    MATERIAL = "material"
    MATERIAL_LEDGER_ENTRY = "material_ledger_entry"
    MATERIAL_REQUIREMENT = "material_requirement"


def import_provenance_id(
    target_entity_type: ImportProvenanceTargetType,
    target_entity_id: str,
) -> str:
    digest = sha256(f"{target_entity_type.value}:|:{target_entity_id}".encode()).hexdigest()[:32]
    return f"prv_{digest}"


def import_dependency_target_id(
    predecessor_task_id: str,
    successor_task_id: str,
) -> str:
    digest = sha256(f"{predecessor_task_id}:|:{successor_task_id}".encode()).hexdigest()[:32]
    return f"dep_{digest}"


class ProjectImportRecord(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    source_id: CanonicalId
    status: ProjectImportStatus
    draft: ProjectImportDraft | None = None
    reviewed_at: AwareDatetime | None = None
    confirmed_at: AwareDatetime | None = None
    cancelled_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    extraction_idempotency_key: IdempotencyKey | None = None
    extraction_request_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    extraction_session_id: CanonicalId | None = None
    extraction_invocation_id: IdempotencyKey | None = None
    extraction_lease_until: AwareDatetime | None = None
    extraction_attempt: int = Field(default=0, ge=0)
    import_attempt: int = Field(default=0, ge=0)
    decision_action: str | None = Field(default=None, pattern=r"^[a-z_]+$")
    decision_idempotency_key: IdempotencyKey | None = None
    decision_request_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision_expected_version: int | None = Field(default=None, ge=0)
    failure_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    failure_message: str | None = Field(default=None, max_length=500)
    telemetry_trace_id: str | None = Field(default=None, min_length=4, max_length=128)
    prompt_registry_key: str | None = Field(default=None, pattern=r"^[a-z0-9_.-]+$", max_length=128)
    model_registry_key: str | None = Field(default=None, pattern=r"^[a-z0-9_.-]+$", max_length=128)
    diagnostic_stage: str | None = Field(default=None, pattern=r"^[a-z_]+$", max_length=64)
    diagnostic_attempt: int = Field(default=0, ge=0)
    validation_outcome: str | None = Field(default=None, pattern=r"^(succeeded|blocked|failed)$")
    commit_outcome: str | None = Field(default=None, pattern=r"^(succeeded|failed|running)$")
    phase_count: int = Field(default=0, ge=0)
    task_count: int = Field(default=0, ge=0)
    material_count: int = Field(default=0, ge=0)
    requirement_count: int = Field(default=0, ge=0)
    version: int = Field(default=0, ge=0)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)


class ProjectSource(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    type: SourceType
    name: str = Field(min_length=1, max_length=500)
    checksum: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    storage_reference: str | None = Field(default=None, max_length=2_000)
    content_text: str | None = Field(default=None, max_length=800_000)
    created_by: CanonicalId
    status: ProjectSourceStatus = ProjectSourceStatus.ACTIVE
    created_at: AwareDatetime = Field(default_factory=utc_now)
    version: int = Field(default=0, ge=0)

    @classmethod
    def from_text(
        cls,
        *,
        id: CanonicalId,
        project_id: CanonicalId,
        source_type: SourceType,
        name: str,
        text: str,
        created_by: CanonicalId,
    ) -> "ProjectSource":
        from hashlib import sha256

        if not text.strip():
            raise ValueError("source text cannot be empty")
        if len(text) > 800_000 or len(text.encode("utf-8")) > 800_000:
            raise ValueError("source text exceeds the inline Firestore limit")
        return cls(
            id=id,
            project_id=project_id,
            type=source_type,
            name=name,
            checksum=sha256(text.encode("utf-8")).hexdigest(),
            content_text=text,
            created_by=created_by,
        )


class ProjectPhase(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    import_id: CanonicalId
    name: str = Field(min_length=1, max_length=300)
    sequence: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=5_000)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class MaterialRequirement(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    import_id: CanonicalId
    task_id: CanonicalId
    material_id: CanonicalId
    required_quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=100)
    required_by: date | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    source_provenance_id: CanonicalId | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)


class ImportProvenance(DomainModel):
    id: CanonicalId
    project_id: CanonicalId
    import_id: CanonicalId
    source_id: CanonicalId
    source_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_type: SourceType
    source_name: str = Field(min_length=1, max_length=500)
    target_entity_type: ImportProvenanceTargetType
    target_entity_id: CanonicalId
    section: str | None = Field(default=None, max_length=500)
    external_reference: str | None = Field(default=None, max_length=1_000)
    imported_by: CanonicalId
    imported_at: AwareDatetime
    idempotency_key: IdempotencyKey


__all__ = [
    "ImportProvenance",
    "ImportProvenanceTargetType",
    "MaterialRequirement",
    "ProjectSource",
    "ProjectSourceStatus",
    "ProjectImportRecord",
    "ProjectPhase",
    "import_dependency_target_id",
    "import_provenance_id",
]
