"""Rebuild one daily-report projection from durable activity events.

Dry-run is the default. Applying a rebuild requires an explicit operation ID so
retries use the same mutation/activity idempotency scope.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.config.settings import Settings
from app.domain.activity import ActivitySpec, MutationContext
from app.domain.enums import ActorType, ReportStatus
from app.domain.models import ActivityEvent, DailyReport, ReportFact
from app.infrastructure.firestore import create_firestore_client, decode_firestore_value
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.services.activity import ActivityService


_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CATEGORY_BY_ACTION = {
    "task.completed": "completed_work",
    "task.blocked": "active_blockers",
    "issue.created": "active_blockers",
    "issue.detected": "active_blockers",
    "material.quantity_updated": "material_risks",
    "material.requested": "material_risks",
    "task.planned": "next_focus",
    "daily_brief.focus_added": "next_focus",
}


@dataclass(frozen=True, slots=True)
class ProjectionEvidence:
    project_id: str
    report_date: str
    timezone: str
    dry_run: bool
    changed: bool
    applied: bool
    duplicate: bool
    source_activity_count: int
    source_digest: str
    report_id: str
    operation_id: str | None
    duration_ms: float
    generated_at: str

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def rebuild_daily_report(
    store: RepositoryStore,
    *,
    project_id: str,
    report_date: date,
    activities: Sequence[ActivityEvent],
    timezone_name: str,
    apply: bool = False,
    operation_id: str | None = None,
    max_activities: int = 500,
    now: datetime | None = None,
) -> ProjectionEvidence:
    started = monotonic()
    if max_activities < 1 or max_activities > 5_000:
        raise ValueError("max_activities must be between 1 and 5000")
    if apply and not operation_id:
        raise ValueError("operation_id is required when --apply is used")
    if operation_id and not _OPERATION_ID_RE.fullmatch(operation_id):
        raise ValueError("operation_id must be an opaque identifier")

    selected = select_activity_slice(
        activities,
        report_date=report_date,
        timezone_name=timezone_name,
        max_activities=max_activities,
    )
    source_digest = _source_digest(selected)
    report_id = _report_id(project_id, report_date)
    existing = store.repository(DailyReport).get(project_id, report_id)
    desired = _build_report(
        project_id=project_id,
        report_date=report_date,
        activities=selected,
        existing=existing,
    )
    changed = existing is None or not _same_projection(existing, desired)
    applied = False
    duplicate = False

    if apply and changed:
        assert operation_id is not None
        current_time = _aware_now(now)
        source_event_id = next(
            (
                activity.source_event_id
                for activity in reversed(selected)
                if activity.source_event_id
            ),
            f"evt_rebuild_{sha256(operation_id.encode('utf-8')).hexdigest()[:20]}",
        )
        context = MutationContext(
            project_id=project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=source_event_id,
            idempotency_key=(
                f"projection:{report_id}:{sha256(operation_id.encode('utf-8')).hexdigest()[:24]}"
            ),
            occurred_at=current_time,
        )
        spec = ActivitySpec(
            action="report.projection_rebuilt",
            entity_type="daily_report",
            entity_id=report_id,
            summary=f"Rebuilt daily report from {len(selected)} durable activities",
            metadata={
                "report_date": report_date.isoformat(),
                "source_activity_count": len(selected),
                "source_digest": source_digest,
                "operation_id": operation_id,
            },
        )

        def persist(session: RepositorySession) -> DailyReport:
            reports = session.repository(DailyReport)
            current = reports.get(project_id, report_id)
            if current is None:
                return reports.create(
                    desired.model_copy(
                        update={"created_at": current_time, "updated_at": current_time}
                    )
                )
            rebuilt = desired.model_copy(
                update={
                    "version": current.version,
                    "created_at": current.created_at,
                    "updated_at": current_time,
                    "status": current.status,
                }
            )
            return reports.save(rebuilt, expected_version=current.version)

        result = ActivityService(store).mutate(
            context,
            spec,
            persist,
            replay=lambda session, _activity: session.repository(DailyReport).require(
                project_id, report_id
            ),
        )
        applied = True
        duplicate = result.duplicate

    duration_ms = (monotonic() - started) * 1_000
    return ProjectionEvidence(
        project_id=project_id,
        report_date=report_date.isoformat(),
        timezone=timezone_name,
        dry_run=not apply,
        changed=changed,
        applied=applied,
        duplicate=duplicate,
        source_activity_count=len(selected),
        source_digest=source_digest,
        report_id=report_id,
        operation_id=operation_id,
        duration_ms=round(duration_ms, 3),
        generated_at=_aware_now(now).isoformat().replace("+00:00", "Z"),
    )


def select_activity_slice(
    activities: Sequence[ActivityEvent],
    *,
    report_date: date,
    timezone_name: str,
    max_activities: int,
) -> tuple[ActivityEvent, ...]:
    timezone = ZoneInfo(timezone_name)
    selected = tuple(
        sorted(
            (
                activity
                for activity in activities
                if activity.created_at.astimezone(timezone).date() == report_date
                and activity.action in _CATEGORY_BY_ACTION
            ),
            key=lambda activity: (activity.created_at, activity.id),
        )
    )
    if len(selected) > max_activities:
        raise ValueError(
            f"projection source has {len(selected)} activities; limit is {max_activities}"
        )
    return selected


def load_firestore_activities(
    client: firestore.Client,
    *,
    project_id: str,
    report_date: date,
    timezone_name: str,
    max_activities: int,
) -> tuple[ActivityEvent, ...]:
    timezone = ZoneInfo(timezone_name)
    local_start = datetime.combine(report_date, time.min, tzinfo=timezone)
    local_end = local_start + timedelta(days=1)
    collection = client.collection("projects").document(project_id).collection("activity")
    query = (
        collection.where(filter=FieldFilter("created_at", ">=", local_start.astimezone(UTC)))
        .where(filter=FieldFilter("created_at", "<", local_end.astimezone(UTC)))
        .order_by("created_at")
        .limit(max_activities + 1)
    )
    activities: list[ActivityEvent] = []
    for snapshot in query.stream():
        payload = decode_firestore_value(snapshot.to_dict() or {})
        payload.pop("_repository_version", None)
        activities.append(ActivityEvent.model_validate(payload))
    if len(activities) > max_activities:
        raise ValueError(
            f"projection source exceeds max_activities={max_activities}; narrow the recovery"
        )
    return tuple(activities)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild an Oga daily-report projection")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--report-date", type=date.fromisoformat, required=True)
    parser.add_argument("--timezone", help="project IANA timezone")
    parser.add_argument("--max-activities", type=int, default=500)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operation-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    settings = Settings()
    timezone_name = args.timezone or settings.default_project_timezone
    client = create_firestore_client(settings)
    activities = load_firestore_activities(
        client,
        project_id=args.project_id,
        report_date=args.report_date,
        timezone_name=timezone_name,
        max_activities=args.max_activities,
    )
    evidence = rebuild_daily_report(
        FirestoreRepositoryStore(client),
        project_id=args.project_id,
        report_date=args.report_date,
        activities=activities,
        timezone_name=timezone_name,
        apply=args.apply,
        operation_id=args.operation_id,
        max_activities=args.max_activities,
    )
    encoded = json.dumps(evidence.as_json(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


def _build_report(
    *,
    project_id: str,
    report_date: date,
    activities: Sequence[ActivityEvent],
    existing: DailyReport | None,
) -> DailyReport:
    categories: dict[str, list[ReportFact]] = {
        "completed_work": [],
        "active_blockers": [],
        "material_risks": [],
        "next_focus": [],
    }
    source_update_ids: list[str] = []
    for activity in activities:
        category = _CATEGORY_BY_ACTION[activity.action]
        source_refs = [activity.id]
        if activity.source_event_id:
            source_refs.insert(0, activity.source_event_id)
            if activity.source_event_id.startswith(("upd_", "sup_")):
                source_update_ids.append(activity.source_event_id)
        fact = ReportFact(
            summary=activity.summary,
            source_refs=list(dict.fromkeys(source_refs)),
            metadata={
                "activity_id": activity.id,
                "action": activity.action,
                "entity_type": activity.entity_type,
                "entity_id": activity.entity_id,
            },
        )
        if fact not in categories[category]:
            categories[category].append(fact)

    created_at = existing.created_at if existing else datetime.combine(report_date, time.min, UTC)
    updated_at = existing.updated_at if existing else created_at
    return DailyReport(
        id=_report_id(project_id, report_date),
        project_id=project_id,
        report_date=report_date,
        summary=f"Daily report rebuilt from {len(activities)} durable activity events.",
        completed_work=categories["completed_work"],
        active_blockers=categories["active_blockers"],
        material_risks=categories["material_risks"],
        next_focus=categories["next_focus"],
        source_update_ids=list(dict.fromkeys(source_update_ids)),
        status=existing.status if existing else ReportStatus.DRAFT,
        version=existing.version if existing else 0,
        created_at=created_at,
        updated_at=updated_at,
    )


def _same_projection(left: DailyReport, right: DailyReport) -> bool:
    fields = (
        "summary",
        "completed_work",
        "active_blockers",
        "material_risks",
        "next_focus",
        "source_update_ids",
        "status",
    )
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def _report_id(project_id: str, report_date: date) -> str:
    return f"rpt_{project_id}_{report_date.isoformat()}"


def _source_digest(activities: Sequence[ActivityEvent]) -> str:
    material = "\n".join(
        f"{activity.id}:{activity.action}:{activity.source_event_id or ''}"
        for activity in activities
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _aware_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
