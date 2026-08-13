from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.enums import AttachmentUploadStatus, MaterialRequestStatus, TaskSource, TaskStatus
from app.domain.models import (
    ActivityEvent,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    Project,
    Task,
)


def empty_report_projection() -> dict[str, object]:
    return {
        "date": "No report yet",
        "completed": [],
        "inProgress": [],
        "blocked": [],
        "materials": [],
        "tomorrow": [],
        "risks": [],
        "photos": [],
    }


def project_snapshot_projection(
    project: Project,
    *,
    tasks: Sequence[Task],
    materials: Sequence[Material],
    material_requests: Sequence[MaterialRequest],
    approvals: Sequence[Approval],
    activities: Sequence[ActivityEvent],
    reports: Sequence[DailyReport],
    attachments: Sequence[Attachment] = (),
    issues: Sequence[Issue] = (),
    viewer_id: str | None = None,
) -> dict[str, object]:
    timezone = ZoneInfo(project.timezone)
    requests_by_material = _latest_requests_by_material(material_requests)
    material_names = {material.id: material.name for material in materials}
    downstream_ids: dict[str, list[str]] = {task.id: [] for task in tasks}
    for task in tasks:
        for dependency_id in task.dependency_ids:
            downstream_ids.setdefault(dependency_id, []).append(task.id)
    blocked_task_ids = {task.id for task in tasks if task.status is TaskStatus.BLOCKED}
    latest_report = max(
        reports, key=lambda report: (report.report_date, report.updated_at), default=None
    )
    verified_attachments = [
        attachment
        for attachment in attachments
        if attachment.upload_status is AttachmentUploadStatus.VERIFIED
    ]
    return {
        "viewerId": viewer_id,
        "project": {
            "id": project.id,
            "name": project.name,
            "location": project.location,
            "status": project.status.value.upper(),
            "timezone": project.timezone,
        },
        "tasks": [
            task_projection(
                task,
                timezone,
                downstream_ids=downstream_ids.get(task.id, []),
                blocked_task_ids=blocked_task_ids,
            )
            for task in sorted(tasks, key=lambda item: item.title.casefold())
        ],
        "materials": [
            material_projection(material, requests_by_material.get(material.id))
            for material in sorted(materials, key=lambda item: item.name.casefold())
        ],
        "materialRequests": [
            material_request_projection(request, material_names, timezone)
            for request in sorted(material_requests, key=lambda item: item.updated_at, reverse=True)
        ],
        "issues": [
            issue_projection(issue, timezone)
            for issue in sorted(issues, key=lambda item: item.updated_at, reverse=True)
        ],
        "approvals": [
            approval_projection(approval, timezone)
            for approval in sorted(approvals, key=lambda item: item.requested_at, reverse=True)
        ],
        "activities": [
            activity_projection(activity, timezone)
            for activity in sorted(activities, key=lambda item: item.created_at, reverse=True)
        ],
        "dailyLogs": [
            daily_log_projection(report)
            for report in sorted(reports, key=lambda item: item.report_date, reverse=True)
        ],
        "photos": [
            photo_projection(attachment, timezone, tasks, issues, reports)
            for attachment in sorted(
                verified_attachments, key=lambda item: item.created_at, reverse=True
            )
            if attachment.content_type.startswith("image/")
        ],
        "documents": [
            document_projection(attachment, timezone, tasks, issues, reports)
            for attachment in sorted(
                verified_attachments, key=lambda item: item.created_at, reverse=True
            )
            if attachment.content_type == "application/pdf"
        ],
        "report": report_projection(latest_report) if latest_report else empty_report_projection(),
    }


def task_projection(
    task: Task,
    timezone: ZoneInfo,
    *,
    downstream_ids: Sequence[str] = (),
    blocked_task_ids: set[str] | None = None,
) -> dict[str, object]:
    status = {
        TaskStatus.PROPOSED: "PENDING",
        TaskStatus.PLANNED: "PENDING",
        TaskStatus.CANCELLED: "PENDING",
    }.get(task.status, task.status.value.upper())
    if task.actual_completion is not None:
        due_label = f"Completed {task.actual_completion.astimezone(timezone):%-d %b}"
    elif task.planned_end is not None:
        due_label = f"Due {task.planned_end.astimezone(timezone):%-d %b}"
    else:
        due_label = "Not scheduled"
    note = task.description or f"{_display_decimal(task.completion_percent)}% complete."
    is_follow_up = task.source is TaskSource.SITE_UPDATE and bool(task.source_refs)
    planned_start = _local_date(task.planned_start, timezone)
    planned_finish = _local_date(task.planned_end, timezone)
    finish_date = planned_finish or _local_date(task.actual_completion, timezone)
    duration_days = (
        (
            task.planned_end.astimezone(timezone).date()
            - task.planned_start.astimezone(timezone).date()
        ).days
        + 1
        if task.planned_start is not None and task.planned_end is not None
        else None
    )
    return {
        "id": task.id,
        "title": task.title,
        "status": status,
        "assignee": task.assigned_to or "Unassigned",
        "location": None,
        "trade": None,
        "startLabel": _date_label(task.planned_start, timezone, default="Not set"),
        "startDate": planned_start,
        "finishDate": finish_date,
        "durationDays": duration_days,
        "isMilestone": task.is_milestone,
        "downstreamIds": list(downstream_ids),
        "atRisk": bool(set(task.dependency_ids) & (blocked_task_ids or set())),
        "dueLabel": due_label,
        "progress": _number(task.completion_percent),
        "dependencyIds": list(task.dependency_ids),
        "blocking": None,
        "note": note,
        "needsAttention": is_follow_up
        and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED},
        "sourceRefs": list(task.source_refs),
    }


def issue_projection(issue: Issue, timezone: ZoneInfo) -> dict[str, object]:
    return {
        "id": issue.id,
        "description": issue.description,
        "type": issue.type.value.upper(),
        "severity": issue.severity.value.upper(),
        "status": issue.status.value.upper(),
        "owner": issue.owner_id or "Unassigned",
        "dueLabel": _date_label(issue.due_at, timezone),
        "taskIds": list(issue.task_ids),
        "evidenceRefs": list(issue.evidence_refs),
        "location": None,
    }


def material_request_projection(
    request: MaterialRequest,
    material_names: Mapping[str, str],
    timezone: ZoneInfo,
) -> dict[str, object]:
    return {
        "id": request.id,
        "materialId": request.material_id,
        "materialName": material_names.get(request.material_id, "Unknown material"),
        "quantity": _number(request.quantity),
        "unit": request.unit,
        "reason": request.reason,
        "neededBy": _date_label(request.needed_by, timezone),
        "status": request.status.value.upper(),
        "approvalId": request.approval_id,
    }


def material_projection(
    material: Material,
    latest_request: MaterialRequest | None,
) -> dict[str, object]:
    required = material.upcoming_requirement_quantity or material.minimum_required_quantity
    status = "OK"
    if latest_request is not None and latest_request.status is MaterialRequestStatus.DELAYED:
        status = "DELAYED"
    elif latest_request is not None and latest_request.status in {
        MaterialRequestStatus.AWAITING_APPROVAL,
        MaterialRequestStatus.APPROVED,
        MaterialRequestStatus.SUBMITTED,
        MaterialRequestStatus.CONFIRMED,
    }:
        status = "REQUESTED"
    elif material.available_quantity < required:
        status = "LOW"
    shortage = max(required - material.available_quantity, Decimal("0"))
    note = (
        f"Short by {_display_decimal(shortage)} {material.unit} for upcoming work."
        if shortage > 0
        else "Stock covers the current recorded requirement."
    )
    return {
        "id": material.id,
        "name": material.name,
        "quantity": _number(material.available_quantity),
        "unit": material.unit,
        "need": _number(required),
        "forWork": "Upcoming work",
        "status": status,
        "note": note,
        "version": material.version,
    }


def approval_projection(approval: Approval, timezone: ZoneInfo) -> dict[str, object]:
    action = approval.proposed_action
    material_name = _text(action.get("material_name"))
    title = _text(action.get("title")) or (
        f"{material_name} request"
        if material_name
        else approval.action_type.value.replace("_", " ").title()
    )
    quantity_value = _text(action.get("quantity"))
    unit = _text(action.get("unit"))
    quantity = " ".join(part for part in (quantity_value, unit) if part) or "Review proposal"
    needed_by = _text(action.get("needed_by")) or "Not specified"
    if needed_by != "Not specified":
        try:
            parsed_needed_by = datetime.fromisoformat(needed_by)
            if parsed_needed_by.tzinfo is not None:
                needed_by = parsed_needed_by.astimezone(timezone).strftime("%d %b").lstrip("0")
        except ValueError:
            pass
    affected_task_ids = action.get("affected_task_ids")
    needed_for = _text(action.get("needed_for"))
    if not needed_for and isinstance(affected_task_ids, list) and affected_task_ids:
        needed_for = f"{len(affected_task_ids)} affected task{'s' if len(affected_task_ids) != 1 else ''}"
    resolved_at = approval.resolved_at.astimezone(timezone) if approval.resolved_at else None
    return {
        "id": approval.id,
        "type": approval.action_type.value.replace("_", " ").title(),
        "title": title,
        "status": approval.status.value.upper(),
        "quantity": quantity,
        "neededBy": needed_by,
        "neededFor": needed_for or "Not specified",
        "reason": approval.reason,
        "requestedBy": "Oga" if approval.requested_by == "system" else approval.requested_by,
        "date": approval.requested_at.astimezone(timezone).strftime("%d %b, %H:%M").lstrip("0"),
        "resolvedBy": approval.resolved_by,
        "resolvedAt": resolved_at.strftime("%d %b, %H:%M").lstrip("0") if resolved_at else None,
        "version": approval.version,
    }


def activity_projection(activity: ActivityEvent, timezone: ZoneInfo) -> dict[str, object]:
    kind = _activity_kind(activity)
    needs_action = activity.action in {"approval.requested", "material.requested"}
    occurred_at = activity.created_at.astimezone(timezone)
    return {
        "id": activity.id,
        "kind": kind,
        "title": activity.summary,
        "description": activity.summary,
        "date": occurred_at.strftime("%H:%M"),
        "dateLabel": occurred_at.strftime("%A, %-d %B %Y"),
        "occurredAt": occurred_at.isoformat(),
        "user": activity.actor_id or "Oga",
        "actorType": activity.actor_type.value,
        "action": activity.action,
        "entityType": activity.entity_type,
        "entityId": activity.entity_id,
        "needsAction": needs_action,
        "actionLabel": "Review request" if needs_action else None,
    }


def report_projection(report: DailyReport) -> dict[str, object]:
    return {
        "date": report.report_date.strftime("%A, %-d %B"),
        "completed": [fact.summary for fact in report.completed_work],
        "inProgress": [fact.summary for fact in report.in_progress_work],
        "blocked": [fact.summary for fact in report.active_blockers],
        "materials": [fact.summary for fact in report.material_risks],
        "tomorrow": [fact.summary for fact in report.next_focus],
        "risks": [fact.summary for fact in (*report.active_blockers, *report.material_risks)],
        "photos": list(report.photo_refs),
    }


def daily_log_projection(report: DailyReport) -> dict[str, object]:
    return {
        "id": report.id,
        "date": report.report_date.strftime("%A, %-d %B"),
        "dateIso": report.report_date.isoformat(),
        "summary": report.summary,
        "crew": report.crew_summary,
        "weather": report.weather_summary,
        "completed": [fact.summary for fact in report.completed_work],
        "inProgress": [fact.summary for fact in report.in_progress_work],
        "blocked": [fact.summary for fact in report.active_blockers],
        "materials": [fact.summary for fact in report.material_risks],
        "deliveries": [fact.summary for fact in report.deliveries],
        "inspections": [fact.summary for fact in report.inspections],
        "photos": list(report.photo_refs),
        "tomorrow": [fact.summary for fact in report.next_focus],
        "risks": [fact.summary for fact in (*report.active_blockers, *report.material_risks)],
        "sourceUpdateCount": len(report.source_update_ids),
        "status": report.status.value.upper(),
        "version": report.version,
    }


def photo_projection(
    attachment: Attachment,
    timezone: ZoneInfo,
    tasks: Sequence[Task],
    issues: Sequence[Issue],
    reports: Sequence[DailyReport],
) -> dict[str, object]:
    task_ids, issue_ids, daily_log_ids = _attachment_links(attachment, tasks, issues, reports)
    return {
        "id": attachment.id,
        "name": attachment.original_name or attachment.id,
        "contentType": attachment.content_type,
        "date": attachment.created_at.astimezone(timezone).strftime("%-d %b %Y, %H:%M"),
        "dateIso": attachment.created_at.isoformat(),
        "uploadedBy": attachment.uploaded_by or "Not recorded",
        "location": _text(attachment.metadata.get("location")) or None,
        "siteUpdateId": attachment.site_update_id,
        "taskIds": task_ids,
        "issueIds": issue_ids,
        "dailyLogIds": daily_log_ids,
    }


def document_projection(
    attachment: Attachment,
    timezone: ZoneInfo,
    tasks: Sequence[Task],
    issues: Sequence[Issue],
    reports: Sequence[DailyReport],
) -> dict[str, object]:
    task_ids, issue_ids, daily_log_ids = _attachment_links(attachment, tasks, issues, reports)
    return {
        "id": attachment.id,
        "name": attachment.original_name or attachment.id,
        "type": "PDF",
        "revision": _text(attachment.metadata.get("revision")) or None,
        "uploadedBy": attachment.uploaded_by or "Not recorded",
        "updated": attachment.created_at.astimezone(timezone).strftime("%-d %b %Y"),
        "siteUpdateId": attachment.site_update_id,
        "linkedRecords": [*task_ids, *issue_ids, *daily_log_ids],
    }


def _attachment_links(
    attachment: Attachment,
    tasks: Sequence[Task],
    issues: Sequence[Issue],
    reports: Sequence[DailyReport],
) -> tuple[list[str], list[str], list[str]]:
    source_id = attachment.site_update_id
    if source_id is None:
        return [], [], []
    return (
        [task.id for task in tasks if source_id in task.source_refs],
        [issue.id for issue in issues if source_id in issue.evidence_refs],
        [report.id for report in reports if source_id in report.source_update_ids],
    )


def _latest_requests_by_material(
    requests: Sequence[MaterialRequest],
) -> dict[str, MaterialRequest]:
    latest: dict[str, MaterialRequest] = {}
    for request in requests:
        existing = latest.get(request.material_id)
        if existing is None or request.updated_at > existing.updated_at:
            latest[request.material_id] = request
    return latest


def _activity_kind(activity: ActivityEvent) -> str:
    if activity.entity_type == "task":
        return "progress"
    if activity.entity_type == "issue":
        return "blocker"
    if activity.entity_type in {"material", "material_request"}:
        return "material"
    if activity.entity_type == "report":
        return "report"
    if activity.entity_type == "approval":
        return "approval"
    return "update"


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _date_label(value: Any, timezone: ZoneInfo, *, default: str = "Not specified") -> str:
    if value is None:
        return default
    return value.astimezone(timezone).strftime("%-d %b")


def _local_date(value: Any, timezone: ZoneInfo) -> str | None:
    return value.astimezone(timezone).date().isoformat() if value is not None else None


def _display_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


__all__ = [
    "activity_projection",
    "approval_projection",
    "empty_report_projection",
    "daily_log_projection",
    "material_projection",
    "material_request_projection",
    "photo_projection",
    "document_projection",
    "issue_projection",
    "project_snapshot_projection",
    "report_projection",
    "task_projection",
]
