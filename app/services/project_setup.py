"""Deterministic project-readiness projection from authorized persisted state."""

from __future__ import annotations

import re

from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.conversation import ProjectReadinessState, ProjectSetupStatus
from app.domain.enums import IssueStatus, MemberStatus, TaskSource, TaskStatus
from app.domain.import_records import MaterialRequirement
from app.domain.models import (
    ActivityEvent,
    DailyReport,
    Issue,
    Material,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.repositories.interfaces import RepositoryStore
from app.services.conversation_context import ProjectReader


class ProjectSetupService:
    def __init__(self, store: RepositoryStore, projects: ProjectReader) -> None:
        self._store = store
        self._projects = projects

    def retrieve(self, access: ProjectAccessContext) -> ProjectSetupStatus:
        ensure_permission(access, ProjectPermission.READ)
        project = self._projects.require(access)
        tasks = tuple(
            task
            for task in self._store.repository(Task).list(project.id)
            if task.status is not TaskStatus.CANCELLED
        )
        materials = self._store.repository(Material).list(project.id)
        requirements = self._store.repository(MaterialRequirement).list(project.id)
        site_updates = self._store.repository(SiteUpdate).list(project.id)
        daily_logs = self._store.repository(DailyReport).list(project.id)
        activity = self._store.repository(ActivityEvent).list(project.id)
        members = tuple(
            member
            for member in self._store.repository(ProjectMember).list(project.id)
            if member.status is MemberStatus.ACTIVE
        )
        issues = tuple(
            issue
            for issue in self._store.repository(Issue).list(project.id)
            if issue.status not in {IssueStatus.RESOLVED, IssueStatus.DISMISSED}
        )
        has_schedule = any(
            task.planned_start is not None or task.planned_end is not None for task in tasks
        )
        requirement_task_ids = {requirement.task_id for requirement in requirements}
        planned_tasks_without_material_requirements = sum(
            1
            for task in tasks
            if task.status is TaskStatus.PLANNED and task.id not in requirement_task_ids
        )
        dependency_count = sum(len(task.dependency_ids) for task in tasks)
        has_initial_state = any(task.source is TaskSource.IMPORT for task in tasks)
        if not any((tasks, materials, requirements, site_updates, daily_logs)):
            readiness = ProjectReadinessState.EMPTY
        elif tasks:
            readiness = ProjectReadinessState.OPERATIONAL
        else:
            readiness = ProjectReadinessState.PARTIALLY_CONFIGURED
        return ProjectSetupStatus(
            project_exists=True,
            project_name=project.name,
            has_members=bool(members),
            has_tasks=bool(tasks),
            has_dependencies=bool(dependency_count),
            has_schedule=has_schedule,
            has_materials=bool(materials),
            has_material_requirements=bool(requirements),
            has_initial_state=has_initial_state,
            has_site_updates=bool(site_updates),
            has_daily_logs=bool(daily_logs),
            has_recent_activity=bool(activity),
            task_count=len(tasks),
            dependency_count=dependency_count,
            material_requirement_task_count=len(requirement_task_ids),
            planned_tasks_without_material_requirements=planned_tasks_without_material_requirements,
            open_issue_count=len(issues),
            readiness_state=readiness,
        )


def is_project_setup_question(message: str) -> bool:
    normalized = " ".join(message.casefold().split()).rstrip("?!. ")
    return any(
        re.fullmatch(pattern, normalized)
        for pattern in (
            r"(?:do we have|is|are) (?:my|our|the) project (?:set|set up|ready)",
            r"(?:is|are) (?:my|our|the) project setup (?:done|ready|complete)",
            r"how (?:do i|can i|do we) set up (?:my|our|the) project",
        )
    )


__all__ = ["ProjectSetupService", "is_project_setup_question"]
