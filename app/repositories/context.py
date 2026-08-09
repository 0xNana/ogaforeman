"""Authorized project context repository."""

from dataclasses import dataclass
from collections.abc import Sequence

from app.domain.authorization import ProjectAccessContext
from app.domain.models import Approval, Issue, Material, Task
from app.repositories.interfaces import RepositoryStore
from app.repositories.tasks import TaskRepository
from app.repositories.materials import MaterialRepository


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    active_tasks: Sequence[Task]
    materials: Sequence[Material]
    open_issues: Sequence[Issue]
    pending_approvals: Sequence[Approval]


class ContextRepository:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._task_repo = TaskRepository(store)
        self._material_repo = MaterialRepository(store)

    def get_bounded_context(self, access: ProjectAccessContext) -> ProjectContext:
        tasks = self._task_repo.list(access)
        materials = self._material_repo.list(access)

        # Currently IssueRepository and ApprovalRepository may not be fully implemented,
        # so we will initialize empty lists for them.
        open_issues: Sequence[Issue] = ()
        pending_approvals: Sequence[Approval] = ()

        return ProjectContext(
            project_id=access.project_id,
            active_tasks=tasks,
            materials=materials,
            open_issues=open_issues,
            pending_approvals=pending_approvals,
        )
