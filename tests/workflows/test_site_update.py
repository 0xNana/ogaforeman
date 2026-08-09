"""Tests for Daily Site Update orchestration."""

from decimal import Decimal

import pytest

from app.agents.interpreter import FakeSiteInterpreter
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import MemberRole, TaskSource, TaskStatus
from app.domain.facts import (
    ExtractedFactSet,
    MaterialQuantityFact,
    TaskCompletionFact,
)
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import ActivityEvent, DailyReport, Material, Task
from app.repositories.context import ContextRepository
from app.repositories.memory import InMemoryRepositoryStore
from app.services.context import ContextService
from app.services.issues import IssueService
from app.services.material_requests import MaterialRequestService
from app.services.materials import MaterialService
from app.services.reports import ReportService
from app.services.site_updates import SiteUpdateService
from app.services.tasks import TaskService
from app.tools.materials import MaterialTools
from app.tools.tasks import TaskTools
from app.workflows.runtime import RuntimeManager
from app.workflows.site_update import run_site_update_workflow


@pytest.mark.asyncio
async def test_canonical_mixed_update_mutates_each_entity_once() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_blockwork123",
            project_id="prj_testproject123",
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            source=TaskSource.MANUAL,
            completion_percent=Decimal("80"),
        )
    )
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id="prj_testproject123",
            name="Cement",
            normalized_name="cement",
            aliases=["cement bags"],
            unit="bags",
            available_quantity=Decimal("25"),
        )
    )
    runtime = RuntimeManager(store)
    interpreter = FakeSiteInterpreter(
        responses={
            "test site update": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="First-floor blockwork",
                        is_completed=True,
                        evidence="First-floor blockwork is done",
                        confidence="high",
                    )
                ],
                materials=[
                    MaterialQuantityFact(
                        material_name="cement bags",
                        quantity=10,
                        unit="bags",
                        evidence="We have 10 bags of cement left",
                        confidence="high",
                    )
                ],
            )
        }
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_testuser123", subject="test"),
        project_id="prj_testproject123",
        role=MemberRole.MANAGER,
    )
    service = SiteUpdateService(
        interpreter=interpreter,
        context_service=ContextService(ContextRepository(store)),
        task_tools=TaskTools(TaskService(store), access),
        material_tools=MaterialTools(MaterialService(store), access),
        issue_service=IssueService(store),
        material_request_service=MaterialRequestService(store),
        report_service=ReportService(store),
        runtime_manager=runtime,
    )

    result = await run_site_update_workflow(
        site_id="prj_testproject123",
        raw_text="test site update",
        service=service,
        runtime=runtime,
        access=access,
    )

    task = store.repository(Task).require("prj_testproject123", "tsk_blockwork123")
    material = store.repository(Material).require("prj_testproject123", "mat_cement123")
    activities = store.repository(ActivityEvent).list("prj_testproject123")
    ledger = store.repository(MaterialLedgerEntry).list("prj_testproject123")

    assert result["status"] == "completed"
    assert result["tasks_updated"] == 1
    assert result["materials_updated"] == 1
    assert task.status is TaskStatus.COMPLETED
    assert material.available_quantity == Decimal("10")
    assert len(activities) == 3
    assert len(ledger) == 1
    assert len(store.repository(DailyReport).list("prj_testproject123")) == 1


@pytest.mark.asyncio
async def test_unknown_task_pauses_for_clarification_without_mutation() -> None:
    store = InMemoryRepositoryStore()
    runtime = RuntimeManager(store)
    interpreter = FakeSiteInterpreter(
        responses={
            "unknown work": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="North retaining wall",
                        is_completed=True,
                        evidence="North retaining wall is done",
                        confidence="high",
                    )
                ]
            )
        }
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_testuser123", subject="test"),
        project_id="prj_testproject123",
        role=MemberRole.MANAGER,
    )
    service = SiteUpdateService(
        interpreter=interpreter,
        context_service=ContextService(ContextRepository(store)),
        task_tools=TaskTools(TaskService(store), access),
        material_tools=MaterialTools(MaterialService(store), access),
        issue_service=IssueService(store),
        material_request_service=MaterialRequestService(store),
        report_service=ReportService(store),
        runtime_manager=runtime,
    )

    result = await run_site_update_workflow(
        site_id="prj_testproject123",
        raw_text="unknown work",
        service=service,
        runtime=runtime,
        access=access,
    )

    assert result["status"] == "paused"
    assert result["has_clarifications"] is True
    assert result["tasks_updated"] == 0
    assert {
        activity.action for activity in store.repository(ActivityEvent).list("prj_testproject123")
    } == {"report.projected"}
