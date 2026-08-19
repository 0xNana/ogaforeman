from datetime import UTC, datetime

import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import TaskOperation
from app.domain.enums import MemberRole, ProjectStatus, TaskStatus
from app.domain.models import ActivityEvent, Project, Task, ConversationMemory
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_action_composer import (
    ActionInterpretationEnvelope,
    TaskActionBatchInterpretation,
    TaskActionInterpretation,
)
from app.services.conversation_action_execution import ConversationActionExecutionService


PROJECT_ID = "prj_taskbatch123"


class _ProjectReader:
    def __init__(self) -> None:
        self.project = Project(
            id=PROJECT_ID,
            name="Ridge House",
            location="Accra",
            timezone="Africa/Accra",
            status=ProjectStatus.ACTIVE,
            created_by="usr_foreman123",
        )

    def require(self, _access: ProjectAccessContext) -> Project:
        return self.project


class _BatchInterpreter:
    def __init__(self, interpretation: TaskActionBatchInterpretation) -> None:
        self.interpretation = interpretation

    async def interpret(self, _message: str, *, context: object) -> TaskActionBatchInterpretation:
        return self.interpretation


def _access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman123", subject="foreman"),
        project_id=PROJECT_ID,
        role=MemberRole.ADMIN,
    )


def _service(
    *tasks: Task,
    interpretation: TaskActionBatchInterpretation,
) -> tuple[InMemoryRepositoryStore, ConversationActionExecutionService]:
    store = InMemoryRepositoryStore()
    for task in tasks:
        store.repository(Task).create(task)
    return store, ConversationActionExecutionService(
        store,
        _ProjectReader(),
        _BatchInterpreter(interpretation),
        proposal_signing_key=b"task-batch-test-signing-key-32-bytes",
    )


def _due_batch() -> TaskActionBatchInterpretation:
    return TaskActionBatchInterpretation(
        actions=(
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_DUE_DATE,
                task_reference="excavation",
                planned_end=datetime(2026, 8, 20, tzinfo=UTC),
            ),
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_DUE_DATE,
                task_reference="foundation",
                planned_end=datetime(2026, 8, 19, tzinfo=UTC),
            ),
        )
    )


def test_action_envelope_accepts_multiple_independent_typed_task_actions() -> None:
    envelope = ActionInterpretationEnvelope.model_validate(
        {
            "action": {
                "kind": "task_batch",
                "actions": [
                    {
                        "kind": "task",
                        "operation": "change_due_date",
                        "task_reference": "excavation",
                        "planned_end": "2026-08-20T00:00:00Z",
                    },
                    {
                        "kind": "task",
                        "operation": "change_due_date",
                        "task_reference": "foundation",
                        "planned_end": "2026-08-19T00:00:00Z",
                    },
                ],
            }
        }
    )

    assert isinstance(envelope.action, TaskActionBatchInterpretation)
    assert [action.task_reference for action in envelope.action.actions] == [
        "excavation",
        "foundation",
    ]
    canonical = ActionInterpretationEnvelope.model_validate(
        {
            "kind": "task_batch",
            "actions": [
                {
                    "kind": "task",
                    "operation": "change_due_date",
                    "task_reference": "excavation",
                    "due_date": "2026-08-20T00:00:00Z",
                },
                {
                    "kind": "task",
                    "operation": "change_due_date",
                    "task_reference": "foundation",
                    "due_date": "2026-08-19T00:00:00Z",
                },
            ],
        }
    )
    assert isinstance(canonical.action, TaskActionBatchInterpretation)


@pytest.mark.asyncio
async def test_day_only_dates_use_retrieved_project_calendar_context() -> None:
    interpretation = TaskActionBatchInterpretation(
        actions=(
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_DUE_DATE,
                task_reference="excavation",
                due_day=20,
            ),
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_DUE_DATE,
                task_reference="foundation",
                due_day=19,
            ),
        )
    )
    store, service = _service(
        Task(
            id="tsk_excavation123",
            project_id=PROJECT_ID,
            title="Excavation",
            status=TaskStatus.PLANNED,
        ),
        Task(
            id="tsk_foundation123",
            project_id=PROJECT_ID,
            title="Foundation",
            status=TaskStatus.PLANNED,
        ),
        interpretation=interpretation,
    )

    result = await service.execute(
        _access(), "excavation due 20th, foundation due 19th", idempotency_key="batch-date"
    )

    assert result.kind == "done"
    tasks = {task.title: task for task in store.repository(Task).list(PROJECT_ID)}
    assert tasks["Excavation"].planned_end.date().isoformat() == "2026-08-20"
    assert tasks["Foundation"].planned_end.date().isoformat() == "2026-08-19"


@pytest.mark.asyncio
async def test_task_batch_updates_two_tasks_and_is_idempotent() -> None:
    store, service = _service(
        Task(
            id="tsk_excavation123",
            project_id=PROJECT_ID,
            title="Excavation",
            status=TaskStatus.PLANNED,
        ),
        Task(
            id="tsk_foundation123",
            project_id=PROJECT_ID,
            title="Foundation",
            status=TaskStatus.PLANNED,
        ),
        interpretation=_due_batch(),
    )

    first = await service.execute(_access(), "update them separately", idempotency_key="batch-1")
    second = await service.execute(_access(), "update them separately", idempotency_key="batch-1")

    tasks = {task.title: task for task in store.repository(Task).list(PROJECT_ID)}
    assert first.text == "Done. Excavation is due August 20 and Foundation is due August 19."
    assert first.mutation_performed is True
    assert second.mutation_performed is False
    assert tasks["Excavation"].planned_end.date().isoformat() == "2026-08-20"
    assert tasks["Foundation"].planned_end.date().isoformat() == "2026-08-19"
    assert len(store.repository(Task).list(PROJECT_ID)) == 2
    assert [event.action for event in store.repository(ActivityEvent).list(PROJECT_ID)] == [
        "task.due_date_changed",
        "task.due_date_changed",
    ]


@pytest.mark.asyncio
async def test_task_batch_can_update_existing_and_create_explicit_missing_task() -> None:
    interpretation = TaskActionBatchInterpretation(
        actions=(
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_DUE_DATE,
                task_reference="excavation",
                planned_end=datetime(2026, 8, 20, tzinfo=UTC),
            ),
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_DUE_DATE,
                task_reference="foundation",
                planned_end=datetime(2026, 8, 19, tzinfo=UTC),
            ),
        )
    )
    store, service = _service(
        Task(
            id="tsk_excavation123",
            project_id=PROJECT_ID,
            title="Excavation",
            status=TaskStatus.PLANNED,
        ),
        interpretation=interpretation,
    )

    result = await service.execute(
        _access(), "update them as separate tasks", idempotency_key="batch-2"
    )

    tasks = {task.title: task for task in store.repository(Task).list(PROJECT_ID)}
    assert result.mutation_performed is True
    assert set(tasks) == {"Excavation", "foundation"}
    assert tasks["foundation"].planned_end.date().isoformat() == "2026-08-19"


@pytest.mark.asyncio
async def test_task_batch_creates_two_missing_tasks_as_separate_typed_commands() -> None:
    interpretation = TaskActionBatchInterpretation(
        actions=(
            TaskActionInterpretation(
                operation=TaskOperation.CREATE,
                title="Excavation",
                planned_end=datetime(2026, 8, 20, tzinfo=UTC),
            ),
            TaskActionInterpretation(
                operation=TaskOperation.CREATE,
                title="Foundation",
                planned_end=datetime(2026, 8, 19, tzinfo=UTC),
            ),
        )
    )
    store, service = _service(interpretation=interpretation)

    result = await service.execute(
        _access(), "create both as separate tasks", idempotency_key="batch-create"
    )

    tasks = {task.title: task for task in store.repository(Task).list(PROJECT_ID)}
    assert result.kind == "done"
    assert set(tasks) == {"Excavation", "Foundation"}
    assert tasks["Excavation"].planned_end.date().isoformat() == "2026-08-20"
    assert tasks["Foundation"].planned_end.date().isoformat() == "2026-08-19"


@pytest.mark.asyncio
async def test_task_batch_clarifies_only_ambiguous_entity_and_persists_both_actions() -> None:
    store, service = _service(
        Task(
            id="tsk_excavation123",
            project_id=PROJECT_ID,
            title="Excavation",
            status=TaskStatus.PLANNED,
        ),
        Task(
            id="tsk_foundationa123",
            project_id=PROJECT_ID,
            title="Foundation concrete",
            status=TaskStatus.PLANNED,
        ),
        Task(
            id="tsk_foundationb123",
            project_id=PROJECT_ID,
            title="Foundation excavation",
            status=TaskStatus.PLANNED,
        ),
        interpretation=_due_batch(),
    )

    result = await service.execute(
        _access(), "update excavation and foundation", idempotency_key="batch-3"
    )

    memory = store.repository(ConversationMemory).list(PROJECT_ID)[0]
    assert result.kind == "clarification"
    assert "foundation" in result.text.casefold()
    assert memory.active_clarification is not None
    assert memory.active_clarification.action_json is not None
    restored = TaskActionBatchInterpretation.model_validate_json(
        memory.active_clarification.action_json
    )
    assert [action.task_reference for action in restored.actions] == ["excavation", "foundation"]
    assert store.repository(Task).get(PROJECT_ID, "tsk_excavation123").planned_end is None
