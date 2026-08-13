import json
from decimal import Decimal

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    ApprovalActionType,
    ApprovalStatus,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MemberRole,
    Severity,
    TaskStatus,
)
from app.domain.facts import ExtractedFactSet, TaskCompletionFact
from app.domain.models import Approval, Issue, Material, Task
from app.repositories.context import ContextRepository, ProjectContext
from app.repositories.memory import InMemoryRepositoryStore
from app.services.site_updates import (
    _guard_visual_task_completions,
    _project_context_prompt,
)


def test_visual_completion_requires_traceable_text_corroboration() -> None:
    facts = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                task_name="Ground-floor blockwork",
                is_completed=True,
                evidence="The visible wall appears complete.",
                confidence="high",
            )
        ]
    )

    guarded = _guard_visual_task_completions(
        facts,
        "The electrician did not come today.",
    )

    assert guarded.tasks[0].clarification_needed is not None
    assert str(guarded.tasks[0].confidence) == "medium"


def test_visual_completion_can_use_explicit_text_evidence() -> None:
    facts = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                task_name="Ground-floor blockwork",
                is_completed=True,
                evidence="Ground-floor blockwork is complete.",
                confidence="high",
            )
        ]
    )

    guarded = _guard_visual_task_completions(
        facts,
        "Ground-floor blockwork is complete. Photo attached.",
    )

    assert guarded.tasks[0].clarification_needed is None
    assert str(guarded.tasks[0].confidence) == "high"


def test_model_project_context_is_bounded_without_limiting_resolution_context() -> None:
    oversized_dependencies = [f"tsk_dependency{i:05d}" for i in range(10_000)]
    tasks = (
        Task(
            id="tsk_oversized123",
            project_id="prj_context123",
            title="Oversized task",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("10"),
            dependency_ids=oversized_dependencies,
        ),
        Task(
            id="tsk_afteroversized123",
            project_id="prj_context123",
            title="Task outside the model projection",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("20"),
        ),
    )
    materials = (
        Material(
            id="mat_cement123",
            project_id="prj_context123",
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("10"),
        ),
    )
    context = ProjectContext(
        project_id="prj_context123",
        active_tasks=tasks,
        materials=materials,
        open_issues=(),
        pending_approvals=(),
    )

    encoded = _project_context_prompt(context)
    projected = json.loads(encoded)

    assert len(encoded) <= 100_000
    assert projected["project_id"] == "prj_context123"
    assert [task["id"] for task in projected["tasks"]] == ["tsk_afteroversized123"]
    assert projected["materials"][0]["id"] == "mat_cement123"
    assert len(context.active_tasks) == 2


def test_golden_context_repository_returns_open_issues_and_pending_approvals() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Issue).create(
        Issue(
            id="iss_open123",
            project_id="prj_context123",
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrical is blocked.",
            status=IssueStatus.OPEN,
            detected_by=IssueDetectedBy.SITE_UPDATE,
        )
    )
    store.repository(Approval).create(
        Approval(
            id="apr_pending123",
            project_id="prj_context123",
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"quantity": 30},
            reason="Cement shortage",
            status=ApprovalStatus.PENDING,
            requested_by="system",
        )
    )
    project_access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_viewer123", subject="viewer"),
        project_id="prj_context123",
        role=MemberRole.VIEWER,
    )

    context = ContextRepository(store).get_bounded_context(project_access)

    assert [issue.id for issue in context.open_issues] == ["iss_open123"]
    assert [approval.id for approval in context.pending_approvals] == ["apr_pending123"]
