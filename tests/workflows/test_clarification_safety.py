"""Tests for clarification and safety stop branches."""

from app.workflows.clarification import execute_clarification_branch
from app.workflows.safety import execute_safety_stop_branch
from app.workflows.runtime import RuntimeManager
from app.services.notifications import NotificationService
from app.repositories.memory import InMemoryRepositoryStore
from app.services.outbox import OutboxService
from app.domain.enums import WorkflowName, AgentRunStatus
from app.domain.facts import TaskCompletionFact, SafetyIssueFact
from app.domain.models import OutboxMessage


def test_execute_clarification_branch():
    store = InMemoryRepositoryStore()
    runtime = RuntimeManager(store)
    outbox_service = OutboxService(store)
    notifications = NotificationService(outbox_service)

    project_id = "prj_testproject123"
    run_id = "run_testrun123"

    runtime.start_run(
        project_id=project_id,
        trigger_event_id="evt_123",
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )

    clarifications = [
        TaskCompletionFact(
            task_name="Ambiguous task",
            is_completed=True,
            evidence="Some mention of task",
            confidence="low",
            clarification_needed="Which task did you mean?",
        )
    ]

    run = execute_clarification_branch(project_id, run_id, clarifications, runtime, notifications)

    assert run.status == AgentRunStatus.WAITING_FOR_CLARIFICATION

    # Check that a notification was created in outbox
    outbox = store.repository(OutboxMessage).list(project_id)
    assert len(outbox) == 1
    assert outbox[0].message_type == "notification:clarification_needed"


def test_execute_safety_stop_branch():
    store = InMemoryRepositoryStore()
    runtime = RuntimeManager(store)
    outbox_service = OutboxService(store)
    notifications = NotificationService(outbox_service)

    project_id = "prj_testproject123"
    run_id = "run_testrun456"

    runtime.start_run(
        project_id=project_id,
        trigger_event_id="evt_123",
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )

    safety_stops = [
        SafetyIssueFact(
            description="Crane leak",
            severity="critical",
            evidence="Crane is leaking",
            confidence="high",
        )
    ]

    run = execute_safety_stop_branch(project_id, run_id, safety_stops, runtime, notifications)

    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "SAFETY_STOP"

    # Check that an escalation notification was created
    outbox = store.repository(OutboxMessage).list(project_id)
    assert len(outbox) == 1
    assert outbox[0].message_type == "notification:safety_escalation"
