"""Bounded Gemini extraction for project initialization sources."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from typing import Any, Literal, Protocol

from google.genai.errors import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config.settings import Settings
from app.domain.project_import import (
    DependencyDraft,
    ExtractedMaterialDraft,
    ExtractedMaterialRequirementDraft,
    ImportConflict,
    ImportWarning,
    MilestoneDraft,
    PhaseDraft,
    ProjectDraft,
    ProjectImportDraft,
    ProjectImportStatus,
    TaskDraft,
)
from app.services.project_import_normalization import ProjectImportNormalizer
from app.services.project_import_registry import PROJECT_IMPORT_EXTRACTION


class ProjectImportModelUnavailableError(RuntimeError):
    code = "DEPENDENCY_UNAVAILABLE"


class ProjectImportModelOutputInvalidError(ValueError):
    code = "PROJECT_IMPORT_MODEL_OUTPUT_INVALID"


class ProjectImportCandidate(BaseModel):
    """Schema-constrained Gemini output with draft-only identity."""

    model_config = ConfigDict(strict=True, extra="forbid")

    project: ProjectDraft
    phases: list[PhaseDraft] = Field(default_factory=list, max_length=100)
    tasks: list[TaskDraft] = Field(default_factory=list, max_length=300)
    dependencies: list[DependencyDraft] = Field(default_factory=list, max_length=900)
    materials: list[ExtractedMaterialDraft] = Field(default_factory=list, max_length=200)
    material_requirements: list[ExtractedMaterialRequirementDraft] = Field(
        default_factory=list, max_length=600
    )
    milestones: list[MilestoneDraft] = Field(default_factory=list, max_length=100)
    warnings: list[ImportWarning] = Field(default_factory=list, max_length=200)
    conflicts: list[ImportConflict] = Field(default_factory=list, max_length=200)
    unresolved_references: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def reject_canonical_source_references(self) -> "ProjectImportCandidate":
        references = (
            [task.source_reference for task in self.tasks]
            + [item.source_reference for item in self.dependencies]
            + [item.source_reference for item in self.materials]
            + [item.source_reference for item in self.material_requirements]
            + [item.source_reference for item in self.milestones]
            + [item.source_reference for item in self.warnings]
            + [item.source_reference for item in self.conflicts]
        )
        if any(
            reference is not None and not reference.source_id.startswith("tmp_")
            for reference in references
        ):
            raise ValueError("extraction source references must use draft temporary IDs")
        return self


class ProjectImportCandidateExtractor(Protocol):
    async def extract(self, source_text: str) -> ProjectImportCandidate: ...


class ProjectImportExtractionService:
    """Convert one source into a normalized draft without agent orchestration."""

    def __init__(
        self,
        extractor: ProjectImportCandidateExtractor,
        *,
        normalizer: ProjectImportNormalizer | None = None,
        timeout_seconds: float = 90,
    ) -> None:
        self._extractor = extractor
        self._normalizer = normalizer or ProjectImportNormalizer()
        self._timeout_seconds = timeout_seconds

    @property
    def model_id(self) -> str | None:
        value = getattr(self._extractor, "model_id", None)
        return value if isinstance(value, str) else None

    async def extract(
        self,
        *,
        project_id: str,
        import_id: str,
        source_id: str,
        source_text: str,
        schema_version: Literal[1] = 1,
    ) -> ProjectImportDraft:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                candidate = await self._extractor.extract(source_text)
        except TimeoutError:
            raise ProjectImportModelUnavailableError(
                "Gemini project import extraction timed out"
            ) from None
        normalized = self._normalizer.normalize(candidate, source_id=source_id)
        return ProjectImportDraft(
            schema_version=schema_version,
            id=import_id,
            project_id=project_id,
            source_id=source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            project=normalized.project,
            phases=normalized.phases,
            tasks=normalized.tasks,
            dependencies=normalized.dependencies,
            materials=normalized.materials,
            material_requirements=normalized.material_requirements,
            milestones=normalized.milestones,
            warnings=normalized.warnings,
            conflicts=normalized.conflicts,
            unresolved_references=normalized.unresolved_references,
        )


class GeminiProjectExtractor:
    """Direct Google Gen AI / Vertex schema-constrained candidate extractor."""

    def __init__(self, settings: Settings, *, prefer_vertex: bool = False) -> None:
        from app.infrastructure.gemini import create_gemini_client

        if not settings.gemini_model_id:
            raise RuntimeError("Live Gemini requires GEMINI_MODEL_ID")
        self._client = create_gemini_client(settings, prefer_vertex=prefer_vertex)
        self._model_name = settings.gemini_model_id

    @property
    def model_id(self) -> str:
        return self._model_name

    async def extract(self, source_text: str) -> ProjectImportCandidate:
        from google.genai import types

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=PROJECT_IMPORT_EXTRACTION.render_prompt(source_text),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=_gemini_candidate_schema(),
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    temperature=0.0,
                ),
            )
        except APIError:
            raise ProjectImportModelUnavailableError(
                "Gemini project import extraction is unavailable"
            ) from None
        if not response.text:
            raise ProjectImportModelOutputInvalidError(
                "Gemini returned an empty project import extraction"
            )
        try:
            payload = json.loads(response.text)
            return ProjectImportCandidate.model_validate_json(
                json.dumps(_discard_model_source_references(payload))
            )
        except (json.JSONDecodeError, ValidationError):
            raise ProjectImportModelOutputInvalidError(
                "Gemini returned an invalid project import extraction"
            ) from None


def _discard_model_source_references(payload: object) -> object:
    """Keep persisted source identity outside the untrusted model boundary."""

    if not isinstance(payload, dict):
        return payload
    sanitized = deepcopy(payload)
    for collection_name in (
        "tasks",
        "dependencies",
        "materials",
        "material_requirements",
        "milestones",
        "warnings",
        "conflicts",
    ):
        records = sanitized.get(collection_name)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                record.pop("source_reference", None)
    return sanitized


def _gemini_candidate_schema() -> dict[str, Any]:
    """Remove generation hints unsupported by the Vertex schema dialect."""

    unsupported = {
        "additionalProperties",
        "format",
        "maxItems",
        "maxLength",
        "maximum",
        "minLength",
        "minimum",
        "pattern",
    }
    schema = deepcopy(ProjectImportCandidate.model_json_schema())

    def clean(value: object) -> None:
        if isinstance(value, dict):
            for key in unsupported:
                value.pop(key, None)
            for child in value.values():
                clean(child)
        elif isinstance(value, list):
            for child in value:
                clean(child)

    clean(schema)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)
    return schema


__all__ = [
    "GeminiProjectExtractor",
    "ProjectImportCandidate",
    "ProjectImportCandidateExtractor",
    "ProjectImportExtractionService",
    "ProjectImportModelOutputInvalidError",
    "ProjectImportModelUnavailableError",
]
