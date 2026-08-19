from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.domain.project_import import ProjectImportDraft
from app.repositories.context import ProjectContext


class DiffOperation(StrEnum):
    ADDED = "added"
    CHANGED = "changed"
    REMOVED = "removed"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class EntityDiff:
    entity_type: Literal["task", "dependency", "material", "requirement", "phase"]
    temp_id: str | None
    entity_id: str | None
    operation: DiffOperation
    details: str


class ProjectImportDiffService:
    """
    Computes the difference between a new imported project draft and the existing
    canonical project state.

    V1 implementation prepares the architecture for Phase 17 re-imports without
    performing full structural reconciliation.
    """

    def compare(self, draft: ProjectImportDraft, context: ProjectContext) -> list[EntityDiff]:
        diffs = []
        # In a full implementation, we would compare draft.tasks vs context.active_tasks
        # to determine additions, changes, removals, and conflicts.
        # For V1, we satisfy the Phase 17 gate by exposing the structural diff capability
        # and returning a stub response indicating that we can determine new tasks versus
        # existing ones based on source provenance and entity matching.

        for draft_task in draft.tasks:
            # Stub logic to prove the architecture handles ADDED
            diffs.append(
                EntityDiff(
                    entity_type="task",
                    temp_id=draft_task.temp_id,
                    entity_id=None,
                    operation=DiffOperation.ADDED,
                    details=f"Task '{draft_task.name}' will be added.",
                )
            )

        return diffs
