"""Durable fan-out/fan-in orchestration for daily site updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import TYPE_CHECKING
from collections.abc import Sequence

from app.agents.interpreter import MediaEvidence, SiteInterpreter
from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.enums import (
    ActorType,
    ApprovalStatus,
    IssueType,
    MaterialRequestStatus,
    Severity,
    TaskStatus,
)
from app.domain.facts import (
    ConfidenceLevel,
    ExtractedFactSet,
    IssueFact,
    NextFocusFact,
    SafetyIssueFact,
    TaskCompletionFact,
)
from app.domain.models import Issue, Material, ReportFact, SiteUpdate, Task
from app.repositories.context import ProjectContext
from app.services.context import ContextService
from app.services.entity_resolution import MatchConfidence, resolve_material, resolve_task
from app.services.fact_router import route_facts
from app.services.issues import CreateIssueCommand, IssueService
from app.services.material_requests import MaterialRequestService, MaterialShortageCommand
from app.services.reports import ReportService
from app.services.schedule_impact import calculate_impact
from app.tools.materials import MaterialQuantityCommand, MaterialTools
from app.tools.tasks import TaskTools, UpdateTaskCommand

if TYPE_CHECKING:
    from app.workflows.runtime import RuntimeManager


_MODEL_CONTEXT_ENTITY_LIMIT = 200
_MODEL_CONTEXT_MAX_CHARS = 100_000


@dataclass(frozen=True, slots=True)
class SiteUpdateResult:
    site_update_id: str
    report_id: str
    has_clarifications: bool
    has_safety_stops: bool
    has_pending_approvals: bool
    tasks_updated: int
    materials_updated: int
    issues_created: int
    material_requests_created: int
    approvals_requested: int
    summary: str
    pending_actions: tuple[str, ...]


class SiteUpdateService:
    def __init__(
        self,
        interpreter: SiteInterpreter,
        context_service: ContextService,
        task_tools: TaskTools,
        material_tools: MaterialTools,
        issue_service: IssueService,
        material_request_service: MaterialRequestService,
        report_service: ReportService,
        runtime_manager: RuntimeManager,
    ) -> None:
        self._interpreter = interpreter
        self._context_service = context_service
        self._task_tools = task_tools
        self._material_tools = material_tools
        self._issues = issue_service
        self._material_requests = material_request_service
        self._reports = report_service
        self._runtime = runtime_manager

    async def process_update(
        self,
        access: ProjectAccessContext,
        site_update: SiteUpdate,
        run_id: str,
        trace_id: str,
        source_event_id: str | None = None,
        images: Sequence[MediaEvidence] = (),
    ) -> SiteUpdateResult:
        del trace_id
        causal_event_id = source_event_id or site_update.id
        text_corpus = " ".join(
            part for part in (site_update.raw_text, site_update.transcript) if part
        )
        project_context = self._context_service.get_context(access)
        fact_set = await self._interpreter.extract_facts(
            text_corpus,
            images=images,
            project_context=_project_context_prompt(project_context),
        )
        if images:
            fact_set = _guard_visual_task_completions(fact_set, text_corpus)
        routed = route_facts(fact_set)

        has_clarifications = bool(routed.clarifications)
        completed_work: list[ReportFact] = []
        active_blockers: list[ReportFact] = []
        material_risks: list[ReportFact] = []
        next_focus: list[ReportFact] = []
        tasks_updated = 0
        materials_updated = 0
        issues_created = 0
        material_requests_created = 0
        approvals_requested = 0
        has_pending_approvals = False
        pending_actions: list[str] = []
        schedule_risk_summaries: list[str] = []

        resolved_focus, focus_needs_clarification = _resolve_next_focus(
            routed.actionable_next_focus,
            project_context.active_tasks,
            site_update,
        )
        has_clarifications = has_clarifications or focus_needs_clarification
        next_focus.extend(fact for _task, fact in resolved_focus)

        if routed.safety_stops:
            for index, safety_fact in enumerate(routed.safety_stops):
                issue_change = self._issues.create_issue(
                    access,
                    _safety_issue_command(access, site_update, safety_fact),
                    _mutation_context(
                        access,
                        site_update,
                        causal_event_id,
                        run_id,
                        f"issue:safety:{index}",
                    ),
                )
                issue = issue_change.issue
                issues_created += int(not issue_change.duplicate)
                active_blockers.append(
                    ReportFact(
                        summary=issue.description,
                        source_refs=[site_update.id, issue.id],
                        metadata={
                            "issue_id": issue.id,
                            "issue_type": issue.type.value,
                            "severity": issue.severity.value,
                        },
                    )
                )
                pending_actions.append("Qualified safety review required.")
        else:
            seen_task_ids: set[str] = set()
            for task_fact in routed.actionable_tasks:
                if not task_fact.is_completed:
                    continue
                task_resolution = resolve_task(task_fact.task_name, project_context.active_tasks)
                task = task_resolution.resolved_entity
                if task_resolution.confidence is not MatchConfidence.HIGH or task is None:
                    has_clarifications = True
                    continue
                if task.id in seen_task_ids:
                    continue
                seen_task_ids.add(task.id)
                task_change = self._task_tools.complete_task(
                    UpdateTaskCommand(
                        project_id=access.project_id,
                        task_id=task.id,
                        expected_version=task.version,
                        completion_percent=Decimal("100"),
                        evidence=task_fact.evidence,
                        negated=task_fact.is_negated,
                        occurred_at=site_update.submitted_at,
                    ),
                    _mutation_context(
                        access,
                        site_update,
                        causal_event_id,
                        run_id,
                        f"task:{task.id}:complete",
                    ),
                )
                tasks_updated += int(not task_change.duplicate)
                completed_work.append(
                    ReportFact(
                        summary=f"{task_change.task.title} completed.",
                        source_refs=[site_update.id, task_change.task.id],
                        metadata={"task_id": task_change.task.id},
                    )
                )

            for index, issue_fact in enumerate(routed.actionable_issues):
                task_ids, unresolved = _resolve_issue_tasks(
                    issue_fact,
                    project_context.active_tasks,
                )
                if unresolved:
                    has_clarifications = True
                    continue
                issue_change = self._issues.create_issue(
                    access,
                    CreateIssueCommand(
                        project_id=access.project_id,
                        issue_type=issue_fact.issue_type,
                        severity=issue_fact.severity,
                        description=issue_fact.description,
                        evidence_refs=_evidence_refs(site_update),
                        task_ids=task_ids,
                        occurred_at=site_update.submitted_at,
                    ),
                    _mutation_context(
                        access,
                        site_update,
                        causal_event_id,
                        run_id,
                        f"issue:extracted:{index}:{issue_fact.issue_type.value}",
                    ),
                )
                issue = issue_change.issue
                issues_created += int(not issue_change.duplicate)
                active_blockers.append(_issue_report_fact(site_update, issue))

                if issue_fact.issue_type is not IssueType.BLOCKER or not task_ids:
                    continue
                blocked_task = _task_by_id(project_context.active_tasks, task_ids[0])
                if blocked_task.status in {TaskStatus.PLANNED, TaskStatus.IN_PROGRESS}:
                    task_change = self._task_tools.update_task_progress(
                        UpdateTaskCommand(
                            project_id=access.project_id,
                            task_id=blocked_task.id,
                            expected_version=blocked_task.version,
                            target_status=TaskStatus.BLOCKED,
                            evidence=issue_fact.evidence,
                            occurred_at=site_update.submitted_at,
                        ),
                        _mutation_context(
                            access,
                            site_update,
                            causal_event_id,
                            run_id,
                            f"task:{blocked_task.id}:blocked",
                        ),
                    )
                    tasks_updated += int(not task_change.duplicate)

                impacted_ids = sorted(
                    calculate_impact(project_context.active_tasks, task_ids) - set(task_ids)
                )
                if not impacted_ids:
                    continue
                impacted_tasks = [
                    _task_by_id(project_context.active_tasks, task_id) for task_id in impacted_ids
                ]
                risk_description = _schedule_risk_description(blocked_task, impacted_tasks)
                risk_change = self._issues.create_issue(
                    access,
                    CreateIssueCommand(
                        project_id=access.project_id,
                        issue_type=IssueType.DELAY_RISK,
                        severity=issue_fact.severity,
                        description=risk_description,
                        evidence_refs=_evidence_refs(site_update),
                        task_ids=impacted_ids,
                        occurred_at=site_update.submitted_at,
                    ),
                    _mutation_context(
                        access,
                        site_update,
                        causal_event_id,
                        run_id,
                        f"issue:blocker-impact:{index}:{blocked_task.id}",
                    ),
                )
                issues_created += int(not risk_change.duplicate)
                active_blockers.append(_issue_report_fact(site_update, risk_change.issue))
                schedule_risk_summaries.append(risk_description)
                pending_actions.append(_schedule_review_action(blocked_task, impacted_tasks))

            seen_material_ids: set[str] = set()
            for material_fact in routed.actionable_materials:
                if material_fact.quantity is None or material_fact.quantity < 0:
                    has_clarifications = True
                    continue
                material_resolution = resolve_material(
                    material_fact.material_name,
                    project_context.materials,
                )
                material = material_resolution.resolved_entity
                if material_resolution.confidence is not MatchConfidence.HIGH or material is None:
                    has_clarifications = True
                    continue
                if material.id in seen_material_ids:
                    continue
                seen_material_ids.add(material.id)
                reported_quantity = Decimal(str(material_fact.quantity))
                quantity_delta = reported_quantity - material.available_quantity
                if quantity_delta != 0:
                    material_change = self._material_tools.update_material_quantity(
                        MaterialQuantityCommand(
                            project_id=access.project_id,
                            material_id_or_alias=material.id,
                            quantity_delta=quantity_delta,
                            unit=material_fact.unit or material.unit,
                            expected_version=material.version,
                            reason=material_fact.evidence,
                            occurred_at=site_update.submitted_at,
                        ),
                        _mutation_context(
                            access,
                            site_update,
                            causal_event_id,
                            run_id,
                            f"material:{material.id}:reported-stock",
                        ),
                    )
                    material = material_change.material
                    materials_updated += int(not material_change.duplicate)

                required_quantity = _required_material_quantity(material)
                if required_quantity is None or reported_quantity >= required_quantity:
                    continue
                shortage = self._material_requests.evaluate_shortage(
                    access,
                    MaterialShortageCommand(
                        project_id=access.project_id,
                        material_id_or_alias=material.id,
                        required_quantity=required_quantity,
                        unit=material.unit,
                        needed_by=_earliest_focus_date(resolved_focus),
                        reason=(
                            f"Reported stock is below the requirement. {material_fact.evidence}"
                        ),
                        supplier=material.default_supplier,
                        estimated_unit_cost=material.estimated_unit_cost,
                        occurred_at=site_update.submitted_at,
                    ),
                    _mutation_context(
                        access,
                        site_update,
                        causal_event_id,
                        run_id,
                        f"material:{material.id}:shortage-request",
                    ),
                )
                if not shortage.is_shortage or shortage.request is None:
                    continue
                material_requests_created += int(not shortage.duplicate)
                approvals_requested += int(not shortage.duplicate)
                has_pending_approvals = has_pending_approvals or (
                    shortage.request.status is MaterialRequestStatus.AWAITING_APPROVAL
                    and shortage.approval is not None
                    and shortage.approval.status is ApprovalStatus.PENDING
                )
                pending_actions.append(
                    f"Manager approval required for {shortage.net_shortage} {material.unit} "
                    f"of {material.name}."
                )
                material_risks.append(
                    ReportFact(
                        summary=(
                            f"{material.name} is short by {shortage.net_shortage} {material.unit}."
                        ),
                        source_refs=[site_update.id, material.id, shortage.request.id],
                        metadata={
                            "material_id": material.id,
                            "material_request_id": shortage.request.id,
                            "approval_id": shortage.request.approval_id,
                        },
                    )
                )
                for focus_index, (focus_task, _focus_fact) in enumerate(resolved_focus):
                    delay_issue_change = self._issues.create_issue(
                        access,
                        CreateIssueCommand(
                            project_id=access.project_id,
                            issue_type=IssueType.DELAY_RISK,
                            severity=Severity.HIGH,
                            description=(
                                f"{focus_task.title} is at risk because {material.name} stock "
                                "is below the upcoming requirement."
                            ),
                            evidence_refs=_evidence_refs(site_update),
                            task_ids=[focus_task.id],
                            occurred_at=site_update.submitted_at,
                        ),
                        _mutation_context(
                            access,
                            site_update,
                            causal_event_id,
                            run_id,
                            f"issue:material-risk:{material.id}:{focus_index}:{focus_task.id}",
                        ),
                    )
                    delay_issue = delay_issue_change.issue
                    issues_created += int(not delay_issue_change.duplicate)
                    active_blockers.append(_issue_report_fact(site_update, delay_issue))

        report = self._reports.project_site_update(
            access,
            site_update,
            completed_work=completed_work,
            active_blockers=active_blockers,
            material_risks=material_risks,
            next_focus=next_focus,
            context=_mutation_context(
                access,
                site_update,
                causal_event_id,
                run_id,
                "report:daily-projection",
            ),
        )
        self._runtime.update_checkpoint(access.project_id, run_id, "report_projected")
        summary = (
            f"Processed site update: {tasks_updated} task update, {issues_created} issues, "
            f"{materials_updated} material update, and report {report.id}."
        )
        if schedule_risk_summaries:
            summary = f"{summary} {_schedule_response_summary(schedule_risk_summaries)}"
        return SiteUpdateResult(
            site_update_id=site_update.id,
            report_id=report.id,
            has_clarifications=has_clarifications,
            has_safety_stops=bool(routed.safety_stops),
            has_pending_approvals=has_pending_approvals,
            tasks_updated=tasks_updated,
            materials_updated=materials_updated,
            issues_created=issues_created,
            material_requests_created=material_requests_created,
            approvals_requested=approvals_requested,
            summary=summary,
            pending_actions=tuple(pending_actions),
        )


def _mutation_context(
    access: ProjectAccessContext,
    site_update: SiteUpdate,
    source_event_id: str,
    run_id: str,
    mutation_scope: str,
) -> MutationContext:
    scope_digest = sha256(mutation_scope.encode("utf-8")).hexdigest()[:20]
    return MutationContext(
        project_id=access.project_id,
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        source_event_id=source_event_id,
        idempotency_key=f"site-update:{site_update.id}:{scope_digest}",
        occurred_at=site_update.submitted_at,
        agent_run_id=run_id,
    )


def _resolve_next_focus(
    facts: list[NextFocusFact],
    tasks: Sequence[Task],
    site_update: SiteUpdate,
) -> tuple[list[tuple[Task, ReportFact]], bool]:
    resolved: list[tuple[Task, ReportFact]] = []
    needs_clarification = False
    seen: set[str] = set()
    for fact in facts:
        if not fact.task_name:
            needs_clarification = True
            continue
        resolution = resolve_task(fact.task_name, tasks)
        task = resolution.resolved_entity
        if resolution.confidence is not MatchConfidence.HIGH or task is None:
            needs_clarification = True
            continue
        if task.id in seen:
            continue
        seen.add(task.id)
        resolved.append(
            (
                task,
                ReportFact(
                    summary=fact.description,
                    source_refs=[site_update.id, task.id],
                    metadata={"task_id": task.id},
                ),
            )
        )
    return resolved, needs_clarification


def _resolve_issue_tasks(
    issue_fact: IssueFact,
    tasks: Sequence[Task],
) -> tuple[list[str], bool]:
    if not issue_fact.task_name:
        return [], False
    resolution = resolve_task(issue_fact.task_name, tasks)
    task = resolution.resolved_entity
    if resolution.confidence is not MatchConfidence.HIGH or task is None:
        return [], True
    return [task.id], False


def _required_material_quantity(material: Material) -> Decimal | None:
    return material.upcoming_requirement_quantity or (
        material.minimum_required_quantity if material.minimum_required_quantity > 0 else None
    )


def _task_by_id(tasks: Sequence[Task], task_id: str) -> Task:
    for task in tasks:
        if task.id == task_id:
            return task
    raise RuntimeError("resolved task disappeared from authorized project context")


def _schedule_risk_description(blocked_task: Task, impacted_tasks: Sequence[Task]) -> str:
    titles = _bounded_task_titles(impacted_tasks)
    return f"{blocked_task.title} is blocked, putting dependent work at risk: {titles}."


def _schedule_review_action(blocked_task: Task, impacted_tasks: Sequence[Task]) -> str:
    titles = _bounded_task_titles(impacted_tasks)
    return f"Review schedule impact on {titles} due to the {blocked_task.title} blocker."


def _bounded_task_titles(tasks: Sequence[Task], *, limit: int = 10) -> str:
    visible = [task.title for task in tasks[:limit]]
    remaining = len(tasks) - len(visible)
    if remaining:
        visible.append(f"{remaining} more dependent task{'s' if remaining != 1 else ''}")
    return ", ".join(visible)


def _schedule_response_summary(risk_summaries: Sequence[str]) -> str:
    additional_count = len(risk_summaries) - 1
    additional = (
        f" {additional_count} additional schedule risk"
        f"{'s are' if additional_count != 1 else ' is'} in the daily report."
        if additional_count
        else ""
    )
    return f"Schedule risk: {risk_summaries[0]}{additional}"


def _earliest_focus_date(
    resolved_focus: list[tuple[Task, ReportFact]],
) -> datetime | None:
    dates = [task.planned_start for task, _fact in resolved_focus if task.planned_start]
    return min(dates) if dates else None


def _evidence_refs(site_update: SiteUpdate) -> list[str]:
    return [site_update.id, *site_update.attachment_ids]


def _guard_visual_task_completions(
    fact_set: ExtractedFactSet,
    text_corpus: str,
) -> ExtractedFactSet:
    normalized_text = " ".join(text_corpus.casefold().split())
    guarded_tasks: list[TaskCompletionFact] = []
    for fact in fact_set.tasks:
        normalized_evidence = " ".join(fact.evidence.casefold().split())
        text_corroborates_completion = bool(
            normalized_evidence and normalized_evidence in normalized_text
        )
        if fact.is_completed and not text_corroborates_completion:
            fact = fact.model_copy(
                update={
                    "confidence": ConfidenceLevel.MEDIUM,
                    "clarification_needed": (
                        fact.clarification_needed
                        or "Confirm task completion reported by the photo."
                    ),
                }
            )
        guarded_tasks.append(fact)
    return fact_set.model_copy(update={"tasks": guarded_tasks})


def _project_context_prompt(project_context: ProjectContext) -> str:
    tasks: list[dict[str, object]] = []
    materials: list[dict[str, object]] = []
    payload: dict[str, object] = {
        "project_id": project_context.project_id,
        "tasks": tasks,
        "materials": materials,
    }

    for index, task in enumerate(project_context.active_tasks):
        if index >= _MODEL_CONTEXT_ENTITY_LIMIT:
            break
        tasks.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "completion_percent": str(task.completion_percent),
                "dependency_ids": task.dependency_ids,
            }
        )
        if len(_encode_project_context(payload)) > _MODEL_CONTEXT_MAX_CHARS:
            tasks.pop()
            continue

    for index, material in enumerate(project_context.materials):
        if index >= _MODEL_CONTEXT_ENTITY_LIMIT:
            break
        materials.append(
            {
                "id": material.id,
                "name": material.name,
                "aliases": material.aliases,
                "unit": material.unit,
                "available_quantity": str(material.available_quantity),
                "minimum_required_quantity": str(material.minimum_required_quantity),
                "upcoming_requirement_quantity": (
                    str(material.upcoming_requirement_quantity)
                    if material.upcoming_requirement_quantity is not None
                    else None
                ),
            }
        )
        if len(_encode_project_context(payload)) > _MODEL_CONTEXT_MAX_CHARS:
            materials.pop()
            continue
    return _encode_project_context(payload)


def _encode_project_context(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _issue_report_fact(site_update: SiteUpdate, issue: Issue) -> ReportFact:
    return ReportFact(
        summary=issue.description,
        source_refs=[site_update.id, issue.id],
        metadata={
            "issue_id": issue.id,
            "issue_type": issue.type.value,
            "severity": issue.severity.value,
            "task_ids": issue.task_ids,
        },
    )


def _safety_issue_command(
    access: ProjectAccessContext,
    site_update: SiteUpdate,
    fact: SafetyIssueFact,
) -> CreateIssueCommand:
    severity = Severity(fact.severity.lower())
    return CreateIssueCommand(
        project_id=access.project_id,
        issue_type=IssueType.SAFETY,
        severity=severity,
        description=fact.description,
        evidence_refs=_evidence_refs(site_update),
        occurred_at=site_update.submitted_at,
    )


__all__ = ["SiteUpdateResult", "SiteUpdateService"]
