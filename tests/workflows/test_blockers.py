from app.domain.models import Task, TaskPriority, TaskSource
from app.services.schedule_impact import calculate_impact


def test_calculate_impact():
    task1 = Task(
        id="task_001",
        project_id="proj_001",
        title="Task 1",
        dependency_ids=[],
        priority=TaskPriority.MEDIUM,
        source=TaskSource.MANUAL,
    )
    task2 = Task(
        id="task_002",
        project_id="proj_001",
        title="Task 2",
        dependency_ids=["task_001"],
        priority=TaskPriority.MEDIUM,
        source=TaskSource.MANUAL,
    )
    task3 = Task(
        id="task_003",
        project_id="proj_001",
        title="Task 3",
        dependency_ids=["task_002"],
        priority=TaskPriority.MEDIUM,
        source=TaskSource.MANUAL,
    )

    impacted = calculate_impact(iter([task1, task2, task3]), ["task_001"])
    assert "task_001" in impacted
    assert "task_002" in impacted
    assert "task_003" in impacted

    impacted2 = calculate_impact([task1, task2, task3], ["task_002"])
    assert "task_001" not in impacted2
    assert "task_002" in impacted2
    assert "task_003" in impacted2
