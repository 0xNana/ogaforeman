"""Durable execution for remaining project-event routes that do not require interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectForbiddenError,
    ProjectPermission,
    authorize_project_member,
    ensure_permission,
)
from app.domain.enums import (
    ActorType,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    Severity,
    TaskStatus,
    WorkflowName,
)
from app.domain.events import EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    DailyReport,
    Approval,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    OutboxStatus,
    Project,
    ProjectMember,
    ReportFact,
    ReportStatus,
    Task,
)
from app.domain.policies import ensure_material_request_transition
from app.repositories.interfaces import EntityNotFoundError, RepositorySession, RepositoryStore
from app.services.activity import ActivityService
from app.services.issues import CreateIssueCommand, IssueService
from app.services.material_requests import MaterialRequestService, MaterialShortageCommand
from app.services.outbox import OutboxService
from app.services.schedule_impact import calculate_impact
from app.services.tasks import TaskService, UpdateTaskCommand
from app.services.tasks import CreateDeliveryFollowUpCommand
from app.domain.models import AgentRun
from app.domain.enums import AgentRunStatus
from app.repositories.runs import AgentRunRepository, run_id_for_event
from app.repositories.activity import ActivityRepository
from app.repositories.membership import AuthorizedProjectRepository
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class RoutedEventExecution:
    run_id: str
    result_ref: str
    waiting_for_approval: bool = False


@dataclass(frozen=True, slots=True)
class DeliveryDelayContext:
    project: Project
    request: MaterialRequest
    material: Material
    tasks: tuple[Task, ...]
    directly_affected_task_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeliveryDelayAssessment:
    affected_task_ids: tuple[str, ...]
    severity: Severity


class TypedEventService:
    """Apply one already-claimed event through typed, replay-safe services."""

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

        self._activities = ActivityService(store)

    def execute(self, event: ProjectEvent) -> RoutedEventExecution:
        workflow = {
            EventType.TASK_COMPLETED: WorkflowName.DAILY_SITE_UPDATE,
            EventType.MATERIAL_LOW: WorkflowName.MATERIAL_SHORTAGE,
            EventType.MATERIAL_REQUESTED: WorkflowName.MATERIAL_SHORTAGE,
            EventType.TASK_BLOCKED: WorkflowName.BLOCKER_DELAY,
            EventType.TASK_OVERDUE: WorkflowName.BLOCKER_DELAY,
            EventType.DAILY_BRIEF_REQUESTED: WorkflowName.DAILY_BRIEF,
        }.get(event.event_type)
        if workflow is None:
            raise ValueError(f"routed event executor does not support {event.event_type.value}")

        access = self._authorize(event)
        run_id = run_id_for_event(event.event_id)
        self._start_run(
            project_id=event.project_id,
            trigger_event_id=event.event_id,
            workflow=workflow,
            run_id=run_id,
            trace_id=str(event.metadata.get("trace_id") or event.correlation_id),
        )

        try:
            result_ref, wait_for_approval = self._execute_route(event, access, run_id)
            if wait_for_approval:
                self._pause_for_approval(
                    event.project_id,
                    run_id,
                    "approval_required",
                )
            else:
                self._complete_run(event.project_id, run_id)
        except Exception as exc:
            self._fail_run(
                event.project_id,
                run_id,
                type(exc).__name__[:128],
                str(exc)[:5_000] or "routed workflow execution failed",
            )
            raise

        return RoutedEventExecution(
            run_id=run_id,
            result_ref=result_ref,
            waiting_for_approval=wait_for_approval,
        )

    def start_delivery_delay(self, event: ProjectEvent) -> tuple[ProjectAccessContext, str]:
        if event.event_type is not EventType.DELIVERY_DELAYED:
            raise ValueError("delivery delay workflow requires DELIVERY_DELAYED")
        if event.source is not EventSource.WEB or event.actor.type is not EventActorType.USER:
            raise ProjectForbiddenError("delivery delay requires the authenticated operator intake")
        access = self._authorize(event)
        ensure_permission(access, ProjectPermission.OPERATE)
        run_id = run_id_for_event(event.event_id)
        self._start_run(
            project_id=event.project_id,
            trigger_event_id=event.event_id,
            workflow=WorkflowName.BLOCKER_DELAY,
            run_id=run_id,
            trace_id=str(event.metadata.get("trace_id") or event.correlation_id),
        )
        return access, run_id

    def retrieve_delivery_delay_context(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
    ) -> DeliveryDelayContext:
        ensure_permission(access, ProjectPermission.OPERATE)
        project = AuthorizedProjectRepository(self._store.repository(Project), access).require(
            event.project_id, event.project_id
        )
        request = AuthorizedProjectRepository(
            self._store.repository(MaterialRequest), access
        ).require(event.project_id, str(event.payload["request_id"]))
        material = AuthorizedProjectRepository(self._store.repository(Material), access).require(
            event.project_id, request.material_id
        )
        affected: tuple[str, ...] = ()
        if request.approval_id:
            approval = AuthorizedProjectRepository(
                self._store.repository(Approval), access
            ).require(event.project_id, request.approval_id)
            raw_ids = approval.proposed_action.get("affected_task_ids", [])
            if isinstance(raw_ids, list):
                affected = tuple(dict.fromkeys(str(value) for value in raw_ids))
        tasks = tuple(
            AuthorizedProjectRepository(self._store.repository(Task), access).list(event.project_id)
        )
        self._require_task_ids(list(tasks), list(affected))
        return DeliveryDelayContext(
            project=project,
            request=request,
            material=material,
            tasks=tasks,
            directly_affected_task_ids=affected,
        )

    @staticmethod
    def assess_delivery_delay(context: DeliveryDelayContext) -> DeliveryDelayAssessment:
        affected = tuple(
            sorted(calculate_impact(context.tasks, list(context.directly_affected_task_ids)))
        )
        severity = Severity.HIGH if affected else Severity.MEDIUM
        return DeliveryDelayAssessment(affected_task_ids=affected, severity=severity)

    def mark_delivery_delayed(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> MaterialRequest:
        request_id = str(event.payload["request_id"])
        result = self._activities.mutate(
            self._context(event, run_id, f"delivery-delayed:{request_id}"),
            ActivitySpec(
                action="material_request.delayed",
                entity_type="material_request",
                entity_id=request_id,
                summary="A material delivery delay was reported.",
                metadata={
                    "new_date": str(event.payload["new_date"]),
                    "reason_digest": sha256(
                        str(event.payload["reason"]).encode("utf-8")
                    ).hexdigest()[:16],
                },
            ),
            lambda session: self._mark_request_delayed(
                session,
                event,
                request_id,
                access,
            ),
            replay=lambda session, _activity: AuthorizedProjectRepository(
                session.repository(MaterialRequest),
                access,
            ).require(event.project_id, request_id),
        )
        if result.value is None:
            raise RuntimeError("delivery delay did not resolve its material request")
        return result.value

    def create_delivery_delay_risk(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
        assessment: DeliveryDelayAssessment,
    ) -> Issue:
        request_id = str(event.payload["request_id"])
        return (
            IssueService(self._store)
            .create_issue(
                access,
                CreateIssueCommand(
                    project_id=event.project_id,
                    issue_type=IssueType.DELAY_RISK,
                    severity=assessment.severity,
                    description=(
                        f"Material request {request_id} moved to "
                        f"{event.payload['new_date']}: {event.payload['reason']}"
                    ),
                    evidence_refs=[event.event_id],
                    task_ids=list(assessment.affected_task_ids),
                    detected_by=IssueDetectedBy.DELIVERY_EVENT,
                    occurred_at=event.occurred_at,
                ),
                self._context(event, run_id, "delivery-delay-issue"),
            )
            .issue
        )

    def create_delivery_delay_follow_up(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
        assessment: DeliveryDelayAssessment,
        issue: Issue,
    ) -> Task:
        return (
            TaskService(self._store)
            .create_delivery_follow_up(
                access,
                CreateDeliveryFollowUpCommand(
                    project_id=event.project_id,
                    material_request_id=str(event.payload["request_id"]),
                    source_issue_id=issue.id,
                    source_event_id=event.event_id,
                    affected_task_ids=assessment.affected_task_ids,
                    occurred_at=event.occurred_at,
                ),
                self._context(event, run_id, "delivery-delay-follow-up"),
            )
            .task
        )

    def complete_delivery_delay(
        self, project_id: str, run_id: str, issue_id: str
    ) -> RoutedEventExecution:
        self._complete_run(project_id, run_id)
        return RoutedEventExecution(run_id=run_id, result_ref=f"issue:{issue_id}")

    def fail_delivery_delay(self, project_id: str, run_id: str, exc: Exception) -> None:
        self._fail_run(
            project_id,
            run_id,
            type(exc).__name__[:128],
            str(exc)[:5_000] or "delivery delay workflow failed",
        )

    def _start_run(
        self,
        project_id: str,
        trigger_event_id: str,
        workflow: WorkflowName,
        run_id: str,
        trace_id: str,
    ) -> AgentRun:
        def _start(session: RepositorySession) -> AgentRun:
            now = datetime.now(UTC)
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.get(project_id, run_id)
            should_create = False
            should_save = False
            activity_phase: str | None = None
            activity_action: str | None = None
            activity_summary: str | None = None
            if run is None:
                run = AgentRun(
                    id=run_id,
                    project_id=project_id,
                    trigger_event_id=trigger_event_id,
                    workflow=workflow,
                    trace_id=trace_id,
                    adk_session_id=f"event-{trigger_event_id}",
                    adk_invocation_id=trigger_event_id,
                    adk_workflow_id=workflow.value,
                    status=AgentRunStatus.RUNNING,
                    started_at=now,
                    updated_at=now,
                )
                should_create = True
                activity_phase = "started"
                activity_action = "agent_run.started"
                activity_summary = "Started an agent workflow run."
            elif run.status in {
                AgentRunStatus.QUEUED,
                AgentRunStatus.WAITING_FOR_APPROVAL,
                AgentRunStatus.WAITING_FOR_CLARIFICATION,
            }:
                run = run.model_copy(update={"status": AgentRunStatus.RUNNING, "updated_at": now})
                should_save = True
                activity_phase = "resumed"
                activity_action = "agent_run.resumed"
                activity_summary = "Resumed an agent workflow run."
            elif run.status is AgentRunStatus.FAILED:
                run = run.model_copy(
                    update={
                        "status": AgentRunStatus.RUNNING,
                        "attempt": run.attempt + 1,
                        "completed_at": None,
                        "error_code": None,
                        "error_summary": None,
                        "updated_at": now,
                    }
                )
                should_save = True
                activity_phase = "retried"
                activity_action = "agent_run.retried"
                activity_summary = "Retried a failed agent workflow run."
            activity: ActivityEvent | None = None
            existing_activity: ActivityEvent | None = None
            if activity_phase and activity_action and activity_summary:
                activity = self._build_run_activity(
                    run,
                    phase=activity_phase,
                    action=activity_action,
                    summary=activity_summary,
                )
                existing_activity = session.repository(ActivityEvent).get(
                    run.project_id, activity.id
                )
                if existing_activity is not None:
                    ActivityRepository.ensure_replay_matches(existing_activity, activity)
            if should_create:
                run = run_repo.create(run)
            elif should_save:
                run = run_repo.save(run, expected_version=run.version)
            if activity is not None and existing_activity is None:
                session.repository(ActivityEvent).create(activity)
            return run

        return AgentRunRepository(self._store).run_transaction(_start)

    def _pause_for_approval(self, project_id: str, run_id: str, step: str) -> AgentRun:
        def _pause(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            run = run.model_copy(
                update={
                    "status": AgentRunStatus.WAITING_FOR_APPROVAL,
                    "step": step,
                    "updated_at": datetime.now(UTC),
                }
            )
            activity = self._build_run_activity(
                run,
                phase="paused",
                action="agent_run.paused",
                summary="Paused an agent workflow run for approval.",
            )
            existing_activity = session.repository(ActivityEvent).get(project_id, activity.id)
            if existing_activity is not None:
                ActivityRepository.ensure_replay_matches(existing_activity, activity)
            saved = run_repo.save(run, expected_version=run.version)
            if existing_activity is None:
                session.repository(ActivityEvent).create(activity)
            return saved

        return AgentRunRepository(self._store).run_transaction(_pause)

    def _complete_run(self, project_id: str, run_id: str) -> AgentRun:
        def _complete(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            if run.status is AgentRunStatus.COMPLETED:
                return run
            completed_at = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": AgentRunStatus.COMPLETED,
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                }
            )
            activity = self._build_run_activity(
                run,
                phase="completed",
                action="agent_run.completed",
                summary="Completed an agent workflow run.",
            )
            existing_activity = session.repository(ActivityEvent).get(project_id, activity.id)
            if existing_activity is not None:
                ActivityRepository.ensure_replay_matches(existing_activity, activity)
            saved = run_repo.save(run, expected_version=run.version)
            if existing_activity is None:
                session.repository(ActivityEvent).create(activity)
            return saved

        return AgentRunRepository(self._store).run_transaction(_complete)

    def _fail_run(
        self, project_id: str, run_id: str, error_code: str, error_summary: str
    ) -> AgentRun:
        def _fail(session: RepositorySession) -> AgentRun:
            run_repo = AgentRunRepository.for_session(session)
            run = run_repo.require(project_id, run_id)
            if run.status is AgentRunStatus.COMPLETED:
                return run
            completed_at = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": AgentRunStatus.FAILED,
                    "error_code": error_code,
                    "error_summary": error_summary,
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                }
            )
            activity = self._build_run_activity(
                run,
                phase=f"failed-{run.attempt}",
                action="agent_run.failed",
                summary="An agent workflow run failed.",
                error_code=error_code,
            )
            existing_activity = session.repository(ActivityEvent).get(project_id, activity.id)
            if existing_activity is not None:
                ActivityRepository.ensure_replay_matches(existing_activity, activity)
            saved = run_repo.save(run, expected_version=run.version)
            if existing_activity is None:
                session.repository(ActivityEvent).create(activity)
            return saved

        return AgentRunRepository(self._store).run_transaction(_fail)

    @staticmethod
    def _build_run_activity(
        run: AgentRun,
        *,
        phase: str,
        action: str,
        summary: str,
        error_code: str | None = None,
    ) -> ActivityEvent:
        context = MutationContext(
            project_id=run.project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=run.trigger_event_id,
            agent_run_id=run.id,
            idempotency_key=f"agent-run:{run.id}:{phase}:{run.attempt}",
            occurred_at=run.updated_at,
        )
        metadata: dict[str, object] = {
            "workflow": run.workflow.value,
            "status": run.status.value,
            "attempt": run.attempt,
        }
        if error_code is not None:
            metadata["error_code"] = error_code
        return ActivityRepository.build_event(
            context,
            ActivitySpec(
                action=action,
                entity_type="agent_run",
                entity_id=run.id,
                summary=summary,
                metadata=metadata,
            ),
        )

    def _execute_route(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> tuple[str, bool]:
        if event.event_type is EventType.TASK_COMPLETED:
            return self._complete_task(event, access, run_id), False
        if event.event_type is EventType.MATERIAL_LOW:
            return self._handle_material_low(event, access, run_id)
        if event.event_type is EventType.MATERIAL_REQUESTED:
            return self._observe_material_request(event, access, run_id)
        if event.event_type is EventType.TASK_BLOCKED:
            return self._handle_blocked_task(event, access, run_id), False
        if event.event_type is EventType.TASK_OVERDUE:
            return self._handle_overdue_task(event, access, run_id), False
        if event.event_type is EventType.DAILY_BRIEF_REQUESTED:
            return self._generate_daily_brief(event, access, run_id), False
        raise ValueError(f"unhandled routed event type {event.event_type.value}")

    def _complete_task(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> str:
        evidence_refs = [str(value) for value in event.payload["evidence_refs"]]
        if not evidence_refs:
            raise ValueError("TASK_COMPLETED requires at least one completion evidence reference")
        completion_percent = Decimal(str(event.payload.get("completion_percent", 100)))
        if completion_percent != Decimal("100"):
            raise ValueError("TASK_COMPLETED completion_percent must be 100")
        task_id = str(event.payload["task_id"])
        task = self._store.repository(Task).require(event.project_id, task_id)
        result = TaskService(self._store).complete_task(
            access,
            UpdateTaskCommand(
                project_id=event.project_id,
                task_id=task_id,
                expected_version=task.version,
                completion_percent=completion_percent,
                target_status=TaskStatus.COMPLETED,
                evidence="Completion evidence: " + ", ".join(evidence_refs),
                occurred_at=event.occurred_at,
            ),
            self._context(event, run_id, f"task-completed:{task_id}"),
        )
        return f"task:{result.task.id}"

    def _handle_material_low(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> tuple[str, bool]:
        material_ref = str(event.payload.get("material_ref") or event.payload.get("material_name"))
        reason = str(
            event.payload.get("reason")
            or f"Material stock event {event.event_id} requires shortage evaluation."
        )
        result = MaterialRequestService(self._store).evaluate_shortage(
            access,
            MaterialShortageCommand(
                project_id=event.project_id,
                material_id_or_alias=material_ref,
                required_quantity=Decimal(str(event.payload["quantity"])),
                unit=str(event.payload["unit"]),
                supplier=(
                    str(event.payload["supplier"])
                    if event.payload.get("supplier") is not None
                    else None
                ),
                reason=reason,
                occurred_at=event.occurred_at,
            ),
            self._context(event, run_id, f"material-low:{material_ref}"),
        )
        if result.request is None:
            return f"material:{result.material_id}", False
        return f"material_request:{result.request.id}", True

    def _observe_material_request(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> tuple[str, bool]:
        ensure_permission(access, ProjectPermission.OPERATE)
        request_id = str(event.payload["request_id"])
        context = self._context(event, run_id, f"material-requested:{request_id}")
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="material_request.workflow_observed",
                entity_type="material_request",
                entity_id=request_id,
                summary="Material request entered the durable workflow.",
                metadata={"request_id": request_id},
            ),
            lambda session: session.repository(MaterialRequest).require(
                event.project_id, request_id
            ),
            replay=lambda session, _activity: session.repository(MaterialRequest).require(
                event.project_id, request_id
            ),
        )
        if result.value is None:
            raise RuntimeError("material request event did not resolve persisted state")
        waiting = result.value.status in {
            MaterialRequestStatus.PROPOSED,
            MaterialRequestStatus.AWAITING_APPROVAL,
        }
        return f"material_request:{request_id}", waiting

    def _handle_blocked_task(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> str:
        task_ids = [str(value) for value in event.payload["task_refs"]]
        tasks = list(self._store.repository(Task).list(event.project_id))
        self._require_task_ids(tasks, task_ids)
        impacted_ids = sorted(calculate_impact(tasks, task_ids))
        severity = Severity(str(event.payload["severity"]))
        issue = (
            IssueService(self._store)
            .create_issue(
                access,
                CreateIssueCommand(
                    project_id=event.project_id,
                    issue_type=IssueType.BLOCKER,
                    severity=severity,
                    description=str(event.payload["description"]),
                    evidence_refs=[event.event_id],
                    task_ids=impacted_ids,
                    detected_by=IssueDetectedBy.USER,
                    occurred_at=event.occurred_at,
                ),
                self._context(event, run_id, "blocked-issue"),
            )
            .issue
        )

        tasks_by_id = {task.id: task for task in tasks}
        for task_id in task_ids:
            task = tasks_by_id[task_id]
            TaskService(self._store).update_task(
                access,
                UpdateTaskCommand(
                    project_id=event.project_id,
                    task_id=task_id,
                    expected_version=task.version,
                    target_status=TaskStatus.BLOCKED,
                    evidence=str(event.payload["description"]),
                    occurred_at=event.occurred_at,
                ),
                self._context(event, run_id, f"blocked-task:{task_id}"),
            )

        if severity in {Severity.HIGH, Severity.CRITICAL}:
            OutboxService(self._store).queue(
                project_id=event.project_id,
                message_type="notification:blocker_escalation",
                payload={
                    "issue_id": issue.id,
                    "severity": severity.value,
                    "task_ids": impacted_ids,
                },
                deduplication_key=_step_key(
                    event.idempotency_key,
                    "blocker-escalation",
                ),
            )
        return f"issue:{issue.id}"

    def _handle_overdue_task(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> str:
        task_id = str(event.payload["task_id"])
        tasks = list(self._store.repository(Task).list(event.project_id))
        self._require_task_ids(tasks, [task_id])
        tasks_by_id = {task.id: task for task in tasks}
        impacted_ids = sorted(calculate_impact(tasks, [task_id]))
        issue = (
            IssueService(self._store)
            .create_issue(
                access,
                CreateIssueCommand(
                    project_id=event.project_id,
                    issue_type=IssueType.DELAY_RISK,
                    severity=Severity.MEDIUM,
                    description=(
                        f"{tasks_by_id[task_id].title} was overdue on "
                        f"{event.payload['expected_date']}."
                    ),
                    evidence_refs=[event.event_id],
                    task_ids=impacted_ids,
                    detected_by=IssueDetectedBy.OVERDUE_CHECK,
                    occurred_at=event.occurred_at,
                ),
                self._context(event, run_id, "overdue-issue"),
            )
            .issue
        )
        OutboxService(self._store).queue(
            project_id=event.project_id,
            message_type="notification:delay_risk",
            payload={"issue_id": issue.id, "task_ids": impacted_ids},
            deduplication_key=_step_key(event.idempotency_key, "delay-risk"),
        )
        return f"issue:{issue.id}"

    def _generate_daily_brief(
        self,
        event: ProjectEvent,
        access: ProjectAccessContext,
        run_id: str,
    ) -> str:
        ensure_permission(access, ProjectPermission.OPERATE)
        report_date = date.fromisoformat(str(event.payload["report_date"]))
        report_id = f"rpt_{event.project_id}_{report_date.isoformat()}"
        context = self._context(event, run_id, f"daily-brief:{report_date.isoformat()}")
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="daily_brief.generated",
                entity_type="daily_report",
                entity_id=report_id,
                summary="Generated the scheduled daily brief.",
                metadata={
                    "report_date": report_date.isoformat(),
                    "timezone": str(event.payload["timezone"]),
                },
            ),
            lambda session: self._upsert_daily_brief(
                session,
                event,
                report_id,
                report_date,
            ),
            replay=lambda session, _activity: session.repository(DailyReport).require(
                event.project_id, report_id
            ),
        )
        if result.value is None:
            raise RuntimeError("daily brief replay did not resolve persisted report")
        return f"daily_report:{result.value.id}"

    def _authorize(self, event: ProjectEvent) -> ProjectAccessContext:
        actor = AuthenticatedUser(
            user_id=event.actor.id,
            subject=f"event:{event.actor.type.value}:{event.actor.id}",
        )
        if event.actor.type is EventActorType.USER:
            membership = self._store.repository(ProjectMember).get(
                event.project_id,
                event.actor.id,
            )
            return authorize_project_member(
                actor,
                event.project_id,
                membership,
                ProjectPermission.OPERATE,
            )
        if event.source is EventSource.WEB:
            raise ProjectForbiddenError("web events require an authorized user actor")
        return ProjectAccessContext(
            actor=actor,
            project_id=event.project_id,
            role=MemberRole.MANAGER,
        )

    @staticmethod
    def _require_task_ids(tasks: list[Task], task_ids: list[str]) -> None:
        known = {task.id for task in tasks}
        missing = [task_id for task_id in task_ids if task_id not in known]
        if missing:
            raise EntityNotFoundError("event references unknown task(s): " + ", ".join(missing))

    @staticmethod
    def _mark_request_delayed(
        session: RepositorySession,
        event: ProjectEvent,
        request_id: str,
        access: ProjectAccessContext,
    ) -> MaterialRequest:
        repository = AuthorizedProjectRepository(
            session.repository(MaterialRequest),
            access,
        )
        request = repository.require(event.project_id, request_id)
        ensure_material_request_transition(request.status, MaterialRequestStatus.DELAYED)
        return repository.save(
            request.model_copy(
                update={
                    "status": MaterialRequestStatus.DELAYED,
                    "updated_at": event.occurred_at,
                }
            ),
            expected_version=repository.version_of(event.project_id, request_id),
        )

    @staticmethod
    def _upsert_daily_brief(
        session: RepositorySession,
        event: ProjectEvent,
        report_id: str,
        report_date: date,
    ) -> DailyReport:
        tasks = list(session.repository(Task).list(event.project_id))
        issues = list(session.repository(Issue).list(event.project_id))
        requests = list(session.repository(MaterialRequest).list(event.project_id))
        reports = session.repository(DailyReport)
        current = reports.get(event.project_id, report_id)
        outbox = session.repository(OutboxMessage)
        message_id = _outbox_id(event.idempotency_key, "daily-brief")
        existing_message = outbox.get(event.project_id, message_id)

        completed = [
            ReportFact(
                summary=f"{task.title} completed.",
                source_refs=[event.event_id],
                metadata={"task_id": task.id},
            )
            for task in sorted(tasks, key=lambda item: item.id)
            if task.status is TaskStatus.COMPLETED
        ]
        blockers = [
            ReportFact(
                summary=issue.description,
                source_refs=[event.event_id],
                metadata={"issue_id": issue.id, "severity": issue.severity.value},
            )
            for issue in sorted(issues, key=lambda item: item.id)
            if issue.status not in {IssueStatus.RESOLVED, IssueStatus.DISMISSED}
        ]
        material_risks = [
            ReportFact(
                summary=(
                    f"Material request {request.id} is {request.status.value.replace('_', ' ')}."
                ),
                source_refs=[event.event_id],
                metadata={"request_id": request.id, "material_id": request.material_id},
            )
            for request in sorted(requests, key=lambda item: item.id)
            if request.status
            in {
                MaterialRequestStatus.AWAITING_APPROVAL,
                MaterialRequestStatus.APPROVED,
                MaterialRequestStatus.SUBMITTED,
                MaterialRequestStatus.CONFIRMED,
                MaterialRequestStatus.DELAYED,
            }
        ]
        next_focus = [
            ReportFact(
                summary=f"Continue {task.title}.",
                source_refs=[event.event_id],
                metadata={"task_id": task.id},
            )
            for task in sorted(tasks, key=lambda item: item.id)
            if task.status in {TaskStatus.PLANNED, TaskStatus.IN_PROGRESS}
        ][:3]
        in_progress = [
            ReportFact(
                summary=f"{task.title} is in progress.",
                source_refs=[event.event_id, task.id],
                metadata={"task_id": task.id},
            )
            for task in sorted(tasks, key=lambda item: item.id)
            if task.status is TaskStatus.IN_PROGRESS
        ]
        merged_completed = _merge_facts(current.completed_work if current else (), completed)
        merged_blockers = _merge_facts(current.active_blockers if current else (), blockers)
        merged_materials = _merge_facts(current.material_risks if current else (), material_risks)
        merged_focus = _merge_facts(current.next_focus if current else (), next_focus)
        retained_in_progress = [
            fact
            for fact in (current.in_progress_work if current else ())
            if "task_id" not in fact.metadata
        ]
        merged_in_progress = _merge_facts(retained_in_progress, in_progress)
        summary = (
            f"Daily brief: {len(merged_completed)} achievements, "
            f"{len(merged_blockers)} blockers, {len(merged_materials)} material risks, "
            f"{len(merged_focus)} next-focus items."
        )
        desired = DailyReport(
            id=report_id,
            project_id=event.project_id,
            report_date=report_date,
            summary=summary,
            completed_work=merged_completed,
            in_progress_work=merged_in_progress,
            active_blockers=merged_blockers,
            material_risks=merged_materials,
            next_focus=merged_focus,
            crew_summary=current.crew_summary if current else None,
            weather_summary=current.weather_summary if current else None,
            deliveries=list(current.deliveries) if current else [],
            inspections=list(current.inspections) if current else [],
            photo_refs=list(current.photo_refs) if current else [],
            source_update_ids=list(current.source_update_ids) if current else [],
            status=current.status if current else ReportStatus.DRAFT,
            version=current.version if current else 0,
            created_at=current.created_at if current else event.occurred_at,
            updated_at=event.occurred_at,
        )
        if current is None:
            report = reports.create(desired)
        else:
            report = reports.save(
                desired,
                expected_version=reports.version_of(event.project_id, report_id),
            )

        if existing_message is None:
            outbox.create(
                OutboxMessage(
                    id=message_id,
                    project_id=event.project_id,
                    message_type="notification:daily_brief",
                    deduplication_key=_step_key(event.idempotency_key, "daily-brief"),
                    payload={
                        "report_id": report.id,
                        "report_date": report.report_date.isoformat(),
                        "summary": report.summary,
                    },
                    status=OutboxStatus.PENDING,
                    created_at=event.occurred_at,
                )
            )
        return report

    @staticmethod
    def _context(event: ProjectEvent, run_id: str, step: str) -> MutationContext:
        actor_type = ActorType.USER if event.actor.type is EventActorType.USER else ActorType.SYSTEM
        return MutationContext(
            project_id=event.project_id,
            actor_type=actor_type,
            actor_id=event.actor.id if actor_type is ActorType.USER else None,
            source_event_id=event.event_id,
            agent_run_id=run_id,
            idempotency_key=_step_key(event.idempotency_key, step),
            occurred_at=event.occurred_at,
        )


def _step_key(event_key: str, step: str) -> str:
    digest = sha256(f"{event_key}\x00{step}".encode("utf-8")).hexdigest()[:32]
    return f"event-step:{digest}"


def _outbox_id(event_key: str, kind: str) -> str:
    digest = sha256(f"{event_key}\x00{kind}".encode("utf-8")).hexdigest()[:20]
    return f"obx_{digest}"


def _merge_facts(
    existing: tuple[ReportFact, ...] | list[ReportFact],
    incoming: list[ReportFact],
) -> list[ReportFact]:
    merged = list(existing)
    for fact in incoming:
        if fact not in merged:
            merged.append(fact)
    return merged


__all__ = ["RoutedEventExecution", "TypedEventService"]
