"""Authorized project context repository."""

from dataclasses import dataclass
from collections.abc import Sequence

from app.domain.authorization import ProjectAccessContext
from app.domain.authorization import ProjectPermission, ensure_permission, ensure_project_scope
from app.domain.enums import ApprovalStatus, IssueStatus, TaskStatus
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
        ensure_project_scope(access, access.project_id)
        ensure_permission(access, ProjectPermission.READ)
        tasks = self._task_repo.list(access)
        materials = self._material_repo.list(access)
        open_issues = tuple(
            issue
            for issue in self._store.repository(Issue).list(access.project_id)
            if issue.status in {IssueStatus.OPEN, IssueStatus.ACKNOWLEDGED, IssueStatus.MITIGATED}
        )
        pending_approvals = tuple(
            approval
            for approval in self._store.repository(Approval).list(access.project_id)
            if approval.status is ApprovalStatus.PENDING
        )

        return ProjectContext(
            project_id=access.project_id,
            active_tasks=tuple(task for task in tasks if task.status is not TaskStatus.CANCELLED),
            materials=materials,
            open_issues=open_issues,
            pending_approvals=pending_approvals,
        )
