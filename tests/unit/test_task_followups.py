from datetime import UTC, datetime

import pytest

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, RoleRequiredError
from app.domain.enums import (
    ActorType,
    IssueDetectedBy,
    IssueType,
    MemberRole,
    Severity,
    SiteUpdateInputType,
    TaskSource,
    TaskStatus,
)
from app.domain.models import ActivityEvent, Issue, SiteUpdate, Task
from app.repositories.memory import InMemoryRepositoryStore
from app.services.tasks import (
    CreateBlockerFollowUpCommand,
    TaskService,
    TaskStateError,
)


NOW = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
PROJECT_ID = "prj_followup123"
BLOCKED_TASK_ID = "tsk_electrical123"
ISSUE_ID = "iss_blocker123"
UPDATE_ID = "sup_followup123"


def _store(*, issue_task_ids: list[str] | None = None) -> InMemoryRepositoryStore:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id=BLOCKED_TASK_ID,
            project_id=PROJECT_ID,
            title="Electrical rough-in",
            status=TaskStatus.BLOCKED,
            assigned_to="usr_electrician123",
        )
    )
    store.repository(SiteUpdate).create(
        SiteUpdate(
            id=UPDATE_ID,
            project_id=PROJECT_ID,
            submitted_by="usr_foreman123",
            input_type=SiteUpdateInputType.TEXT,
            raw_text="The assigned subcontractor was absent today.",
            client_event_id="client-followup-123",
            submitted_at=NOW,
        )
    )
    store.repository(Issue).create(
        Issue(
            id=ISSUE_ID,
            project_id=PROJECT_ID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="The assigned subcontractor was absent today.",
            evidence_refs=[UPDATE_ID],
            task_ids=issue_task_ids or [BLOCKED_TASK_ID],
            detected_by=IssueDetectedBy.SITE_UPDATE,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return store


def _access(*, role: MemberRole = MemberRole.FOREMAN) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman123", subject="firebase-foreman"),
        project_id=PROJECT_ID,
        role=role,
    )


def _command() -> CreateBlockerFollowUpCommand:
    return CreateBlockerFollowUpCommand(
        project_id=PROJECT_ID,
        blocked_task_id=BLOCKED_TASK_ID,
        source_issue_id=ISSUE_ID,
        source_site_update_id=UPDATE_ID,
        occurred_at=NOW,
    )


def _context() -> MutationContext:
    return MutationContext(
        project_id=PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id="usr_foreman123",
        source_event_id="evt_followup123",
        agent_run_id="run_followup123",
        idempotency_key="task:blocker-followup:123",
        occurred_at=NOW,
    )


def test_blocker_follow_up_is_assigned_source_linked_audited_and_idempotent() -> None:
    store = _store()
    service = TaskService(store)

    created = service.create_blocker_follow_up(_access(), _command(), _context())
    task_repository = store.repository(Task)
    blocked_task = task_repository.require(PROJECT_ID, BLOCKED_TASK_ID)
    task_repository.save(
        blocked_task.model_copy(update={"assigned_to": "usr_reassigned123"}),
        expected_version=blocked_task.version,
    )
    replay = service.create_blocker_follow_up(_access(), _command(), _context())

    follow_ups = [
        task
        for task in store.repository(Task).list(PROJECT_ID)
        if task.source is TaskSource.SITE_UPDATE
    ]
    assert replay.duplicate is True
    assert follow_ups == [created.task]
    assert created.task.assigned_to == "usr_electrician123"
    assert created.task.source_refs == [UPDATE_ID, ISSUE_ID, BLOCKED_TASK_ID]
    assert created.activity.action == "task.follow_up_created"
    assert len(store.repository(ActivityEvent).list(PROJECT_ID)) == 1


def test_blocker_follow_up_rejects_an_issue_not_linked_to_the_source_task() -> None:
    store = _store(issue_task_ids=["tsk_different123"])

    with pytest.raises(TaskStateError, match="does not reference the source task"):
        TaskService(store).create_blocker_follow_up(_access(), _command(), _context())

    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


def test_blocker_follow_up_requires_operate_permission() -> None:
    store = _store()

    with pytest.raises(RoleRequiredError):
        TaskService(store).create_blocker_follow_up(
            _access(role=MemberRole.VIEWER),
            _command(),
            _context(),
        )

    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()
