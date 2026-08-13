"""Daily report projection service."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.domain.activity import ActivitySpec, MutationContext, WorkflowActivityAction
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType
from app.domain.models import (
    ActivityEvent,
    CanonicalId,
    DailyReport,
    ReportFact,
    ReportStatus,
    SiteUpdate,
)
from app.repositories.interfaces import RepositorySession, RepositoryStore, VersionConflictError
from app.repositories.reports import ReportRepository
from app.services.activity import ActivityService
from app.services.workflow_audit import workflow_audit_activity


class ReportService:
    def __init__(self, store: RepositoryStore):
        self._reports = ReportRepository(store)
        self._store = store
        self._activities = ActivityService(store)

    def edit_daily_log(
        self,
        access: ProjectAccessContext,
        command: EditDailyLogCommand,
        context: MutationContext,
    ) -> DailyLogChange:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.MANAGE)
        if context.actor_type is not ActorType.USER or context.actor_id != access.actor.user_id:
            raise PermissionError("daily log editing requires the authorized user actor")
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="daily_log.edited",
                entity_type="daily_report",
                entity_id=command.report_id,
                summary="Edited daily log client-facing details.",
                metadata={"report_id": command.report_id},
            ),
            lambda session: _edit_daily_log(session, command, context.occurred_at),
            replay=lambda session, _activity: session.repository(DailyReport).require(
                command.project_id, command.report_id
            ),
        )
        if result.value is None:
            raise RuntimeError("daily log edit replay did not resolve persisted state")
        return DailyLogChange(
            report=result.value, activity=result.activity, duplicate=result.duplicate
        )

    def project_site_update(
        self,
        access: ProjectAccessContext,
        site_update: SiteUpdate,
        *,
        completed_work: Sequence[ReportFact],
        active_blockers: Sequence[ReportFact],
        material_risks: Sequence[ReportFact],
        next_focus: Sequence[ReportFact],
        context: MutationContext,
    ) -> DailyReport:
        ensure_project_scope(access, site_update.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        report_date = site_update.submitted_at.astimezone(UTC).date()
        report_id = _report_id(access.project_id, report_date)
        projection_digest = sha256(
            json.dumps(
                {
                    "completed_work": [fact.model_dump(mode="json") for fact in completed_work],
                    "active_blockers": [fact.model_dump(mode="json") for fact in active_blockers],
                    "material_risks": [fact.model_dump(mode="json") for fact in material_risks],
                    "next_focus": [fact.model_dump(mode="json") for fact in next_focus],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        semantic_activity = workflow_audit_activity(
            context,
            action=WorkflowActivityAction.REPORT_UPDATED,
            entity_type="daily_report",
            entity_id=report_id,
            summary="Updated the daily report with observable site-update outcomes.",
            metadata={
                "status": "updated",
                "source_site_update_id": site_update.id,
                "report_id": report_id,
                "report_date": report_date.isoformat(),
                "completed_work_count": len(completed_work),
                "active_blocker_count": len(active_blockers),
                "material_risk_count": len(material_risks),
                "next_focus_count": len(next_focus),
            },
        )
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="report.projected",
                entity_type="daily_report",
                entity_id=report_id,
                summary="Updated the daily report from a site update.",
                metadata={
                    "source_update_id": site_update.id,
                    "report_date": report_date.isoformat(),
                    "projection_digest": projection_digest,
                    "completed_work_count": len(completed_work),
                    "active_blocker_count": len(active_blockers),
                    "material_risk_count": len(material_risks),
                    "next_focus_count": len(next_focus),
                },
            ),
            lambda session: _apply_site_update_projection(
                session,
                access.project_id,
                report_id,
                report_date,
                site_update,
                completed_work,
                active_blockers,
                material_risks,
                next_focus,
                context.occurred_at,
            ),
            replay=lambda session, _activity: session.repository(DailyReport).require(
                access.project_id, report_id
            ),
            additional_activities=(semantic_activity,) if semantic_activity else (),
        )
        if result.value is None:
            raise RuntimeError("report replay did not resolve persisted state")
        return result.value

    def get_or_create_report(self, project_id: str, report_date: date) -> DailyReport:
        # A simple ID scheme based on date
        report_id = f"rpt_{project_id}_{report_date.isoformat()}"

        def _get_or_create(session):
            repo = ReportRepository.for_session(session)
            report = repo.get(project_id, report_id)
            if not report:
                report = repo.create(
                    DailyReport(
                        id=report_id,
                        project_id=project_id,
                        report_date=report_date,
                        summary="Daily site report draft.",
                        status=ReportStatus.DRAFT,
                    )
                )
            return report

        return self._store.run_transaction(_get_or_create)

    def append_fact(
        self,
        project_id: str,
        report_date: date,
        fact: ReportFact,
        category: str,
        source_update_id: str,
    ) -> DailyReport:
        report_id = f"rpt_{project_id}_{report_date.isoformat()}"

        def _append(session):
            repo = ReportRepository.for_session(session)
            report = repo.get(project_id, report_id)
            if not report:
                report = repo.create(
                    DailyReport(
                        id=report_id,
                        project_id=project_id,
                        report_date=report_date,
                        summary="Daily site report draft.",
                        status=ReportStatus.DRAFT,
                    )
                )

            # Avoid duplicate source updates if already tracked
            if source_update_id not in report.source_update_ids:
                new_source_update_ids = report.source_update_ids + [source_update_id]
            else:
                new_source_update_ids = report.source_update_ids

            new_completed_work = report.completed_work.copy()
            new_active_blockers = report.active_blockers.copy()
            new_material_risks = report.material_risks.copy()
            new_next_focus = report.next_focus.copy()

            target_by_category = {
                "completed_work": new_completed_work,
                "active_blockers": new_active_blockers,
                "material_risks": new_material_risks,
                "next_focus": new_next_focus,
            }
            target = target_by_category.get(category)
            if target is None:
                raise ValueError(f"unsupported report fact category: {category}")
            if fact not in target:
                target.append(fact)

            report = report.model_copy(
                update={
                    "source_update_ids": new_source_update_ids,
                    "completed_work": new_completed_work,
                    "active_blockers": new_active_blockers,
                    "material_risks": new_material_risks,
                    "next_focus": new_next_focus,
                    "updated_at": datetime.now(UTC),
                }
            )
            return repo.save(report, expected_version=report.version)

        return self._store.run_transaction(_append)


class EditDailyLogCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    report_id: CanonicalId
    summary: str = Field(min_length=1, max_length=20_000)
    crew_summary: str | None = Field(default=None, max_length=5_000)
    weather_summary: str | None = Field(default=None, max_length=5_000)
    expected_version: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class DailyLogChange:
    report: DailyReport
    activity: ActivityEvent
    duplicate: bool = False


__all__ = ["DailyLogChange", "EditDailyLogCommand", "ReportService"]


def _report_id(project_id: str, report_date: date) -> str:
    return f"rpt_{project_id}_{report_date.isoformat()}"


def _edit_daily_log(
    session: RepositorySession,
    command: EditDailyLogCommand,
    occurred_at: datetime,
) -> DailyReport:
    reports = session.repository(DailyReport)
    current = reports.require(command.project_id, command.report_id)
    if current.version != command.expected_version:
        raise VersionConflictError(
            f"expected_version {command.expected_version} does not match current version {current.version}"
        )
    return reports.save(
        current.model_copy(
            update={
                "summary": command.summary,
                "crew_summary": command.crew_summary or None,
                "weather_summary": command.weather_summary or None,
                "updated_at": occurred_at,
            }
        ),
        expected_version=command.expected_version,
    )


def _apply_site_update_projection(
    session: RepositorySession,
    project_id: str,
    report_id: str,
    report_date: date,
    site_update: SiteUpdate,
    completed_work: Sequence[ReportFact],
    active_blockers: Sequence[ReportFact],
    material_risks: Sequence[ReportFact],
    next_focus: Sequence[ReportFact],
    occurred_at: datetime,
) -> DailyReport:
    reports = session.repository(DailyReport)
    current = reports.get(project_id, report_id)
    created_at = current.created_at if current is not None else occurred_at
    source_update_ids = list(current.source_update_ids) if current is not None else []
    if site_update.id not in source_update_ids:
        source_update_ids.append(site_update.id)

    merged_completed = _merge_facts(current.completed_work if current else (), completed_work)
    merged_blockers = _merge_facts(current.active_blockers if current else (), active_blockers)
    merged_materials = _merge_facts(current.material_risks if current else (), material_risks)
    merged_focus = _merge_facts(current.next_focus if current else (), next_focus)
    summary = (
        f"Daily report: {len(merged_completed)} completed, "
        f"{len(merged_blockers)} active risks, {len(merged_materials)} material risks, "
        f"and {len(merged_focus)} next-focus items."
    )
    desired = DailyReport(
        id=report_id,
        project_id=project_id,
        report_date=report_date,
        summary=summary,
        completed_work=merged_completed,
        active_blockers=merged_blockers,
        material_risks=merged_materials,
        next_focus=merged_focus,
        source_update_ids=source_update_ids,
        status=current.status if current is not None else ReportStatus.DRAFT,
        version=current.version if current is not None else 0,
        created_at=created_at,
        updated_at=occurred_at,
    )
    if current is None:
        return reports.create(desired)
    expected_version = reports.version_of(project_id, report_id)
    if expected_version is None:
        raise RuntimeError("daily report disappeared during projection")
    return reports.save(desired, expected_version=expected_version)


def _merge_facts(
    existing: Sequence[ReportFact],
    incoming: Sequence[ReportFact],
) -> list[ReportFact]:
    merged = list(existing)
    for fact in incoming:
        if fact not in merged:
            merged.append(fact)
    return merged
