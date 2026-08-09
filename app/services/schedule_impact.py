from typing import Iterable, Set, Dict, List
from app.domain.models import Task


def calculate_impact(tasks: Iterable[Task], blocked_task_ids: List[str]) -> Set[str]:
    tasks_by_id = {task.id: task for task in tasks}

    # build reverse dependency graph
    reverse_deps: Dict[str, List[str]] = {task_id: [] for task_id in tasks_by_id}
    for task in tasks:
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
                if downstream not in impacted:
                    stack.append(downstream)

    return impacted
