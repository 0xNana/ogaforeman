"""Tests for durable agent runtime management."""

from app.domain.enums import AgentRunStatus, WorkflowName
from app.workflows.runtime import RuntimeManager
from app.repositories.memory import InMemoryRepositoryStore


def test_runtime_manager_lifecycle():
    store = InMemoryRepositoryStore()
    manager = RuntimeManager(store)

    project_id = "prj_test"
    run_id = "run_123"
    event_id = "evt_456"

    # 1. Start run
    run = manager.start_run(
        project_id=project_id,
        trigger_event_id=event_id,
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )
    assert run.status == AgentRunStatus.RUNNING
    assert run.step is None

    # 2. Update checkpoint
    run = manager.update_checkpoint(project_id, run_id, "extract_facts")
    assert run.step == "extract_facts"

    # Simulate restart by instantiating a new manager with the same store
    manager2 = RuntimeManager(store)
    reloaded_run = manager2.get_run(project_id, run_id)
    assert reloaded_run is not None
    assert reloaded_run.status == AgentRunStatus.RUNNING
    assert reloaded_run.step == "extract_facts"

    # 3. Resume run
    run = manager2.start_run(
        project_id=project_id,
        trigger_event_id=event_id,
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )
    assert run.status == AgentRunStatus.RUNNING

    # 4. Pause for approval
    run = manager2.pause_for_approval(project_id, run_id, "wait_for_purchase")
    assert run.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert run.step == "wait_for_purchase"

    # Restart again
    manager3 = RuntimeManager(store)

    # 5. Resume from approval
    run = manager3.start_run(
        project_id=project_id,
        trigger_event_id=event_id,
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )
    assert run.status == AgentRunStatus.RUNNING
    assert run.step == "wait_for_purchase"

    # 6. Complete
    run = manager3.complete_run(project_id, run_id)
    assert run.status == AgentRunStatus.COMPLETED
    assert run.completed_at is not None


def test_runtime_manager_failure():
    store = InMemoryRepositoryStore()
    manager = RuntimeManager(store)

    project_id = "prj_test"
    run_id = "run_fail"

    manager.start_run(
        project_id=project_id,
        trigger_event_id="evt_123",
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )

    run = manager.fail_run(project_id, run_id, "PROCESS_ERROR", "Failed to extract data")
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "PROCESS_ERROR"
    assert run.error_summary == "Failed to extract data"
    assert run.completed_at is not None

    retried = manager.start_run(
        project_id=project_id,
        trigger_event_id="evt_123",
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id="trace_abc",
    )
    assert retried.status is AgentRunStatus.RUNNING
    assert retried.attempt == 2
    assert retried.completed_at is None
    assert retried.error_code is None
