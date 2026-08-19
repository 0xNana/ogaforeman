"""Deterministic normalization between extraction and import validation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, cast

from pydantic import BaseModel

from app.domain.materials import canonicalize_unit
from app.domain.project_import import (
    DependencyDraft,
    ExtractedMaterialDraft,
    ExtractedMaterialRequirementDraft,
    ImportConflict,
    ImportWarning,
    MaterialDraft,
    MaterialRequirementDraft,
    MilestoneDraft,
    PhaseDraft,
    ProjectDraft,
    TaskDraft,
)


def normalize_task_name_for_match(value: str) -> str:
    """Return a conservative comparison key without changing the display name.

    This intentionally handles only Unicode/case/spacing/punctuation variation.
    It does not reorder words, expand abbreviations, stem terms, or apply trade
    synonyms, so semantically distinct construction activities remain distinct.
    """

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise ValueError("task name cannot be empty")
    return normalized


class ProjectImportExtractionCandidate(Protocol):
    project: ProjectDraft
    phases: list[PhaseDraft]
    tasks: list[TaskDraft]
    dependencies: list[DependencyDraft]
    materials: list[ExtractedMaterialDraft]
    material_requirements: list[ExtractedMaterialRequirementDraft]
    milestones: list[MilestoneDraft]
    warnings: list[ImportWarning]
    conflicts: list[ImportConflict]
    unresolved_references: list[str]


@dataclass(frozen=True, slots=True)
class NormalizedProjectImportCandidate:
    project: ProjectDraft
    phases: list[PhaseDraft]
    tasks: list[TaskDraft]
    dependencies: list[DependencyDraft]
    materials: list[MaterialDraft]
    material_requirements: list[MaterialRequirementDraft]
    milestones: list[MilestoneDraft]
    warnings: list[ImportWarning]
    conflicts: list[ImportConflict]
    unresolved_references: list[str]


class ProjectImportNormalizer:
    """Normalize only known, deterministic extraction variants."""

    def normalize(
        self,
        candidate: ProjectImportExtractionCandidate,
        *,
        source_id: str | None = None,
    ) -> NormalizedProjectImportCandidate:
        return NormalizedProjectImportCandidate(
            project=candidate.project,
            phases=candidate.phases,
            tasks=[
                cast(TaskDraft, self._bind_model_source_reference(item, source_id))
                for item in candidate.tasks
            ],
            dependencies=[
                cast(DependencyDraft, self._bind_model_source_reference(item, source_id))
                for item in candidate.dependencies
            ],
            materials=[self._normalize_material(item, source_id) for item in candidate.materials],
            material_requirements=[
                self._normalize_requirement(item, source_id)
                for item in candidate.material_requirements
            ],
            milestones=[
                cast(MilestoneDraft, self._bind_model_source_reference(item, source_id))
                for item in candidate.milestones
            ],
            warnings=[
                cast(ImportWarning, self._bind_model_source_reference(item, source_id))
                for item in candidate.warnings
            ],
            conflicts=[
                cast(ImportConflict, self._bind_model_source_reference(item, source_id))
                for item in candidate.conflicts
            ],
            unresolved_references=candidate.unresolved_references,
        )

    @staticmethod
    def _normalize_material(item: ExtractedMaterialDraft, source_id: str | None) -> MaterialDraft:
        return MaterialDraft.model_validate(
            ProjectImportNormalizer._bind_mapping_source_reference(
                {
                    **item.model_dump(),
                    "canonical_unit": canonicalize_unit(item.canonical_unit),
                },
                source_id,
            )
        )

    @staticmethod
    def _normalize_requirement(
        item: ExtractedMaterialRequirementDraft,
        source_id: str | None,
    ) -> MaterialRequirementDraft:
        return MaterialRequirementDraft.model_validate(
            ProjectImportNormalizer._bind_mapping_source_reference(
                {**item.model_dump(), "unit": canonicalize_unit(item.unit)}, source_id
            )
        )

    @staticmethod
    def _bind_model_source_reference(item: BaseModel, source_id: str | None) -> BaseModel:
        if source_id is None:
            return item
        data = item.model_dump()
        return type(item).model_validate(
            ProjectImportNormalizer._bind_mapping_source_reference(data, source_id)
        )

    @staticmethod
    def _bind_mapping_source_reference(
        data: dict[str, object], source_id: str | None
    ) -> dict[str, object]:
        if source_id is None:
            return data
        reference = data.get("source_reference")
        if reference is not None:
            reference = dict(cast(dict[str, object], reference))
            reference["source_id"] = source_id
            data["source_reference"] = reference
        return data


__all__ = [
    "NormalizedProjectImportCandidate",
    "ProjectImportNormalizer",
    "normalize_task_name_for_match",
]
