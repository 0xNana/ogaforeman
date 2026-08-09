from collections.abc import Iterable

from app.domain.enums import TaskStatus
from app.domain.models import Task


_TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}


def calculate_impact(tasks: Iterable[Task], blocked_task_ids: list[str]) -> set[str]:
    task_list = list(tasks)
    tasks_by_id = {task.id: task for task in task_list}

    # build reverse dependency graph
    reverse_deps: dict[str, list[str]] = {task_id: [] for task_id in tasks_by_id}
    for task in task_list:
        for dep_id in task.dependency_ids:
            if dep_id in reverse_deps:
                reverse_deps[dep_id].append(task.id)

    impacted = set()
    stack = list(blocked_task_ids)

    while stack:
        current = stack.pop()
        if current in tasks_by_id and current not in impacted:
            impacted.add(current)
            for downstream in reverse_deps.get(current, []):
                if (
                    downstream not in impacted
                    and tasks_by_id[downstream].status not in _TERMINAL_TASK_STATUSES
                ):
                    stack.append(downstream)

    return impacted
