from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.enums import MaterialRequestStatus, TaskStatus
from app.domain.models import (
    ActivityEvent,
    Approval,
    DailyReport,
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
) -> dict[str, object]:
    timezone = ZoneInfo(project.timezone)
    requests_by_material = _latest_requests_by_material(material_requests)
    latest_report = max(
        reports, key=lambda report: (report.report_date, report.updated_at), default=None
    )
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "location": project.location,
            "status": project.status.value.upper(),
            "timezone": project.timezone,
        },
        "tasks": [
            task_projection(task, timezone)
            for task in sorted(tasks, key=lambda item: item.title.casefold())
        ],
        "materials": [
            material_projection(material, requests_by_material.get(material.id))
            for material in sorted(materials, key=lambda item: item.name.casefold())
        ],
        "approvals": [
            approval_projection(approval, timezone)
            for approval in sorted(approvals, key=lambda item: item.requested_at, reverse=True)
        ],
        "activities": [
            activity_projection(activity, timezone)
            for activity in sorted(activities, key=lambda item: item.created_at, reverse=True)
        ],
        "report": report_projection(latest_report) if latest_report else empty_report_projection(),
    }


def task_projection(task: Task, timezone: ZoneInfo) -> dict[str, object]:
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
    return {
        "id": task.id,
        "title": task.title,
        "status": status,
        "assignee": task.assigned_to or "Unassigned",
        "dueLabel": due_label,
        "blocking": None,
        "note": note,
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
    return {
        "id": approval.id,
        "type": approval.action_type.value.replace("_", " ").title(),
        "title": title,
        "status": approval.status.value.upper(),
        "quantity": quantity,
        "neededBy": needed_by,
        "reason": approval.reason,
        "requestedBy": "Oga" if approval.requested_by == "system" else approval.requested_by,
        "date": approval.requested_at.astimezone(timezone).strftime("%d %b, %H:%M").lstrip("0"),
        "version": approval.version,
    }


def activity_projection(activity: ActivityEvent, timezone: ZoneInfo) -> dict[str, object]:
    kind = _activity_kind(activity)
    needs_action = activity.action in {"approval.requested", "material.requested"}
    return {
        "id": activity.id,
        "kind": kind,
        "title": activity.summary,
        "description": activity.summary,
        "date": activity.created_at.astimezone(timezone).strftime("%H:%M"),
        "user": activity.actor_id or "Oga",
        "needsAction": needs_action,
        "actionLabel": "Review request" if needs_action else None,
    }


def report_projection(report: DailyReport) -> dict[str, object]:
    return {
        "date": report.report_date.strftime("%A, %-d %B"),
        "completed": [fact.summary for fact in report.completed_work],
        "inProgress": [],
        "blocked": [fact.summary for fact in report.active_blockers],
        "materials": [fact.summary for fact in report.material_risks],
        "tomorrow": [fact.summary for fact in report.next_focus],
        "risks": [fact.summary for fact in (*report.active_blockers, *report.material_risks)],
        "photos": [],
    }


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


def _display_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


__all__ = [
    "activity_projection",
    "approval_projection",
    "empty_report_projection",
    "material_projection",
    "project_snapshot_projection",
    "report_projection",
    "task_projection",
]
