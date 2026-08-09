from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.activity import (
    ActivitySpec,
    MutationContext,
    MutationContextRequiredError,
    WorkflowActivityAction,
)
from app.domain.enums import ActorType, TaskStatus
from app.domain.models import ActivityEvent, Task
from app.repositories.activity import ActivityIdempotencyConflict
from app.repositories.memory import InMemoryRepositoryStore
from app.services.activity import (
    ActivityService,
)
from app.services.workflow_audit import WorkflowAuditService, workflow_audit_activity


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def make_context(**updates: object) -> MutationContext:
    values: dict[str, object] = {
        "project_id": "prj_ridge",
        "actor_type": ActorType.AGENT,
        "actor_id": "agt_site_report",
        "source_event_id": "evt_update001",
        "agent_run_id": "run_update001",
        "idempotency_key": "task-update:evt_update001:tsk_blockwork",
        "occurred_at": NOW,
    }
    values.update(updates)
    return MutationContext(**values)


def make_spec(**updates: object) -> ActivitySpec:
    values: dict[str, object] = {
        "action": "task.progress_updated",
        "entity_type": "task",
        "entity_id": "tsk_blockwork",
        "summary": "Blockwork progress updated to 50 percent",
        "metadata": {"completion_percent": "50"},
    }
    values.update(updates)
    return ActivitySpec(**values)


def test_workflow_activity_registry_covers_the_public_audit_contract() -> None:
    assert {action.value for action in WorkflowActivityAction} == {
        "site_update.received",
        "site_update.media_processed",
        "site_update.interpreted",
        "project.context_retrieved",
        "task.completed",
        "blocker.detected",
        "schedule.risk_detected",
        "material.quantity_updated",
        "material.risk_detected",
        "material.requested",
        "approval.requested",
        "workflow.paused",
        "approval.approved",
        "approval.rejected",
        "workflow.resumed",
        "external_action.executed",
        "report.updated",
        "workflow.completed",
    }


def test_domain_write_and_activity_commit_atomically_with_full_context() -> None:
    store = InMemoryRepositoryStore()
    tasks = store.repository(Task)
    tasks.create(
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
        )
    )
    service = ActivityService(store)

    result = service.mutate(
        make_context(),
        make_spec(),
        lambda session: session.repository(Task).save(
            session.repository(Task)
            .require("prj_ridge", "tsk_blockwork")
            .model_copy(update={"completion_percent": Decimal("50"), "updated_at": NOW}),
            expected_version=0,
        ),
    )

    assert result.value is not None
    assert result.value.completion_percent == 50
    assert result.duplicate is False
    assert result.activity.actor_type is ActorType.AGENT
    assert result.activity.actor_id == "agt_site_report"
    assert result.activity.source_event_id == "evt_update001"
    assert result.activity.agent_run_id == "run_update001"
    assert result.activity.entity_id == "tsk_blockwork"
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_duplicate_mutation_replays_without_second_write_or_activity() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_blockwork",
            project_id="prj_ridge",
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
        )
    )
    service = ActivityService(store)
    calls = 0

    def mutate(session):
        nonlocal calls
        calls += 1
        task = session.repository(Task).require("prj_ridge", "tsk_blockwork")
        return session.repository(Task).save(
            task.model_copy(update={"completion_percent": Decimal("50")}),
            expected_version=task.version,
        )

    first = service.mutate(make_context(), make_spec(), mutate)
    replay = service.mutate(
        make_context(),
        make_spec(),
        mutate,
        replay=lambda session, activity: session.repository(Task).require(
            activity.project_id, activity.entity_id
        ),
    )

    assert first.duplicate is False
    assert replay.duplicate is True
    assert replay.value is not None and replay.value.version == 1
    assert calls == 1
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1


def test_reusing_idempotency_key_for_different_mutation_conflicts() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(id="tsk_blockwork", project_id="prj_ridge", title="Blockwork")
    )
    service = ActivityService(store)
    service.mutate(
        make_context(),
        make_spec(),
        lambda session: session.repository(Task).require("prj_ridge", "tsk_blockwork"),
    )

    with pytest.raises(ActivityIdempotencyConflict):
        service.mutate(
            make_context(),
            make_spec(
                summary="Blockwork progress updated to 75 percent",
                metadata={"completion_percent": "75"},
            ),
            lambda session: session.repository(Task).require("prj_ridge", "tsk_blockwork"),
        )


def test_failed_mutation_rolls_back_domain_write_and_activity() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(id="tsk_blockwork", project_id="prj_ridge", title="Blockwork")
    )
    service = ActivityService(store)

    def fail_after_write(session):
        task = session.repository(Task).require("prj_ridge", "tsk_blockwork")
        session.repository(Task).save(
            task.model_copy(update={"completion_percent": Decimal("25")}),
            expected_version=task.version,
        )
        raise RuntimeError("simulated mutation failure")

    with pytest.raises(RuntimeError, match="simulated"):
        service.mutate(make_context(), make_spec(), fail_after_write)

    assert store.repository(Task).require("prj_ridge", "tsk_blockwork").version == 0
    assert store.repository(ActivityEvent).list("prj_ridge") == ()


def test_mutation_context_is_required_and_activity_data_is_safe() -> None:
    with pytest.raises(MutationContextRequiredError):
        ActivityService(InMemoryRepositoryStore()).mutate(
            None,
            make_spec(),
            lambda session: None,
        )

    with pytest.raises(ValueError, match="restricted operational data"):
        make_spec(metadata={"chain_of_thought": "hidden model reasoning"})

    with pytest.raises(ValueError, match="restricted operational data"):
        make_spec(summary="Used Bearer abcdefghijklmnop to update the task")


def test_workflow_audit_record_is_typed_safe_and_idempotent() -> None:
    store = InMemoryRepositoryStore()
    service = WorkflowAuditService(store)
    context = make_context(
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        idempotency_key="workflow-audit:evt_update001:interpreted",
    )

    first = service.record(
        context,
        action=WorkflowActivityAction.SITE_UPDATE_INTERPRETED,
        entity_type="site_update",
        entity_id="sup_update001",
        summary="Structured site-update facts were validated and routed.",
        metadata={
            "status": "interpreted",
            "task_fact_count": 1,
            "issue_fact_count": 1,
            "material_fact_count": 1,
            "clarification_count": 0,
        },
    )
    replay = service.record(
        context,
        action=WorkflowActivityAction.SITE_UPDATE_INTERPRETED,
        entity_type="site_update",
        entity_id="sup_update001",
        summary="Structured site-update facts were validated and routed.",
        metadata={
            "status": "interpreted",
            "task_fact_count": 1,
            "issue_fact_count": 1,
            "material_fact_count": 1,
            "clarification_count": 0,
        },
    )

    assert replay.id == first.id
    assert replay.action == "site_update.interpreted"
    assert replay.actor_type is ActorType.SYSTEM
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 1

    with pytest.raises(ValueError, match="workflow audit metadata field"):
        service.record(
            context.model_copy(update={"idempotency_key": "workflow-audit:evt_update001:unsafe"}),
            action=WorkflowActivityAction.SITE_UPDATE_INTERPRETED,
            entity_type="site_update",
            entity_id="sup_update001",
            summary="Unsafe audit attempt.",
            metadata={"raw_prompt": "hidden instruction"},
        )

    with pytest.raises(ValueError, match="status must be a bounded code"):
        service.record(
            context.model_copy(
                update={"idempotency_key": "workflow-audit:evt_update001:raw-status"}
            ),
            action=WorkflowActivityAction.SITE_UPDATE_INTERPRETED,
            entity_type="site_update",
            entity_id="sup_update001",
            summary="Unsafe audit attempt.",
            metadata={"status": "raw transcript text does not belong here"},
        )


def test_semantic_activity_commits_atomically_with_its_domain_mutation() -> None:
    store = InMemoryRepositoryStore()
    task = Task(id="tsk_blockwork", project_id="prj_ridge", title="Blockwork")
    store.repository(Task).create(task)
    context = make_context()
    semantic = workflow_audit_activity(
        context,
        action=WorkflowActivityAction.WORKFLOW_COMPLETED,
        entity_type="agent_run",
        entity_id="run_update001",
        summary="Completed the workflow after supported task mutation.",
        metadata={"status": "completed", "outcome": "succeeded"},
    )
    assert semantic is not None

    result = ActivityService(store).mutate(
        context,
        make_spec(action="task.completed", summary="Completed blockwork."),
        lambda session: session.repository(Task).save(
            session.repository(Task)
            .require("prj_ridge", task.id)
            .model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "completion_percent": Decimal("100"),
                    "actual_completion": NOW,
                }
            ),
            expected_version=0,
        ),
        replay=lambda session, _activity: session.repository(Task).require("prj_ridge", task.id),
        additional_activities=(semantic,),
    )
    replay = ActivityService(store).mutate(
        context,
        make_spec(action="task.completed", summary="Completed blockwork."),
        lambda _session: pytest.fail("duplicate domain mutation was executed"),
        replay=lambda session, _activity: session.repository(Task).require("prj_ridge", task.id),
        additional_activities=(semantic,),
    )

    assert result.duplicate is False
    assert replay.duplicate is True
    assert {activity.action for activity in store.repository(ActivityEvent).list("prj_ridge")} == {
        "task.completed",
        "workflow.completed",
    }
    assert len(store.repository(ActivityEvent).list("prj_ridge")) == 2
