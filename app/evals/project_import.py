"""Release evaluation for the live project-import extraction boundary."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.agents.project_import_extraction import ProjectImportCandidate
from app.agents.project_import_registry import PROJECT_IMPORT_RUNTIME


class ProjectImportEvalExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name_contains: str | None = None
    task_name_contains: str | None = None
    material_name_contains: str | None = None
    required_quantity: Decimal | None = None
    required_unit: str | None = None
    require_unresolved_warning: bool = False
    require_task_dates_absent: bool = False
    forbid_material_requirements: bool = False


class ProjectImportEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    source: str
    expected: ProjectImportEvalExpectation


class ProjectImportEvalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    prompt_registry_key: str
    cases: list[ProjectImportEvalCase] = Field(min_length=1)


class ProjectImportAssertionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    detail: str


class ProjectImportEvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    passed: bool
    assertions: list[ProjectImportAssertionResult]


class ProjectImportEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    prompt_registry_key: str
    model_registry_key: str
    model_id: str
    commit_sha: str
    generated_at: datetime
    passed: bool
    cases: list[ProjectImportEvalCaseResult]


class ProjectImportEvalExtractor(Protocol):
    async def extract(self, source_text: str) -> ProjectImportCandidate: ...


def load_project_import_dataset(path: str | Path) -> ProjectImportEvalDataset:
    dataset = ProjectImportEvalDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if dataset.prompt_registry_key != PROJECT_IMPORT_RUNTIME.prompt_key:
        raise ValueError("evaluation prompt key does not match the runtime registry")
    return dataset


async def run_project_import_evaluation(
    dataset: ProjectImportEvalDataset,
    extractor: ProjectImportEvalExtractor,
    *,
    model_id: str,
) -> ProjectImportEvalReport:
    cases: list[ProjectImportEvalCaseResult] = []
    for case in dataset.cases:
        try:
            candidate = await extractor.extract(case.source)
        except Exception as exc:
            cases.append(
                ProjectImportEvalCaseResult(
                    id=case.id,
                    category=case.category,
                    passed=False,
                    assertions=[
                        ProjectImportAssertionResult(
                            name="extraction_succeeded",
                            passed=False,
                            detail=f"live extraction failed with {_safe_error_code(exc)}",
                        )
                    ],
                )
            )
            continue
        cases.append(evaluate_project_import_candidate(case, candidate))
    return ProjectImportEvalReport(
        dataset_version=dataset.version,
        prompt_registry_key=dataset.prompt_registry_key,
        model_registry_key=PROJECT_IMPORT_RUNTIME.model_key,
        model_id=model_id,
        commit_sha=_commit_sha(),
        generated_at=datetime.now(UTC),
        passed=all(case.passed for case in cases),
        cases=cases,
    )


def evaluate_project_import_candidate(
    case: ProjectImportEvalCase,
    candidate: ProjectImportCandidate,
) -> ProjectImportEvalCaseResult:
    expected = case.expected
    assertions: list[ProjectImportAssertionResult] = []

    def check(name: str, passed: bool, detail: str) -> None:
        assertions.append(ProjectImportAssertionResult(name=name, passed=passed, detail=detail))

    check(
        "draft_identity_boundary",
        _uses_only_temporary_identity(candidate),
        "all model-owned identity fields must remain temporary draft references",
    )

    if expected.project_name_contains is not None:
        check(
            "project_name",
            _contains(candidate.project.name, expected.project_name_contains),
            f"project name must contain {expected.project_name_contains!r}",
        )

    matched_task = next(
        (
            task
            for task in candidate.tasks
            if expected.task_name_contains is not None
            and _contains(task.name, expected.task_name_contains)
        ),
        None,
    )
    if expected.task_name_contains is not None:
        check(
            "task_name",
            matched_task is not None,
            f"one task name must contain {expected.task_name_contains!r}",
        )

    matched_material = next(
        (
            material
            for material in candidate.materials
            if expected.material_name_contains is not None
            and _contains(material.name, expected.material_name_contains)
        ),
        None,
    )
    if expected.material_name_contains is not None:
        check(
            "material_name",
            matched_material is not None,
            f"one material name must contain {expected.material_name_contains!r}",
        )

    if expected.required_quantity is not None or expected.required_unit is not None:
        requirement = next(
            (
                item
                for item in candidate.material_requirements
                if (matched_task is None or item.task_temp_id == matched_task.temp_id)
                and (matched_material is None or item.material_temp_id == matched_material.temp_id)
            ),
            None,
        )
        check(
            "material_requirement_link",
            requirement is not None and matched_task is not None and matched_material is not None,
            "the requirement must link the matched draft task and material",
        )
        if expected.required_quantity is not None:
            check(
                "required_quantity",
                requirement is not None
                and requirement.required_quantity == expected.required_quantity,
                f"required quantity must equal {expected.required_quantity}",
            )
        if expected.required_unit is not None:
            check(
                "required_unit",
                requirement is not None
                and requirement.unit.casefold() == expected.required_unit.casefold(),
                f"required unit must equal {expected.required_unit!r}",
            )

    if expected.require_unresolved_warning:
        check(
            "unresolved_warning",
            bool(candidate.warnings or candidate.unresolved_references),
            "ambiguous or incomplete evidence must remain explicitly unresolved",
        )

    if expected.require_task_dates_absent:
        check(
            "task_dates_absent",
            matched_task is not None
            and matched_task.planned_start is None
            and matched_task.planned_finish is None,
            "an incomplete date must not become a planned start or finish",
        )

    if expected.forbid_material_requirements:
        check(
            "ambiguous_requirement_absent",
            not candidate.material_requirements,
            "ambiguous quantities must not become material requirements",
        )

    return ProjectImportEvalCaseResult(
        id=case.id,
        category=case.category,
        passed=all(assertion.passed for assertion in assertions),
        assertions=assertions,
    )


def _contains(value: str, expected: str) -> bool:
    return expected.casefold() in value.casefold()


def _uses_only_temporary_identity(candidate: ProjectImportCandidate) -> bool:
    identifiers = (
        [phase.temp_id for phase in candidate.phases]
        + [task.temp_id for task in candidate.tasks]
        + [material.temp_id for material in candidate.materials]
        + [milestone.temp_id for milestone in candidate.milestones]
        + [dependency.predecessor_temp_id for dependency in candidate.dependencies]
        + [dependency.successor_temp_id for dependency in candidate.dependencies]
        + [item.task_temp_id for item in candidate.material_requirements]
        + [item.material_temp_id for item in candidate.material_requirements]
    )
    return all(identifier.startswith("tmp_") for identifier in identifiers)


def _commit_sha() -> str:
    configured = os.getenv("GITHUB_SHA") or os.getenv("COMMIT_SHA")
    if configured:
        return configured[:40]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()[:40]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _safe_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code[:128]
    return type(error).__name__[:128]


__all__ = [
    "ProjectImportAssertionResult",
    "ProjectImportEvalCase",
    "ProjectImportEvalCaseResult",
    "ProjectImportEvalDataset",
    "ProjectImportEvalExpectation",
    "ProjectImportEvalReport",
    "evaluate_project_import_candidate",
    "load_project_import_dataset",
    "run_project_import_evaluation",
]
