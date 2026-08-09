from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.domain.enums import ActorType
from app.domain.models import ActivityEvent, DailyReport
from app.repositories.memory import InMemoryRepositoryStore
from scripts.rebuild_projections import rebuild_daily_report


def _activity(
    activity_id: str,
    *,
    action: str,
    summary: str,
    entity_id: str,
    source_event_id: str,
) -> ActivityEvent:
    return ActivityEvent(
        id=activity_id,
        project_id="prj_projection123",
        actor_type=ActorType.AGENT,
        actor_id="agt_oga123",
        action=action,
        entity_type="task" if action.startswith("task.") else "material",
        entity_id=entity_id,
        summary=summary,
        source_event_id=source_event_id,
        created_at=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
    )


def test_projection_rebuild_is_dry_run_by_default() -> None:
    store = InMemoryRepositoryStore()
    activities = (
        _activity(
            "act_complete123",
            action="task.completed",
            summary="Blockwork marked complete",
            entity_id="tsk_blockwork123",
            source_event_id="upd_morning123",
        ),
    )

    evidence = rebuild_daily_report(
        store,
        project_id="prj_projection123",
        report_date=date(2026, 8, 8),
        activities=activities,
        timezone_name="Africa/Accra",
    )

    assert evidence.dry_run is True
    assert evidence.changed is True
    assert evidence.applied is False
    assert store.repository(DailyReport).list("prj_projection123") == ()


def test_projection_rebuild_applies_atomically_and_is_stable_on_rerun() -> None:
    store = InMemoryRepositoryStore()
    activities = (
        _activity(
            "act_complete123",
            action="task.completed",
            summary="Blockwork marked complete",
            entity_id="tsk_blockwork123",
            source_event_id="upd_morning123",
        ),
        _activity(
            "act_material123",
            action="material.requested",
            summary="Requested 90 bags of cement",
            entity_id="mrq_cement123",
            source_event_id="upd_morning123",
        ),
    )
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

    first = rebuild_daily_report(
        store,
        project_id="prj_projection123",
        report_date=date(2026, 8, 8),
        activities=activities,
        timezone_name="Africa/Accra",
        apply=True,
        operation_id="restore-incident-001",
        now=now,
    )
    second = rebuild_daily_report(
        store,
        project_id="prj_projection123",
        report_date=date(2026, 8, 8),
        activities=activities,
        timezone_name="Africa/Accra",
        apply=True,
        operation_id="restore-incident-001",
        now=now,
    )
    report = store.repository(DailyReport).require(
        "prj_projection123", "rpt_prj_projection123_2026-08-08"
    )
    rebuild_activities = [
        activity
        for activity in store.repository(ActivityEvent).list("prj_projection123")
        if activity.action == "report.projection_rebuilt"
    ]

    assert first.applied is True
    assert second.changed is False
    assert second.applied is False
    assert len(report.completed_work) == 1
    assert len(report.material_risks) == 1
    assert report.source_update_ids == ["upd_morning123"]
    assert len(rebuild_activities) == 1


def test_projection_rebuild_refuses_unbounded_source_sets() -> None:
    store = InMemoryRepositoryStore()
    activities = tuple(
        _activity(
            f"act_capacity{index:03d}",
            action="task.completed",
            summary=f"Task {index} complete",
            entity_id=f"tsk_capacity{index:03d}",
            source_event_id=f"upd_capacity{index:03d}",
        )
        for index in range(3)
    )

    with pytest.raises(ValueError, match="limit is 2"):
        rebuild_daily_report(
            store,
            project_id="prj_projection123",
            report_date=date(2026, 8, 8),
            activities=activities,
            timezone_name="Africa/Accra",
            max_activities=2,
        )
