"""Deterministic additive-only preflight for canonical project imports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeVar

from pydantic import BaseModel

from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.import_records import MaterialRequirement, ProjectPhase
from app.domain.materials import normalize_material_name
from app.domain.models import Material, Task
from app.domain.project_import import ImportConflict, MaterialRequirementDraft, ProjectImportDraft
from app.repositories.context import ProjectContext
from app.repositories.interfaces import ProjectRepository, RepositorySession
from app.repositories.membership import AuthorizedProjectRepository
from app.services.project_import_normalization import normalize_task_name_for_match


class DiffOperation(StrEnum):
    ADDED = "added"
    CHANGED = "changed"
    REMOVED = "removed"
    CONFLICTED = "conflicted"


EntityType = Literal["task", "dependency", "material", "requirement", "phase"]


@dataclass(frozen=True, slots=True)
class EntityDiff:
    entity_type: EntityType
    temp_id: str | None
    entity_id: str | None
    operation: DiffOperation
    details: str


class ProjectImportDiffConflictError(ValueError):
    """Raised when a V1 import would require reconciliation."""

    code = "PROJECT_IMPORT_CANONICAL_CONFLICT"

    def __init__(self, diffs: Sequence[EntityDiff]) -> None:
        self.diffs = tuple(diffs)
        super().__init__("project import is not a safe additive change")


@dataclass(frozen=True, slots=True)
class _CanonicalMatch:
    entity_ids: tuple[str, ...]

    @property
    def unique_id(self) -> str | None:
        return self.entity_ids[0] if len(self.entity_ids) == 1 else None

    @property
    def is_new(self) -> bool:
        return not self.entity_ids

    @property
    def is_ambiguous(self) -> bool:
        return len(self.entity_ids) > 1


EntityT = TypeVar("EntityT", bound=BaseModel)


class ProjectImportDiffService:
    """Compare a draft with canonical truth under V1's additive-only policy."""

    def compare(
        self,
        draft: ProjectImportDraft,
        context: ProjectContext,
        *,
        requirements: Sequence[MaterialRequirement] = (),
        phases: Sequence[ProjectPhase] = (),
    ) -> list[EntityDiff]:
        if context.project_id != draft.project_id:
            raise ValueError("project import diff context does not match the draft project")

        diffs: list[EntityDiff] = []
        task_index = _task_index(context.active_tasks)
        material_index = _material_index(context.materials)
        phase_index = _phase_index(phases)
        task_matches: dict[str, _CanonicalMatch] = {}
        material_matches: dict[str, _CanonicalMatch] = {}

        for phase in draft.phases:
            match = _match(phase_index, normalize_task_name_for_match(phase.name))
            diffs.append(
                _identity_diff(
                    entity_type="phase",
                    temp_id=phase.temp_id,
                    display_name=phase.name,
                    match=match,
                )
            )

        for task in draft.tasks:
            match = _match(task_index, normalize_task_name_for_match(task.name))
            task_matches[task.temp_id] = match
            diffs.append(
                _identity_diff(
                    entity_type="task",
                    temp_id=task.temp_id,
                    display_name=task.name,
                    match=match,
                )
            )
        for milestone in draft.milestones:
            match = _match(task_index, normalize_task_name_for_match(milestone.name))
            task_matches[milestone.temp_id] = match
            diffs.append(
                _identity_diff(
                    entity_type="task",
                    temp_id=milestone.temp_id,
                    display_name=milestone.name,
                    match=match,
                )
            )

        tasks_by_id = {task.id: task for task in context.active_tasks}
        for dependency in draft.dependencies:
            predecessor = task_matches[dependency.predecessor_temp_id]
            successor = task_matches[dependency.successor_temp_id]
            diffs.append(
                _dependency_diff(
                    dependency.predecessor_temp_id,
                    dependency.successor_temp_id,
                    predecessor,
                    successor,
                    tasks_by_id,
                )
            )

        for material in draft.materials:
            match = _match(material_index, normalize_material_name(material.name))
            material_matches[material.temp_id] = match
            diff = _identity_diff(
                entity_type="material",
                temp_id=material.temp_id,
                display_name=material.name,
                match=match,
            )
            if match.unique_id is not None:
                existing = next(item for item in context.materials if item.id == match.unique_id)
                if existing.unit != material.canonical_unit:
                    diff = EntityDiff(
                        entity_type="material",
                        temp_id=material.temp_id,
                        entity_id=existing.id,
                        operation=DiffOperation.CONFLICTED,
                        details=(
                            f"Material '{material.name}' matches canonical material "
                            f"{existing.id} with incompatible unit {existing.unit!r}."
                        ),
                    )
            diffs.append(diff)

        requirements_by_pair: dict[tuple[str, str], list[MaterialRequirement]] = defaultdict(list)
        for canonical_requirement in requirements:
            requirements_by_pair[
                (canonical_requirement.task_id, canonical_requirement.material_id)
            ].append(canonical_requirement)
        for values in requirements_by_pair.values():
            values.sort(key=lambda item: item.id)

        for requirement in draft.material_requirements:
            diffs.append(
                _requirement_diff(
                    requirement,
                    task_matches[requirement.task_temp_id],
                    material_matches[requirement.material_temp_id],
                    requirements_by_pair,
                )
            )

        return diffs

    def compare_session(
        self,
        draft: ProjectImportDraft,
        session: RepositorySession,
        access: ProjectAccessContext,
    ) -> list[EntityDiff]:
        """Read canonical truth through the authorized transaction session."""

        tasks = _authorized_repository(session, Task, access).list(draft.project_id)
        materials = _authorized_repository(session, Material, access).list(draft.project_id)
        requirements = _authorized_repository(session, MaterialRequirement, access).list(
            draft.project_id
        )
        phases = _authorized_repository(session, ProjectPhase, access).list(draft.project_id)
        context = ProjectContext(
            project_id=draft.project_id,
            active_tasks=tasks,
            materials=materials,
            open_issues=(),
            pending_approvals=(),
        )
        return self.compare(draft, context, requirements=requirements, phases=phases)

    @staticmethod
    def ensure_additive(diffs: Iterable[EntityDiff]) -> None:
        blocking = tuple(item for item in diffs if item.operation is not DiffOperation.ADDED)
        if blocking:
            raise ProjectImportDiffConflictError(blocking)

    @staticmethod
    def blocking_conflicts(diffs: Iterable[EntityDiff]) -> tuple[ImportConflict, ...]:
        return tuple(
            ImportConflict(
                code=f"CANONICAL_{item.entity_type.upper()}_{item.operation.value.upper()}",
                message=item.details,
                entity_temp_id=item.temp_id,
                existing_reference=item.entity_id,
            )
            for item in diffs
            if item.operation is not DiffOperation.ADDED
        )


def _identity_diff(
    *,
    entity_type: Literal["task", "material", "phase"],
    temp_id: str,
    display_name: str,
    match: _CanonicalMatch,
) -> EntityDiff:
    label = entity_type.capitalize()
    if match.is_new:
        return EntityDiff(
            entity_type=entity_type,
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.ADDED,
            details=f"{label} '{display_name}' will be added.",
        )
    if match.is_ambiguous:
        return EntityDiff(
            entity_type=entity_type,
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details=(
                f"{label} '{display_name}' matches multiple canonical {entity_type}s; "
                "V1 cannot reconcile the ambiguous identity."
            ),
        )
    return EntityDiff(
        entity_type=entity_type,
        temp_id=temp_id,
        entity_id=match.unique_id,
        operation=DiffOperation.CHANGED,
        details=(
            f"{label} '{display_name}' matches existing canonical {entity_type} "
            f"{match.unique_id}; V1 imports cannot replace or duplicate it."
        ),
    )


def _dependency_diff(
    predecessor_temp_id: str,
    successor_temp_id: str,
    predecessor: _CanonicalMatch,
    successor: _CanonicalMatch,
    tasks_by_id: dict[str, Task],
) -> EntityDiff:
    temp_id = successor_temp_id
    if predecessor.is_new and successor.is_new:
        return EntityDiff(
            entity_type="dependency",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.ADDED,
            details="Task dependency will be added.",
        )
    if predecessor.is_ambiguous or successor.is_ambiguous:
        return EntityDiff(
            entity_type="dependency",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details="Task dependency has an ambiguous canonical endpoint.",
        )
    predecessor_id = predecessor.unique_id
    successor_id = successor.unique_id
    if predecessor_id is None or successor_id is None:
        return EntityDiff(
            entity_type="dependency",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details="Task dependency mixes new and existing canonical endpoints.",
        )
    successor_task = tasks_by_id[successor_id]
    exists = predecessor_id in successor_task.dependency_ids
    return EntityDiff(
        entity_type="dependency",
        temp_id=temp_id,
        entity_id=f"{predecessor_id}->{successor_id}" if exists else None,
        operation=DiffOperation.CHANGED if exists else DiffOperation.CONFLICTED,
        details=(
            "Task dependency already exists and cannot be duplicated."
            if exists
            else "Task dependency would modify existing canonical tasks."
        ),
    )


def _requirement_diff(
    requirement: MaterialRequirementDraft,
    task_match: _CanonicalMatch,
    material_match: _CanonicalMatch,
    requirements_by_pair: dict[tuple[str, str], list[MaterialRequirement]],
) -> EntityDiff:
    temp_id = requirement.task_temp_id
    if task_match.is_new and material_match.is_new:
        return EntityDiff(
            entity_type="requirement",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.ADDED,
            details="Material requirement will be added.",
        )
    if task_match.is_ambiguous or material_match.is_ambiguous:
        return EntityDiff(
            entity_type="requirement",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details="Material requirement has an ambiguous canonical task or material.",
        )
    task_id = task_match.unique_id
    material_id = material_match.unique_id
    if task_id is None or material_id is None:
        return EntityDiff(
            entity_type="requirement",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details="Material requirement mixes new and existing canonical entities.",
        )
    existing = requirements_by_pair.get((task_id, material_id), [])
    if not existing:
        return EntityDiff(
            entity_type="requirement",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details="Material requirement would modify existing canonical entities.",
        )
    if len(existing) > 1:
        return EntityDiff(
            entity_type="requirement",
            temp_id=temp_id,
            entity_id=None,
            operation=DiffOperation.CONFLICTED,
            details="Multiple canonical requirements exist for the matched task and material.",
        )
    current = existing[0]
    changed = (
        current.required_quantity != requirement.required_quantity
        or current.unit != requirement.unit
        or current.required_by != requirement.required_by
    )
    return EntityDiff(
        entity_type="requirement",
        temp_id=temp_id,
        entity_id=current.id,
        operation=DiffOperation.CHANGED,
        details=(
            "Imported material requirement differs from the existing requirement."
            if changed
            else "Material requirement already exists and cannot be duplicated."
        ),
    )


def _task_index(tasks: Sequence[Task]) -> dict[str, tuple[str, ...]]:
    values: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        values[normalize_task_name_for_match(task.title)].add(task.id)
    return _freeze_index(values)


def _material_index(materials: Sequence[Material]) -> dict[str, tuple[str, ...]]:
    values: dict[str, set[str]] = defaultdict(set)
    for material in materials:
        names = {material.name, material.normalized_name, *material.aliases}
        for name in names:
            values[normalize_material_name(name)].add(material.id)
    return _freeze_index(values)


def _phase_index(phases: Sequence[ProjectPhase]) -> dict[str, tuple[str, ...]]:
    values: dict[str, set[str]] = defaultdict(set)
    for phase in phases:
        values[normalize_task_name_for_match(phase.name)].add(phase.id)
    return _freeze_index(values)


def _freeze_index(values: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    return {key: tuple(sorted(entity_ids)) for key, entity_ids in values.items()}


def _match(index: dict[str, tuple[str, ...]], key: str) -> _CanonicalMatch:
    return _CanonicalMatch(index.get(key, ()))


def _authorized_repository(
    session: RepositorySession,
    entity_type: type[EntityT],
    access: ProjectAccessContext,
) -> AuthorizedProjectRepository[EntityT]:
    repository: ProjectRepository[EntityT] = session.repository(entity_type)
    return AuthorizedProjectRepository(
        repository,
        access,
        mutation_permission=ProjectPermission.MANAGE,
    )


__all__ = [
    "DiffOperation",
    "EntityDiff",
    "ProjectImportDiffConflictError",
    "ProjectImportDiffService",
]
