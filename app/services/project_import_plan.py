"""Immutable, deterministic write plan for one project import commit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from pydantic import BaseModel

from app.domain.import_records import (
    ImportProvenanceTargetType,
    import_dependency_target_id,
)
from app.domain.project_import import ProjectImportDraft


@dataclass(frozen=True, slots=True)
class ProjectImportSafetyLimits:
    """Conservative limits that leave headroom below Firestore hard bounds."""

    max_transaction_writes: int = 450
    max_document_bytes: int = 750_000
    document_envelope_bytes: int = 32_768
    generated_document_envelope_bytes: int = 8_192


DEFAULT_PROJECT_IMPORT_SAFETY_LIMITS = ProjectImportSafetyLimits()


@dataclass(frozen=True, slots=True)
class PlannedDependency:
    predecessor_task_id: str
    successor_task_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class PlannedRequirement:
    task_id: str
    material_id: str
    target_id: str


@dataclass(frozen=True, slots=True)
class PreparedProjectImportPlan:
    """The canonical IDs and exact writes validation authorizes for commit."""

    import_id: str
    project_id: str
    phase_ids: tuple[tuple[str, str], ...]
    task_ids: tuple[tuple[str, str], ...]
    material_ids: tuple[tuple[str, str], ...]
    ledger_ids: tuple[tuple[str, str], ...]
    dependencies: tuple[PlannedDependency, ...]
    requirements: tuple[PlannedRequirement, ...]
    largest_document_bytes: int
    limits: ProjectImportSafetyLimits

    @property
    def provenance_targets(self) -> tuple[tuple[ImportProvenanceTargetType, str], ...]:
        return (
            tuple(
                (ImportProvenanceTargetType.PROJECT_PHASE, canonical_id)
                for _, canonical_id in self.phase_ids
            )
            + tuple(
                (ImportProvenanceTargetType.TASK, canonical_id) for _, canonical_id in self.task_ids
            )
            + tuple(
                (ImportProvenanceTargetType.MATERIAL, canonical_id)
                for _, canonical_id in self.material_ids
            )
            + tuple(
                (ImportProvenanceTargetType.MATERIAL_LEDGER_ENTRY, canonical_id)
                for _, canonical_id in self.ledger_ids
            )
            + tuple(
                (ImportProvenanceTargetType.DEPENDENCY, dependency.target_id)
                for dependency in self.dependencies
            )
            + tuple(
                (ImportProvenanceTargetType.MATERIAL_REQUIREMENT, requirement.target_id)
                for requirement in self.requirements
            )
        )

    @property
    def provenance_write_count(self) -> int:
        return len(self.provenance_targets)

    @property
    def canonical_write_count(self) -> int:
        return (
            1  # reviewed project metadata
            + len(self.phase_ids)
            + len(self.task_ids)
            + len(self.material_ids)
            + len(self.ledger_ids)
            + len(self.requirements)
        )

    @property
    def activity_write_count(self) -> int:
        return (
            len(self.task_ids)
            + len(self.dependencies)
            + len(self.material_ids)
            + len(self.requirements)
            + 1  # project.initialized
        )

    @property
    def import_state_write_count(self) -> int:
        return 1

    @property
    def commit_write_count(self) -> int:
        return (
            self.provenance_write_count
            + self.canonical_write_count
            + self.activity_write_count
            + self.import_state_write_count
        )


def prepare_project_import_plan(
    draft: ProjectImportDraft,
    *,
    limits: ProjectImportSafetyLimits = DEFAULT_PROJECT_IMPORT_SAFETY_LIMITS,
) -> PreparedProjectImportPlan:
    phase_ids = tuple(
        (phase.temp_id, canonical_import_id("phs", draft.id, phase.temp_id))
        for phase in draft.phases
    )
    task_ids = tuple(
        (task.temp_id, canonical_import_id("tsk", draft.id, task.temp_id)) for task in draft.tasks
    ) + tuple(
        (milestone.temp_id, canonical_import_id("tsk", draft.id, milestone.temp_id))
        for milestone in draft.milestones
    )
    material_ids = tuple(
        (material.temp_id, canonical_import_id("mat", draft.id, material.temp_id))
        for material in draft.materials
    )
    ledger_ids = tuple(
        (material.temp_id, canonical_import_id("led", draft.id, material.temp_id))
        for material in draft.materials
        if material.initial_on_hand_quantity > 0
    )
    dependencies: list[PlannedDependency] = []
    for dependency in draft.dependencies:
        predecessor_task_id = canonical_import_id("tsk", draft.id, dependency.predecessor_temp_id)
        successor_task_id = canonical_import_id("tsk", draft.id, dependency.successor_temp_id)
        dependencies.append(
            PlannedDependency(
                predecessor_task_id=predecessor_task_id,
                successor_task_id=successor_task_id,
                target_id=import_dependency_target_id(predecessor_task_id, successor_task_id),
            )
        )
    requirements = tuple(
        PlannedRequirement(
            task_id=canonical_import_id("tsk", draft.id, requirement.task_temp_id),
            material_id=canonical_import_id("mat", draft.id, requirement.material_temp_id),
            target_id=canonical_import_id(
                "req", draft.id, requirement.task_temp_id, requirement.material_temp_id
            ),
        )
        for requirement in draft.material_requirements
    )
    return PreparedProjectImportPlan(
        import_id=draft.id,
        project_id=draft.project_id,
        phase_ids=phase_ids,
        task_ids=task_ids,
        material_ids=material_ids,
        ledger_ids=ledger_ids,
        dependencies=tuple(dependencies),
        requirements=requirements,
        largest_document_bytes=_largest_document_bytes(draft, limits),
        limits=limits,
    )


def canonical_import_id(prefix: str, *parts: str) -> str:
    digest = sha256(":|:".join(parts).encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _largest_document_bytes(
    draft: ProjectImportDraft,
    limits: ProjectImportSafetyLimits,
) -> int:
    import_record_bytes = _encoded_bytes(draft) + limits.document_envelope_bytes
    generated_documents = (
        *draft.phases,
        *draft.tasks,
        *draft.milestones,
        *draft.materials,
        *draft.material_requirements,
    )
    largest_generated = max(
        (
            _encoded_bytes(item) + limits.generated_document_envelope_bytes
            for item in generated_documents
        ),
        default=0,
    )
    return max(import_record_bytes, largest_generated)


def _encoded_bytes(value: BaseModel) -> int:
    payload = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return len(payload.encode("utf-8"))


__all__ = [
    "DEFAULT_PROJECT_IMPORT_SAFETY_LIMITS",
    "PlannedDependency",
    "PlannedRequirement",
    "PreparedProjectImportPlan",
    "ProjectImportSafetyLimits",
    "canonical_import_id",
    "prepare_project_import_plan",
]
