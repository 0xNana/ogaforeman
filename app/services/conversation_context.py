"""Authorized, query-shaped context retrieval for conversational OG."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol, TypeVar
from zoneinfo import ZoneInfo

from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.conversation import (
    ActivityContextItem,
    ApprovalContextItem,
    ContextDomain,
    ContextFocus,
    ContextQuery,
    ConversationalProjectContext,
    DailyLogContextItem,
    IssueContextItem,
    MaterialContextItem,
    MaterialRequestContextItem,
    MemberContextItem,
    ProjectContextItem,
    TaskContextItem,
)
from app.domain.enums import (
    ApprovalStatus,
    IssueStatus,
    MaterialRequestStatus,
    MemberStatus,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    Approval,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    Project,
    ProjectMember,
    Task,
)
from app.repositories.interfaces import RepositoryStore, RepositoryTransaction


ContextEntityT = TypeVar("ContextEntityT", Issue, Material, MaterialRequest)


class ProjectReader(Protocol):
    def require(self, access: ProjectAccessContext) -> Project: ...


_GENERAL_DOMAINS = (
    ContextDomain.PROJECT,
    ContextDomain.TASKS,
    ContextDomain.ISSUES,
    ContextDomain.MATERIALS,
    ContextDomain.APPROVALS,
    ContextDomain.SCHEDULE,
)
_STOP_WORDS = frozenset(
    {
        "what",
        "whats",
        "what's",
        "who",
        "owns",
        "why",
        "is",
        "are",
        "the",
        "at",
        "us",
        "how",
        "about",
        "happening",
        "with",
        "where",
        "we",
        "our",
        "project",
        "current",
        "status",
        "going",
        "on",
        "for",
        "me",
        "tell",
    }
)


def plan_context_query(message: str) -> ContextQuery:
    """Deterministically select retrieval domains; this never interprets mutations."""

    normalized = " ".join(message.casefold().split())
    if not normalized:
        raise ValueError("project context query cannot be empty")
    if "happened today" in normalized:
        return ContextQuery(
            domains=(ContextDomain.TASKS, ContextDomain.DAILY_LOGS, ContextDomain.RECENT_ACTIVITY),
            focus=ContextFocus.TODAY,
        )
    if "blocking" in normalized or "blocker" in normalized:
        return ContextQuery(domains=(ContextDomain.ISSUES, ContextDomain.TASKS))
    if "late" in normalized or "overdue" in normalized:
        return ContextQuery(
            domains=(ContextDomain.SCHEDULE, ContextDomain.TASKS),
            focus=ContextFocus.OVERDUE,
        )
    if "material" in normalized and "low" in normalized:
        return ContextQuery(
            domains=(ContextDomain.MATERIALS, ContextDomain.MATERIAL_REQUESTS),
            focus=ContextFocus.LOW_STOCK,
        )
    if "approval" in normalized or "needs approval" in normalized:
        return ContextQuery(
            domains=(ContextDomain.APPROVALS, ContextDomain.MATERIAL_REQUESTS),
            focus=ContextFocus.PENDING,
        )
    if "tomorrow" in normalized:
        return ContextQuery(
            domains=(ContextDomain.SCHEDULE, ContextDomain.TASKS),
            focus=ContextFocus.TOMORROW,
        )
    if normalized.startswith("who owns"):
        return ContextQuery(
            domains=(ContextDomain.TASKS, ContextDomain.ISSUES, ContextDomain.PROJECT_MEMBERS),
            search_terms=_search_terms(normalized),
        )
    if normalized.startswith("why") and "risk" in normalized:
        return ContextQuery(
            domains=(
                ContextDomain.TASKS,
                ContextDomain.ISSUES,
                ContextDomain.SCHEDULE,
                ContextDomain.DAILY_LOGS,
            ),
            search_terms=_search_terms(normalized),
        )
    if (
        normalized.startswith("how about ")
        or normalized.startswith("what about ")
        or normalized.startswith("what's happening with ")
        or normalized.startswith("whats happening with ")
        or normalized.startswith("how is ")
        or normalized.startswith("what is happening with ")
    ):
        terms = _search_terms(normalized)
        if terms:
            return ContextQuery(domains=_GENERAL_DOMAINS, search_terms=terms)
    return ContextQuery(domains=_GENERAL_DOMAINS)


class ProjectContextService:
    def __init__(
        self,
        store: RepositoryStore,
        projects: ProjectReader,
        *,
        member_names: Callable[[str], dict[str, str]] | None = None,
        max_items_per_domain: int = 20,
    ) -> None:
        if not 1 <= max_items_per_domain <= 100:
            raise ValueError("max_items_per_domain must be between 1 and 100")
        self._store = store
        self._projects = projects
        self._member_names = member_names or (lambda project_id: {})
        self._limit = max_items_per_domain

    def retrieve(
        self,
        access: ProjectAccessContext,
        query: ContextQuery,
        *,
        now: datetime | None = None,
    ) -> ConversationalProjectContext:
        ensure_project_scope(access, access.project_id)
        ensure_permission(access, ProjectPermission.READ)
        project = self._projects.require(access)
        ensure_project_scope(access, project.id)
        retrieved_at = (now or datetime.now(UTC)).astimezone(UTC)
        timezone = ZoneInfo(project.timezone)
        local_date = retrieved_at.astimezone(timezone).date()
        domains = set(query.domains)
        needs_names = bool(
            domains.intersection(
                {
                    ContextDomain.TASKS,
                    ContextDomain.SCHEDULE,
                    ContextDomain.ISSUES,
                    ContextDomain.PROJECT_MEMBERS,
                }
            )
        )
        names = self._member_names(project.id) if needs_names else {}

        needs_tasks = bool(
            domains.intersection({ContextDomain.TASKS, ContextDomain.SCHEDULE})
            or (ContextDomain.ISSUES in domains and query.search_terms)
        )
        tasks = self._tasks(project.id, query, retrieved_at, timezone, names) if needs_tasks else ()
        issues = (
            self._issues(project.id, query, names, {task.id for task in tasks})
            if ContextDomain.ISSUES in domains
            else ()
        )
        return ConversationalProjectContext(
            project_id=project.id,
            retrieved_at=retrieved_at,
            query=query,
            project=(
                ProjectContextItem(
                    id=project.id,
                    name=project.name,
                    location=project.location,
                    timezone=project.timezone,
                    status=project.status.value,
                )
                if ContextDomain.PROJECT in domains
                else None
            ),
            tasks=tasks if ContextDomain.TASKS in domains else (),
            issues=issues if ContextDomain.ISSUES in domains else (),
            materials=self._materials(project.id, query)
            if ContextDomain.MATERIALS in domains
            else (),
            material_requests=(
                self._requests(project.id, query)
                if ContextDomain.MATERIAL_REQUESTS in domains
                else ()
            ),
            approvals=self._approvals(project.id) if ContextDomain.APPROVALS in domains else (),
            schedule=tasks if ContextDomain.SCHEDULE in domains else (),
            daily_logs=(
                self._daily_logs(project.id, query, local_date)
                if ContextDomain.DAILY_LOGS in domains
                else ()
            ),
            recent_activity=(
                self._activity(project.id, query, local_date, timezone)
                if ContextDomain.RECENT_ACTIVITY in domains
                else ()
            ),
            members=self._members(project.id, names, query)
            if ContextDomain.PROJECT_MEMBERS in domains
            else (),
        )

    def _tasks(
        self,
        project_id: str,
        query: ContextQuery,
        now: datetime,
        timezone: ZoneInfo,
        names: dict[str, str],
    ) -> tuple[TaskContextItem, ...]:
        tasks = list(self._store.repository(Task).list(project_id))
        if query.focus is ContextFocus.TODAY:
            tasks = [
                task
                for task in tasks
                if task.actual_completion
                and task.actual_completion.astimezone(timezone).date()
                == now.astimezone(timezone).date()
            ]
        elif query.focus is ContextFocus.TOMORROW:
            tomorrow = now.astimezone(timezone).date() + timedelta(days=1)
            tasks = [
                task
                for task in tasks
                if task.planned_start and task.planned_start.astimezone(timezone).date() == tomorrow
            ]
        elif query.focus is ContextFocus.OVERDUE:
            tasks = [
                task
                for task in tasks
                if task.planned_end
                and task.planned_end < now
                and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
            ]
        elif query.search_terms:
            tasks = [
                task
                for task in tasks
                if _matches(query.search_terms, task.title, task.trade, task.location)
            ]
        else:
            tasks = [task for task in tasks if task.status is not TaskStatus.CANCELLED]
        tasks.sort(
            key=lambda task: (task.planned_start or datetime.max.replace(tzinfo=UTC), task.id)
        )
        return tuple(_task_item(task, names) for task in tasks[: self._limit])

    def _issues(
        self,
        project_id: str,
        query: ContextQuery,
        names: dict[str, str],
        matched_task_ids: set[str],
    ) -> tuple[IssueContextItem, ...]:
        versioned_issues = self._versioned_items(Issue, project_id)
        issues = list(versioned_issues)
        if query.focus is not ContextFocus.ALL:
            issues = [
                (issue, version)
                for issue, version in issues
                if issue.status
                in {IssueStatus.OPEN, IssueStatus.ACKNOWLEDGED, IssueStatus.MITIGATED}
            ]
        if query.search_terms:
            issues = [
                (issue, version)
                for issue, version in issues
                if _matches(query.search_terms, issue.description)
                or bool(matched_task_ids.intersection(issue.task_ids))
            ]
        issues.sort(key=lambda item: (item[0].severity.value, item[0].updated_at), reverse=True)
        return tuple(
            IssueContextItem(
                id=issue.id,
                type=issue.type.value,
                severity=issue.severity.value,
                description=issue.description[:1000],
                status=issue.status.value,
                task_ids=tuple(issue.task_ids),
                owner_id=issue.owner_id,
                owner_name=names.get(issue.owner_id) if issue.owner_id else None,
                due_at=issue.due_at,
                version=version,
            )
            for issue, version in issues[: self._limit]
        )

    def _materials(self, project_id: str, query: ContextQuery) -> tuple[MaterialContextItem, ...]:
        materials = list(self._versioned_items(Material, project_id))
        if query.focus is ContextFocus.LOW_STOCK:
            materials = [item for item in materials if _is_low(item[0])]
        elif query.search_terms:
            materials = [
                item
                for item in materials
                if _matches(
                    query.search_terms,
                    item[0].name,
                    item[0].normalized_name,
                    *item[0].aliases,
                )
            ]
        return tuple(
            MaterialContextItem(
                id=item.id,
                name=item.name,
                unit=item.unit,
                available_quantity=item.available_quantity,
                reserved_quantity=item.reserved_quantity,
                minimum_required_quantity=item.minimum_required_quantity,
                upcoming_requirement_quantity=item.upcoming_requirement_quantity,
                version=version,
            )
            for item, version in materials[: self._limit]
        )

    def _requests(
        self, project_id: str, query: ContextQuery
    ) -> tuple[MaterialRequestContextItem, ...]:
        requests = list(self._versioned_items(MaterialRequest, project_id))
        if query.focus in {ContextFocus.PENDING, ContextFocus.LOW_STOCK}:
            terminal = {
                MaterialRequestStatus.DELIVERED,
                MaterialRequestStatus.CANCELLED,
                MaterialRequestStatus.REJECTED,
            }
            requests = [item for item in requests if item[0].status not in terminal]
        if query.search_terms:
            material_names = {
                item.id: item.name for item in self._store.repository(Material).list(project_id)
            }
            requests = [
                item
                for item in requests
                if _matches(
                    query.search_terms,
                    item[0].reason,
                    material_names.get(item[0].material_id),
                )
            ]
        requests.sort(key=lambda pair: pair[0].updated_at, reverse=True)
        return tuple(
            MaterialRequestContextItem(
                id=item.id,
                material_id=item.material_id,
                quantity=item.quantity,
                delivered_quantity=item.delivered_quantity,
                unit=item.unit,
                status=item.status.value,
                needed_by=item.needed_by,
                reason=item.reason[:1000],
                approval_id=item.approval_id,
                version=version,
            )
            for item, version in requests[: self._limit]
        )

    def _approvals(self, project_id: str) -> tuple[ApprovalContextItem, ...]:
        approvals = [
            item
            for item in self._store.repository(Approval).list(project_id)
            if item.status is ApprovalStatus.PENDING
        ]
        approvals.sort(key=lambda item: item.requested_at, reverse=True)
        return tuple(
            ApprovalContextItem(
                id=item.id,
                action_type=item.action_type.value,
                status=item.status.value,
                reason=item.reason[:1000],
                requested_at=item.requested_at,
            )
            for item in approvals[: self._limit]
        )

    def _daily_logs(
        self, project_id: str, query: ContextQuery, local_date: date
    ) -> tuple[DailyLogContextItem, ...]:
        reports = list(self._store.repository(DailyReport).list(project_id))
        if query.focus is ContextFocus.TODAY:
            reports = [report for report in reports if report.report_date == local_date]
        reports.sort(key=lambda report: (report.report_date, report.updated_at), reverse=True)
        return tuple(
            DailyLogContextItem(
                id=item.id,
                report_date=item.report_date,
                summary=item.summary[:2000],
                active_blockers=tuple(fact.summary[:500] for fact in item.active_blockers[:10]),
                material_risks=tuple(fact.summary[:500] for fact in item.material_risks[:10]),
                next_focus=tuple(fact.summary[:500] for fact in item.next_focus[:10]),
            )
            for item in reports[: self._limit]
        )

    def _activity(
        self,
        project_id: str,
        query: ContextQuery,
        local_date: date,
        timezone: ZoneInfo,
    ) -> tuple[ActivityContextItem, ...]:
        events = list(self._store.repository(ActivityEvent).list(project_id))
        if query.focus is ContextFocus.TODAY:
            events = [
                event
                for event in events
                if event.created_at.astimezone(timezone).date() == local_date
            ]
        events.sort(key=lambda event: event.created_at, reverse=True)
        return tuple(
            ActivityContextItem(
                id=item.id,
                action=item.action,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                summary=item.summary[:1000],
                created_at=item.created_at,
            )
            for item in events[: self._limit]
        )

    def _members(
        self, project_id: str, names: dict[str, str], query: ContextQuery
    ) -> tuple[MemberContextItem, ...]:
        members = [
            item
            for item in self._store.repository(ProjectMember).list(project_id)
            if item.status is MemberStatus.ACTIVE
        ]
        if query.focus is ContextFocus.ALL and query.search_terms:
            members = [
                item for item in members if _matches(query.search_terms, names.get(item.user_id))
            ]
        members.sort(key=lambda item: (names.get(item.user_id, "").casefold(), item.user_id))
        return tuple(
            MemberContextItem(
                user_id=item.user_id,
                display_name=names.get(item.user_id, "Project member"),
                role=item.role.value,
            )
            for item in members[: self._limit]
        )

    def _versioned_items(
        self,
        model: type[ContextEntityT],
        project_id: str,
    ) -> tuple[tuple[ContextEntityT, int], ...]:
        def read(
            transaction: RepositoryTransaction[ContextEntityT],
        ) -> tuple[tuple[ContextEntityT, int], ...]:
            rows: list[tuple[ContextEntityT, int]] = []
            for item in transaction.list(project_id):
                version = transaction.version_of(project_id, item.id)
                if version is None:
                    raise RuntimeError("authorized context entity has no persisted version")
                rows.append((item, version))
            return tuple(rows)

        return self._store.repository(model).run_transaction(read)


def _task_item(task: Task, names: dict[str, str]) -> TaskContextItem:
    return TaskContextItem(
        id=task.id,
        title=task.title,
        status=task.status.value,
        priority=task.priority.value,
        assignee_id=task.assigned_to,
        assignee_name=names.get(task.assigned_to) if task.assigned_to else None,
        trade=task.trade,
        location=task.location,
        planned_start=task.planned_start,
        planned_end=task.planned_end,
        actual_completion=task.actual_completion,
        completion_percent=task.completion_percent,
        dependency_ids=tuple(task.dependency_ids),
        version=task.version,
    )


def _is_low(material: Material) -> bool:
    threshold = max(
        material.minimum_required_quantity,
        material.upcoming_requirement_quantity or Decimal("0"),
    )
    return material.available_quantity - material.reserved_quantity < threshold


def _search_terms(message: str) -> tuple[str, ...]:
    terms = [term for term in re.findall(r"[a-z0-9-]+", message) if term not in _STOP_WORDS]
    return tuple(term for term in terms if term not in {"risk"})[:8]


def _matches(terms: Sequence[str], *values: str | None) -> bool:
    corpus = " ".join(value.casefold() for value in values if value)
    return any(term in corpus for term in terms)


__all__ = ["ProjectContextService", "ProjectReader", "plan_context_query"]
