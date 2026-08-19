"""Deterministic validation for project initialization drafts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.materials import MaterialUnitMismatchError, ensure_same_unit
from app.domain.project_import import (
    DraftTaskStatus,
    ImportConflict,
    ImportWarning,
    MaterialDraft,
    ProjectImportDraft,
    TaskDraft,
)
from app.services.project_import_normalization import normalize_task_name_for_match
from app.services.project_import_plan import (
    DEFAULT_PROJECT_IMPORT_SAFETY_LIMITS,
    PreparedProjectImportPlan,
    ProjectImportSafetyLimits,
    prepare_project_import_plan,
)


@dataclass(frozen=True, slots=True)
class ProjectImportValidationResult:
    draft: ProjectImportDraft
    plan: PreparedProjectImportPlan
    warnings: tuple[ImportWarning, ...] = ()
    errors: tuple[ImportConflict, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


class ProjectImportValidationError(ValueError):
    """Raised before a draft can reach a canonical repository write."""

    code = "PROJECT_IMPORT_VALIDATION_FAILED"

    def __init__(self, errors: tuple[ImportConflict, ...]) -> None:
        self.errors = errors
        super().__init__("project import draft failed deterministic validation")


class ProjectImportValidator:
    """Validate a complete draft without Gemini, repositories, or side effects."""

    def __init__(
        self,
        *,
        limits: ProjectImportSafetyLimits = DEFAULT_PROJECT_IMPORT_SAFETY_LIMITS,
    ) -> None:
        self._limits = limits

    def validate(self, draft: ProjectImportDraft) -> ProjectImportValidationResult:
        errors = list(draft.conflicts)
        warnings = list(draft.warnings)
        tasks = {task.temp_id: task for task in draft.tasks}
        materials = {material.temp_id: material for material in draft.materials}

        self._validate_unique_ids(draft, errors)
        self._validate_phase_references(draft, errors)
        self._validate_duplicate_task_names(draft, errors)
        self._validate_task_completion_dates(draft, errors)
        self._validate_milestones(draft, errors)
        self._validate_dependencies(draft, tasks, errors)
        self._validate_material_requirements(draft, tasks, materials, errors)
        self._collect_unresolved_reference_warnings(draft, warnings)

        warnings = _deduplicate_warnings(warnings)
        errors = _deduplicate_conflicts(errors)
        validated_draft = draft.model_copy(
            update={
                "warnings": warnings,
                "conflicts": errors,
            }
        )
        plan = prepare_project_import_plan(validated_draft, limits=self._limits)
        self._validate_plan_safety(plan, errors)
        errors = _deduplicate_conflicts(errors)
        validated_draft = validated_draft.model_copy(update={"conflicts": errors})
        plan = prepare_project_import_plan(validated_draft, limits=self._limits)

        return ProjectImportValidationResult(
            draft=validated_draft,
            plan=plan,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def validate_or_raise(self, draft: ProjectImportDraft) -> ProjectImportValidationResult:
        result = self.validate(draft)
        if not result.is_valid:
            raise ProjectImportValidationError(result.errors)
        return result

    @staticmethod
    def _validate_unique_ids(
        draft: ProjectImportDraft,
        errors: list[ImportConflict],
    ) -> None:
        for label, values in (
            ("phase", [item.temp_id for item in draft.phases]),
            ("task", [item.temp_id for item in draft.tasks]),
            ("material", [item.temp_id for item in draft.materials]),
        ):
            seen: set[str] = set()
            for value in values:
                if value in seen:
                    errors.append(
                        ImportConflict(
                            code="DUPLICATE_TEMP_ID",
                            message=f"duplicate {label} temp_id: {value}",
                            entity_temp_id=value,
                        )
                    )
                seen.add(value)

    @staticmethod
    def _validate_phase_references(
        draft: ProjectImportDraft,
        errors: list[ImportConflict],
    ) -> None:
        phase_ids = {phase.temp_id for phase in draft.phases}
        for task in draft.tasks:
            if task.phase_temp_id is not None and task.phase_temp_id not in phase_ids:
                errors.append(
                    ImportConflict(
                        code="UNKNOWN_TASK_PHASE",
                        message=f"task phase does not exist: {task.phase_temp_id}",
                        entity_temp_id=task.temp_id,
                        source_reference=task.source_reference,
                    )
                )

    @staticmethod
    def _validate_duplicate_task_names(
        draft: ProjectImportDraft,
        errors: list[ImportConflict],
    ) -> None:
        seen: dict[str, str] = {}
        for task in draft.tasks:
            key = normalize_task_name_for_match(task.name)
            original = seen.get(key)
            if original is not None:
                errors.append(
                    ImportConflict(
                        code="DUPLICATE_TASK_NAME",
                        message=(
                            f"task name is equivalent after conservative normalization: {task.name}"
                        ),
                        entity_temp_id=task.temp_id,
                        source_reference=task.source_reference,
                    )
                )
            else:
                seen[key] = task.temp_id

    @staticmethod
    def _validate_task_completion_dates(
        draft: ProjectImportDraft,
        errors: list[ImportConflict],
    ) -> None:
        for task in draft.tasks:
            if task.initial_status is DraftTaskStatus.COMPLETED and task.actual_completion is None:
                errors.append(
                    ImportConflict(
                        code="COMPLETED_TASK_MISSING_DATE",
                        message="completed imported tasks require an explicit actual completion date",
                        entity_temp_id=task.temp_id,
                        source_reference=task.source_reference,
                    )
                )

    @staticmethod
    def _validate_milestones(
        draft: ProjectImportDraft,
        errors: list[ImportConflict],
    ) -> None:
        seen: set[str] = set()
        task_ids = {task.temp_id for task in draft.tasks}
        for milestone in draft.milestones:
            if milestone.temp_id in seen or milestone.temp_id in task_ids:
                errors.append(
                    ImportConflict(
                        code="DUPLICATE_MILESTONE_TEMP_ID",
                        message=f"milestone temp_id collides with another draft entity: {milestone.temp_id}",
                        entity_temp_id=milestone.temp_id,
                        source_reference=milestone.source_reference,
                    )
                )
            if milestone.planned_date is None:
                errors.append(
                    ImportConflict(
                        code="MILESTONE_MISSING_DATE",
                        message="milestones require an explicit planned date",
                        entity_temp_id=milestone.temp_id,
                        source_reference=milestone.source_reference,
                    )
                )
            seen.add(milestone.temp_id)

    @staticmethod
    def _validate_dependencies(
        draft: ProjectImportDraft,
        tasks: Mapping[str, TaskDraft],
        errors: list[ImportConflict],
    ) -> None:
        edges: set[tuple[str, str, str]] = set()
        graph: dict[str, set[str]] = {task_id: set() for task_id in tasks}
        for dependency in draft.dependencies:
            predecessor = dependency.predecessor_temp_id
            successor = dependency.successor_temp_id
            edge = (predecessor, successor, dependency.type.value)
            if edge in edges:
                errors.append(
                    ImportConflict(
                        code="DUPLICATE_DEPENDENCY",
                        message=f"duplicate dependency edge: {predecessor} -> {successor}",
                        entity_temp_id=successor,
                        source_reference=dependency.source_reference,
                    )
                )
            edges.add(edge)
            if predecessor not in tasks:
                errors.append(
                    ImportConflict(
                        code="UNKNOWN_PREDECESSOR",
                        message=f"dependency predecessor does not exist: {predecessor}",
                        entity_temp_id=successor,
                        source_reference=dependency.source_reference,
                    )
                )
            if successor not in tasks:
                errors.append(
                    ImportConflict(
                        code="UNKNOWN_SUCCESSOR",
                        message=f"dependency successor does not exist: {successor}",
                        entity_temp_id=predecessor,
                        source_reference=dependency.source_reference,
                    )
                )
            if predecessor == successor:
                errors.append(
                    ImportConflict(
                        code="SELF_DEPENDENCY",
                        message=f"task cannot depend on itself: {predecessor}",
                        entity_temp_id=predecessor,
                        source_reference=dependency.source_reference,
                    )
                )
                continue
            if predecessor in tasks and successor in tasks:
                graph[successor].add(predecessor)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                errors.append(
                    ImportConflict(
                        code="DEPENDENCY_CYCLE",
                        message=f"dependency cycle includes task: {task_id}",
                        entity_temp_id=task_id,
                    )
                )
                return
            if task_id in visited:
                return
            visiting.add(task_id)
            for predecessor in graph[task_id]:
                visit(predecessor)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)

    @staticmethod
    def _validate_material_requirements(
        draft: ProjectImportDraft,
        tasks: Mapping[str, TaskDraft],
        materials: Mapping[str, MaterialDraft],
        errors: list[ImportConflict],
    ) -> None:
        seen_pairs: set[tuple[str, str]] = set()
        for requirement in draft.material_requirements:
            pair = (requirement.task_temp_id, requirement.material_temp_id)
            if pair in seen_pairs:
                errors.append(
                    ImportConflict(
                        code="DUPLICATE_MATERIAL_REQUIREMENT",
                        message=(
                            "duplicate material requirement for task/material pair: "
                            f"{pair[0]} / {pair[1]}"
                        ),
                        entity_temp_id=requirement.task_temp_id,
                        source_reference=requirement.source_reference,
                    )
                )
            seen_pairs.add(pair)
            if requirement.task_temp_id not in tasks:
                errors.append(
                    ImportConflict(
                        code="UNKNOWN_REQUIREMENT_TASK",
                        message=f"material requirement task does not exist: {requirement.task_temp_id}",
                        entity_temp_id=requirement.task_temp_id,
                        source_reference=requirement.source_reference,
                    )
                )
            material = materials.get(requirement.material_temp_id)
            if material is None:
                errors.append(
                    ImportConflict(
                        code="UNKNOWN_REQUIREMENT_MATERIAL",
                        message=(
                            "material requirement material does not exist: "
                            f"{requirement.material_temp_id}"
                        ),
                        entity_temp_id=requirement.material_temp_id,
                        source_reference=requirement.source_reference,
                    )
                )
                continue
            try:
                ensure_same_unit(material.canonical_unit, requirement.unit)
            except MaterialUnitMismatchError:
                errors.append(
                    ImportConflict(
                        code="MATERIAL_UNIT_MISMATCH",
                        message=(
                            f"requirement unit {requirement.unit} is incompatible with "
                            f"material unit {material.canonical_unit}"
                        ),
                        entity_temp_id=requirement.material_temp_id,
                        source_reference=requirement.source_reference,
                    )
                )

    @staticmethod
    def _validate_plan_safety(
        plan: PreparedProjectImportPlan,
        errors: list[ImportConflict],
    ) -> None:
        if plan.commit_write_count > plan.limits.max_transaction_writes:
            errors.append(
                ImportConflict(
                    code="TRANSACTION_WRITE_BUDGET_EXCEEDED",
                    message=(
                        "project import requires "
                        f"{plan.commit_write_count} atomic writes; the safe limit is "
                        f"{plan.limits.max_transaction_writes}"
                    ),
                )
            )
        if plan.largest_document_bytes > plan.limits.max_document_bytes:
            errors.append(
                ImportConflict(
                    code="IMPORT_DOCUMENT_SIZE_EXCEEDED",
                    message=(
                        "project import draft exceeds the safe document limit of "
                        f"{plan.limits.max_document_bytes} bytes"
                    ),
                )
            )

    @staticmethod
    def _collect_unresolved_reference_warnings(
        draft: ProjectImportDraft,
        warnings: list[ImportWarning],
    ) -> None:
        for reference in draft.unresolved_references:
            warnings.append(
                ImportWarning(
                    code="UNRESOLVED_REFERENCE",
                    message=(
                        f"reference requires human review; no date or entity was inferred: {reference}"
                    ),
                )
            )


def _deduplicate_warnings(warnings: list[ImportWarning]) -> list[ImportWarning]:
    seen: set[str] = set()
    result: list[ImportWarning] = []
    for warning in warnings:
        key = warning.model_dump_json()
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result


def _deduplicate_conflicts(conflicts: list[ImportConflict]) -> list[ImportConflict]:
    seen: set[str] = set()
    result: list[ImportConflict] = []
    for conflict in conflicts:
        key = conflict.model_dump_json()
        if key not in seen:
            seen.add(key)
            result.append(conflict)
    return result


__all__ = [
    "ProjectImportValidationError",
    "ProjectImportValidationResult",
    "ProjectImportValidator",
]
