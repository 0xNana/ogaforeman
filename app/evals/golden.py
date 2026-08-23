"""Live Golden Scenario evaluation through the production operational boundary."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.interpreter import SiteInterpreter
from app.agents.event_execution import DeliveryDelayEventExecutor
from app.config.settings import Settings
from app.prompts import PromptId, prompt_registry
from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalActionType,
    ApprovalStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    Severity,
    SiteUpdateInputType,
    TaskStatus,
    TaskSource,
    WorkflowName,
)
from app.domain.events import EventType, ProjectEvent
from app.domain.facts import (
    ExtractedFactSet,
    IssueFact,
    MaterialQuantityFact,
    NextFocusFact,
    TaskCompletionFact,
)
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    Project,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.repositories.context import ContextRepository
from app.repositories.memory import InMemoryRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.services.context import ContextService
from app.infrastructure.notification_gateway import NotificationProvider
from app.services.issues import IssueService
from app.services.material_requests import MaterialRequestService
from app.services.materials import MaterialService
from app.services.reports import ReportService
from app.services.site_update_lifecycle import SiteUpdateExecutionStateService
from app.services.site_updates import SiteUpdateService
from app.services.tasks import TaskService
from app.services.workflow_audit import WorkflowAuditService
from app.tools.materials import MaterialTools
from app.tools.tasks import TaskTools


GOLDEN_DATASET_VERSION = "golden-operational-v1"
GOLDEN_PROMPT_VERSION = (
    f"site-report-{prompt_registry.get_prompt_config(PromptId.SITE_REPORT).prompt_version}"
)
GOLDEN_UPDATE_TEXT = (
    "First-floor blockwork is complete. The electrician did not come today. "
    "We have 10 bags of cement left. Plastering starts tomorrow."
)
GOLDEN_CHECK_IDS = (
    "blockwork_completion",
    "electrical_blocker",
    "cement_inventory",
    "cement_requirement",
    "shortage_90_bags",
    "material_request",
    "approval",
    "delivery_delay",
)

_PROJECT_ID = "prj_goldeneval123"
_FOREMAN_ID = "usr_goldenforeman123"
_MANAGER_ID = "usr_goldenmanager123"
_BLOCKWORK_ID = "tsk_goldenblockwork123"
_ELECTRICAL_ID = "tsk_goldenelectrical123"
_PLASTERING_ID = "tsk_goldenplastering123"
_CEMENT_ID = "mat_goldencement123"
_UPDATE_ID = "sup_goldensiteupdate123"
_EVENT_ID = "evt_goldensiteupdate123"
_RUN_ID = "run_goldensiteupdate123"
_NOW = datetime(2026, 8, 3, 10, tzinfo=UTC)


class GoldenCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    passed: bool
    evidence: str


class GoldenMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_pass_rate: float
    canonical_entity_resolution_accuracy: float


class GoldenEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    prompt_version: str
    adapter: str
    backend: str
    model_id: str | None = None
    cloud_project: str | None = None
    cloud_location: str | None = None
    commit_sha: str
    source_tree_dirty: bool
    generated_at: datetime
    passed: bool
    metrics: GoldenMetrics
    checks: list[GoldenCheck]


def golden_fixture_fact_set() -> ExtractedFactSet:
    """Return the locked extraction expected from the canonical site update."""

    return ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                task_name="First-floor blockwork",
                is_completed=True,
                evidence="First-floor blockwork is complete",
                confidence="high",
            )
        ],
        issues=[
            IssueFact(
                issue_type=IssueType.BLOCKER,
                task_name="Electrical rough-in",
                description="The electrician did not come today.",
                severity=Severity.HIGH,
                evidence="The electrician did not come today",
                confidence="high",
            )
        ],
        materials=[
            MaterialQuantityFact(
                material_name="Cement Bags",
                quantity=10,
                unit="bags",
                evidence="We have 10 bags of cement left",
                confidence="high",
            )
        ],
        next_focus=[
            NextFocusFact(
                task_name="First-floor plastering",
                description="First-floor plastering starts tomorrow.",
                evidence="Plastering starts tomorrow",
                confidence="high",
            )
        ],
    )


async def run_golden_evaluation(
    interpreter: SiteInterpreter,
    *,
    adapter: str,
    model_id: str | None,
    backend: str,
    cloud_project: str | None = None,
    cloud_location: str | None = None,
    settings: Settings | None = None,
    notification_gateway: NotificationProvider,
) -> GoldenEvalReport:
    """Run one live extraction through deterministic production services."""

    store = InMemoryRepositoryStore()
    foreman_access, manager_access = _seed_golden_project(store)
    lifecycle = SiteUpdateExecutionStateService(store)
    lifecycle.start_attempt(
        foreman_access,
        _UPDATE_ID,
        source_event_id=_EVENT_ID,
        run_id=_RUN_ID,
        trace_id=_EVENT_ID,
        attempt=1,
        adk_session_id="golden-eval/run_goldensiteupdate123-attempt-1",
        adk_invocation_id=_EVENT_ID,
        adk_workflow_id="daily_site_update_workflow",
    )
    site_update = store.repository(SiteUpdate).require(_PROJECT_ID, _UPDATE_ID)
    service = SiteUpdateService(
        interpreter=interpreter,
        context_service=ContextService(ContextRepository(store)),
        task_tools=TaskTools(TaskService(store), foreman_access),
        material_tools=MaterialTools(MaterialService(store), foreman_access),
        issue_service=IssueService(store),
        material_request_service=MaterialRequestService(store),
        report_service=ReportService(store),
        workflow_audit=WorkflowAuditService(store),
    )

    try:
        result = await service.process_update(
            access=foreman_access,
            site_update=site_update,
            run_id=_RUN_ID,
            trace_id=_EVENT_ID,
            source_event_id=_EVENT_ID,
        )
    except Exception as exc:
        return _failed_execution_report(
            adapter=adapter,
            model_id=model_id,
            backend=backend,
            cloud_project=cloud_project,
            cloud_location=cloud_location,
            error_code=type(exc).__name__,
        )

    if result.has_pending_approvals:
        lifecycle.wait_for_approval(
            foreman_access,
            _UPDATE_ID,
            source_event_id=_EVENT_ID,
            run_id=_RUN_ID,
            trace_id=_EVENT_ID,
            attempt=1,
            step="approval_required",
            result_summary=result.summary,
            pending_actions=result.pending_actions,
        )

    tasks = {task.id: task for task in store.repository(Task).list(_PROJECT_ID)}
    material = store.repository(Material).require(_PROJECT_ID, _CEMENT_ID)
    issues = store.repository(Issue).list(_PROJECT_ID)
    requests = store.repository(MaterialRequest).list(_PROJECT_ID)
    approvals = store.repository(Approval).list(_PROJECT_ID)
    reports = store.repository(DailyReport).list(_PROJECT_ID)

    blockwork_ok = tasks[_BLOCKWORK_ID].status is TaskStatus.COMPLETED and tasks[
        _BLOCKWORK_ID
    ].completion_percent == Decimal("100")
    electrical_blockers = [
        issue
        for issue in issues
        if issue.type is IssueType.BLOCKER and issue.task_ids == [_ELECTRICAL_ID]
    ]
    follow_ups = [
        task
        for task in tasks.values()
        if task.source is TaskSource.SITE_UPDATE and _ELECTRICAL_ID in task.source_refs
    ]
    electrical_ok = len(electrical_blockers) == 1 and len(follow_ups) == 1
    inventory_ok = material.available_quantity == Decimal("10")
    focus_ids = {
        str(fact.metadata.get("task_id"))
        for report in reports
        for fact in report.next_focus
        if fact.metadata.get("task_id")
    }
    requirement_ok = (
        material.upcoming_requirement_quantity == Decimal("100") and _PLASTERING_ID in focus_ids
    )
    request = requests[0] if len(requests) == 1 else None
    shortage_ok = (
        request is not None
        and request.material_id == _CEMENT_ID
        and request.quantity == Decimal("90")
        and request.unit == "bags"
    )
    request_ok = (
        request is not None
        and request.status is MaterialRequestStatus.AWAITING_APPROVAL
        and result.material_requests_created == 1
    )
    approval = approvals[0] if len(approvals) == 1 else None
    approval_ok = (
        approval is not None
        and request is not None
        and approval.action_type is ApprovalActionType.PURCHASE
        and approval.status is ApprovalStatus.PENDING
        and request.approval_id == approval.id
        and result.has_pending_approvals
        and not any(
            activity.action == "material_request.submitted"
            for activity in store.repository(ActivityEvent).list(_PROJECT_ID)
        )
    )

    delivery_ok = False
    delivery_evidence = "No canonical approved request was available for the delay check."
    if approval_ok and approval is not None and request is not None:
        try:
            decision_at = datetime.now(UTC)
            approval_result = ApprovalService(store).approve(
                manager_access,
                ResolutionCommand(
                    project_id=_PROJECT_ID,
                    approval_id=approval.id,
                    expected_version=approval.version,
                    notes="Golden Scenario approval.",
                    occurred_at=decision_at,
                ),
                MutationContext(
                    project_id=_PROJECT_ID,
                    actor_type=ActorType.USER,
                    actor_id=_MANAGER_ID,
                    source_event_id=_EVENT_ID,
                    agent_run_id=_RUN_ID,
                    idempotency_key="golden:approval:decision",
                    occurred_at=decision_at,
                ),
            )
            _approval_event(store, approval_result.approval.id)
            delay_event = ProjectEvent(
                event_id="evt_goldendelivery123",
                project_id=_PROJECT_ID,
                event_type=EventType.DELIVERY_DELAYED,
                source="web",
                occurred_at=decision_at,
                received_at=decision_at,
                actor={"type": "user", "id": _MANAGER_ID},
                idempotency_key="golden:operator:delivery-delay",
                correlation_id=_EVENT_ID,
                payload={
                    "request_id": request.id,
                    "new_date": (decision_at + timedelta(days=5)).date().isoformat(),
                    "reason": "Supplier reported that inventory is delayed.",
                },
            )
            await DeliveryDelayEventExecutor(
                store,
                settings or Settings(_env_file=None),
                notification_gateway,
            ).execute(delay_event)
            delayed_request = store.repository(MaterialRequest).require(_PROJECT_ID, request.id)
            delivery_ok = (
                delay_event is not None
                and delayed_request.status is MaterialRequestStatus.DELAYED
                and any(
                    issue.type is IssueType.DELAY_RISK
                    and delay_event.event_id in issue.evidence_refs
                    for issue in store.repository(Issue).list(_PROJECT_ID)
                )
                and any(
                    activity.action == "material_request.delayed"
                    and activity.entity_id == request.id
                    for activity in store.repository(ActivityEvent).list(_PROJECT_ID)
                )
            )
            delivery_evidence = (
                f"request={request.id}; status={delayed_request.status.value}; "
                f"event={delay_event.event_id if delay_event else 'missing'}"
            )
        except Exception as exc:
            location = ""
            if isinstance(exc, ValidationError) and exc.errors():
                first_error = exc.errors()[0]
                location = (
                    "; field="
                    + ".".join(str(item) for item in first_error["loc"])
                    + "; reason="
                    + str(first_error["msg"])[:200]
                )
            delivery_evidence = f"delivery_path_error={type(exc).__name__}{location}"

    checks = [
        GoldenCheck(
            id="blockwork_completion",
            passed=blockwork_ok,
            evidence=f"task={_BLOCKWORK_ID}; status={tasks[_BLOCKWORK_ID].status.value}",
        ),
        GoldenCheck(
            id="electrical_blocker",
            passed=electrical_ok,
            evidence=(
                f"task={_ELECTRICAL_ID}; blockers={len(electrical_blockers)}; "
                f"follow_ups={len(follow_ups)}"
            ),
        ),
        GoldenCheck(
            id="cement_inventory",
            passed=inventory_ok,
            evidence=f"material={_CEMENT_ID}; on_hand={material.available_quantity} bags",
        ),
        GoldenCheck(
            id="cement_requirement",
            passed=requirement_ok,
            evidence=(
                f"material={_CEMENT_ID}; required={material.upcoming_requirement_quantity} "
                f"bags; focus={_PLASTERING_ID in focus_ids}"
            ),
        ),
        GoldenCheck(
            id="shortage_90_bags",
            passed=shortage_ok,
            evidence=f"request_quantity={request.quantity if request else 'missing'} bags",
        ),
        GoldenCheck(
            id="material_request",
            passed=request_ok,
            evidence=(
                f"requests={len(requests)}; status={request.status.value if request else 'missing'}"
            ),
        ),
        GoldenCheck(
            id="approval",
            passed=approval_ok,
            evidence=(
                f"approvals={len(approvals)}; "
                f"status={approval.status.value if approval else 'missing'}; "
                "external_submission_before_decision=false"
            ),
        ),
        GoldenCheck(
            id="delivery_delay",
            passed=delivery_ok,
            evidence=delivery_evidence,
        ),
    ]
    canonical_checks = (
        blockwork_ok,
        bool(electrical_blockers),
        inventory_ok,
        _PLASTERING_ID in focus_ids,
        request is not None and request.material_id == _CEMENT_ID,
    )
    return _report(
        adapter=adapter,
        model_id=model_id,
        backend=backend,
        cloud_project=cloud_project,
        cloud_location=cloud_location,
        checks=checks,
        canonical_accuracy=sum(canonical_checks) / len(canonical_checks),
    )


def _seed_golden_project(
    store: InMemoryRepositoryStore,
) -> tuple[ProjectAccessContext, ProjectAccessContext]:
    store.repository(Project).create(
        Project(
            id=_PROJECT_ID,
            name="Golden Ridge Site",
            location="Accra",
            timezone="Africa/Accra",
            created_by=_MANAGER_ID,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    for user_id, role in (
        (_FOREMAN_ID, MemberRole.FOREMAN),
        (_MANAGER_ID, MemberRole.MANAGER),
    ):
        store.repository(ProjectMember).create(
            ProjectMember(
                project_id=_PROJECT_ID,
                user_id=user_id,
                role=role,
                status=MemberStatus.ACTIVE,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    for task in (
        Task(
            id=_BLOCKWORK_ID,
            project_id=_PROJECT_ID,
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
            updated_at=_NOW,
        ),
        Task(
            id=_ELECTRICAL_ID,
            project_id=_PROJECT_ID,
            title="Electrical rough-in",
            status=TaskStatus.PLANNED,
            assigned_to="usr_goldenelectrician123",
            dependency_ids=[_BLOCKWORK_ID],
            created_at=_NOW,
            updated_at=_NOW,
        ),
        Task(
            id=_PLASTERING_ID,
            project_id=_PROJECT_ID,
            title="First-floor plastering",
            status=TaskStatus.PLANNED,
            dependency_ids=[_BLOCKWORK_ID, _ELECTRICAL_ID],
            planned_start=_NOW + timedelta(days=1),
            created_at=_NOW,
            updated_at=_NOW,
        ),
    ):
        store.repository(Task).create(task)
    store.repository(Material).create(
        Material(
            id=_CEMENT_ID,
            project_id=_PROJECT_ID,
            name="Cement Bags",
            normalized_name="cement bags",
            aliases=["cement"],
            unit="bags",
            available_quantity=Decimal("25"),
            minimum_required_quantity=Decimal("20"),
            upcoming_requirement_quantity=Decimal("100"),
            default_supplier="Golden supplier",
            updated_at=_NOW,
        )
    )
    store.repository(SiteUpdate).create(
        SiteUpdate(
            id=_UPDATE_ID,
            project_id=_PROJECT_ID,
            submitted_by=_FOREMAN_ID,
            input_type=SiteUpdateInputType.TEXT,
            raw_text=GOLDEN_UPDATE_TEXT,
            client_event_id="golden-live-eval-v1",
            submitted_at=_NOW,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    store.repository(AgentRun).create(
        AgentRun(
            id=_RUN_ID,
            project_id=_PROJECT_ID,
            trigger_event_id=_EVENT_ID,
            workflow=WorkflowName.DAILY_SITE_UPDATE,
            status=AgentRunStatus.RUNNING,
            step="interpretation",
            trace_id=_EVENT_ID,
            started_at=_NOW,
            updated_at=_NOW,
        )
    )
    store.repository(ActivityEvent).create(
        ActivityEvent(
            id="act_goldensiteupdate123",
            project_id=_PROJECT_ID,
            actor_type=ActorType.USER,
            actor_id=_FOREMAN_ID,
            action="site_update.received",
            entity_type="site_update",
            entity_id=_UPDATE_ID,
            summary="Received the Golden Scenario site update.",
            source_event_id=_EVENT_ID,
            agent_run_id=_RUN_ID,
            created_at=_NOW,
        )
    )
    return (
        ProjectAccessContext(
            actor=AuthenticatedUser(user_id=_FOREMAN_ID, subject="golden-eval-foreman"),
            project_id=_PROJECT_ID,
            role=MemberRole.FOREMAN,
        ),
        ProjectAccessContext(
            actor=AuthenticatedUser(user_id=_MANAGER_ID, subject="golden-eval-manager"),
            project_id=_PROJECT_ID,
            role=MemberRole.MANAGER,
        ),
    )


def _approval_event(store: InMemoryRepositoryStore, approval_id: str) -> ProjectEvent:
    matches = [
        message
        for message in store.repository(OutboxMessage).list(_PROJECT_ID)
        if message.message_type == EventType.APPROVAL_GRANTED.value
        and message.payload.get("payload", {}).get("approval_id") == approval_id
    ]
    if len(matches) != 1:
        raise RuntimeError("approval decision did not emit one continuation event")
    return ProjectEvent.model_validate(matches[0].payload)


def _failed_execution_report(
    *,
    adapter: str,
    model_id: str | None,
    backend: str,
    cloud_project: str | None,
    cloud_location: str | None,
    error_code: str,
) -> GoldenEvalReport:
    return _report(
        adapter=adapter,
        model_id=model_id,
        backend=backend,
        cloud_project=cloud_project,
        cloud_location=cloud_location,
        checks=[
            GoldenCheck(id=check_id, passed=False, evidence=f"execution_error={error_code}")
            for check_id in GOLDEN_CHECK_IDS
        ],
        canonical_accuracy=0,
    )


def _report(
    *,
    adapter: str,
    model_id: str | None,
    backend: str,
    cloud_project: str | None,
    cloud_location: str | None,
    checks: list[GoldenCheck],
    canonical_accuracy: float,
) -> GoldenEvalReport:
    pass_rate = sum(check.passed for check in checks) / len(GOLDEN_CHECK_IDS)
    source_tree_dirty = _worktree_dirty()
    return GoldenEvalReport(
        dataset_version=GOLDEN_DATASET_VERSION,
        prompt_version=GOLDEN_PROMPT_VERSION,
        adapter=adapter,
        backend=backend,
        model_id=model_id,
        cloud_project=cloud_project,
        cloud_location=cloud_location,
        commit_sha=_commit_sha(),
        source_tree_dirty=source_tree_dirty,
        generated_at=datetime.now(UTC),
        passed=(
            len(checks) == len(GOLDEN_CHECK_IDS)
            and tuple(check.id for check in checks) == GOLDEN_CHECK_IDS
            and pass_rate == 1
            and canonical_accuracy == 1
            and (adapter != "gemini" or not source_tree_dirty)
        ),
        metrics=GoldenMetrics(
            case_pass_rate=pass_rate,
            canonical_entity_resolution_accuracy=canonical_accuracy,
        ),
        checks=checks,
    )


def _commit_sha() -> str:
    configured = os.getenv("GITHUB_SHA") or os.getenv("COMMIT_SHA")
    if configured:
        return configured[:40]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()[:40]
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _worktree_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())


__all__ = [
    "GOLDEN_CHECK_IDS",
    "GOLDEN_DATASET_VERSION",
    "GOLDEN_PROMPT_VERSION",
    "GOLDEN_UPDATE_TEXT",
    "GoldenCheck",
    "GoldenEvalReport",
    "GoldenMetrics",
    "golden_fixture_fact_set",
    "run_golden_evaluation",
]
