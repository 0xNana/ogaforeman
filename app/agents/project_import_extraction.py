"""Native ADK workflow for extracting a project import draft."""

from __future__ import annotations

import json
from typing import Any, Protocol

from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.workflow import FunctionNode, START, Workflow
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from app.services.project_import_validation import (
    ProjectImportValidationResult,
    ProjectImportValidator,
)


class ProjectImportExtractor(Protocol):
    async def extract(self, source_text: str) -> "ProjectImportCandidate": ...


class ProjectImportCandidate(BaseModel):
    """Schema-constrained Gemini output with no canonical IDs."""

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


class GeminiProjectImportExtractor:
    """Gemini schema-constrained extraction boundary for project sources."""

    def __init__(self, settings: Settings) -> None:
        from app.infrastructure.gemini import create_gemini_client

        if not settings.gemini_model_id:
            raise RuntimeError("Live Gemini requires GEMINI_MODEL_ID")
        self._client = create_gemini_client(settings)
        self._model_name = settings.gemini_model_id

    async def extract(self, source_text: str) -> ProjectImportCandidate:
        from google.genai import types

        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=(
                "Extract a construction project plan into the supplied schema. "
                "Identify tasks, phases, dependencies, materials, quantities, units, "
                "dates, and requirements from the source. Use only draft temp IDs "
                "matching tmp_...; never output Firestore IDs, canonical entity IDs, "
                "approval authority, or mutation tokens. Do not invent missing date "
                "months or years; add unresolved references instead.\n\n"
                f"<project_source>\n{source_text}\n</project_source>"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ProjectImportCandidate,
                temperature=0.0,
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty project import extraction")
        return ProjectImportCandidate.model_validate_json(response.text)


class ProjectImportExtractionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = "created"
    stage_history: list[str] = Field(default_factory=list)
    source_text: str = Field(max_length=800_000)
    candidate: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    validation_warnings: list[dict[str, Any]] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    needs_review: bool = False


def build_project_import_workflow(
    *,
    source_text: str,
    project_id: str,
    import_id: str,
    source_id: str,
    extractor: ProjectImportExtractor,
    validator: ProjectImportValidator | None = None,
    timeout_seconds: int = 45,
) -> Workflow:
    """Build the native extraction graph; no custom scheduler is involved."""

    deterministic_validator = validator or ProjectImportValidator()
    normalizer = ProjectImportNormalizer()

    async def source_received(ctx: Context) -> dict[str, str]:
        # Persist the source payload in ADK state so a rebuilt Runner can
        # continue from the durable session without relying on process memory.
        ctx.state["source_text"] = source_text
        ctx.state["stage"] = "source_received"
        ctx.state["stage_history"] = ["source_received"]
        return {"stage": "source_received"}

    async def load_source(ctx: Context) -> dict[str, str]:
        loaded_source = str(ctx.state.get("source_text", source_text))
        ctx.state["stage"] = "load_source"
        history = list(ctx.state.get("stage_history", []))
        history.append("load_source")
        ctx.state["stage_history"] = history
        return {"stage": "load_source", "characters": str(len(loaded_source))}

    async def extract_candidate(ctx: Context) -> dict[str, str]:
        loaded_source = str(ctx.state.get("source_text", source_text))
        candidate = await extractor.extract(loaded_source)
        ctx.state["candidate"] = candidate.model_dump(mode="json")
        ctx.state["stage"] = "gemini_extraction"
        history = list(ctx.state.get("stage_history", []))
        history.append("gemini_extraction")
        ctx.state["stage_history"] = history
        return {"stage": "gemini_extraction"}

    async def validate_schema(ctx: Context) -> dict[str, str]:
        candidate = _candidate_from_state(ctx.state["candidate"])
        ctx.state["candidate"] = candidate.model_dump(mode="json")
        ctx.state["stage"] = "schema_validated"
        history = list(ctx.state.get("stage_history", []))
        history.append("schema_validation")
        ctx.state["stage_history"] = history
        return {"stage": "schema_validated"}

    async def normalize_draft(ctx: Context) -> dict[str, str]:
        candidate = _candidate_from_state(ctx.state["candidate"])
        normalized = normalizer.normalize(candidate, source_id=source_id)
        draft = ProjectImportDraft(
            schema_version=1,
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
        ctx.state["draft"] = draft.model_dump(mode="json")
        ctx.state["stage"] = "draft_normalized"
        history = list(ctx.state.get("stage_history", []))
        history.append("normalize_draft")
        ctx.state["stage_history"] = history
        return {"stage": "draft_normalized"}

    async def deterministic_validate(ctx: Context) -> dict[str, str]:
        draft = _draft_from_state(ctx.state["draft"])
        result: ProjectImportValidationResult = deterministic_validator.validate(draft)
        ctx.state["validation_warnings"] = [
            item.model_dump(mode="json") for item in result.warnings
        ]
        ctx.state["validation_errors"] = [item.model_dump(mode="json") for item in result.errors]
        ctx.state["needs_review"] = bool(result.warnings or result.errors or draft.conflicts)
        ctx.state["stage"] = "deterministically_validated"
        history = list(ctx.state.get("stage_history", []))
        history.append("deterministic_validation")
        ctx.state["stage_history"] = history
        return {
            "stage": "deterministically_validated",
            "needs_review": str(ctx.state["needs_review"]),
        }

    async def needs_review(ctx: Context) -> dict[str, str]:
        ctx.state["stage"] = "needs_review"
        history = list(ctx.state.get("stage_history", []))
        history.append("needs_review")
        ctx.state["stage_history"] = history
        return {"stage": "needs_review"}

    nodes = [
        FunctionNode(func=source_received, name="source_received", timeout=timeout_seconds),
        FunctionNode(func=load_source, name="load_source", timeout=timeout_seconds),
        FunctionNode(func=extract_candidate, name="gemini_extraction", timeout=timeout_seconds),
        FunctionNode(func=validate_schema, name="schema_validation", timeout=timeout_seconds),
        FunctionNode(func=normalize_draft, name="normalize_draft", timeout=timeout_seconds),
        FunctionNode(
            func=deterministic_validate, name="deterministic_validation", timeout=timeout_seconds
        ),
        FunctionNode(func=needs_review, name="needs_review", timeout=timeout_seconds),
    ]
    return Workflow(
        name="project_import_extraction_workflow",
        state_schema=ProjectImportExtractionState,
        edges=[(START, *nodes)],
    )


def build_project_import_app(
    app_name: str,
    *,
    source_text: str,
    project_id: str,
    import_id: str,
    source_id: str,
    extractor: ProjectImportExtractor,
    timeout_seconds: int = 45,
) -> App:
    return App(
        name=app_name,
        root_agent=build_project_import_workflow(
            source_text=source_text,
            project_id=project_id,
            import_id=import_id,
            source_id=source_id,
            extractor=extractor,
            timeout_seconds=timeout_seconds,
        ),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


def _candidate_from_state(value: object) -> ProjectImportCandidate:
    if isinstance(value, str):
        return ProjectImportCandidate.model_validate_json(value)
    if isinstance(value, dict):
        return ProjectImportCandidate.model_validate_json(json.dumps(value))
    return ProjectImportCandidate.model_validate(value)


def _draft_from_state(value: object) -> ProjectImportDraft:
    if isinstance(value, str):
        return ProjectImportDraft.model_validate_json(value)
    if isinstance(value, dict):
        return ProjectImportDraft.model_validate_json(json.dumps(value))
    return ProjectImportDraft.model_validate(value)


__all__ = [
    "GeminiProjectImportExtractor",
    "ProjectImportCandidate",
    "ProjectImportExtractionState",
    "ProjectImportExtractor",
    "build_project_import_app",
    "build_project_import_workflow",
]
