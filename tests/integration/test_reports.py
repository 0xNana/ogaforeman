"""Integration tests for daily reports."""

from datetime import UTC, date, datetime

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import ActorType, MemberRole, SiteUpdateInputType
from app.domain.models import DailyReport, ReportFact, SiteUpdate
from app.repositories.memory import InMemoryRepositoryStore
from app.services.reports import ReportService


def test_daily_report_creation_and_append():
    store = InMemoryRepositoryStore()
    service = ReportService(store)

    project_id = "prj_test"
    report_date = date(2026, 8, 7)

    # Create or get
    report = service.get_or_create_report(project_id, report_date)
    assert report.project_id == project_id
    assert report.report_date == report_date
    assert len(report.completed_work) == 0

    # Append fact
    fact = ReportFact(summary="Completed first floor wiring", source_refs=["update_123"])
    report = service.append_fact(project_id, report_date, fact, "completed_work", "update_123")
    assert len(report.completed_work) == 1
    assert report.completed_work[0].summary == "Completed first floor wiring"
    assert "update_123" in report.source_update_ids


def test_daily_report_duplicate_append_idempotency():
    store = InMemoryRepositoryStore()
    service = ReportService(store)

    project_id = "prj_test"
    report_date = date(2026, 8, 7)

    fact = ReportFact(summary="Completed first floor wiring", source_refs=["update_123"])
    service.append_fact(project_id, report_date, fact, "completed_work", "update_123")

    # Reprocessing the same source update must not duplicate either its source link or fact.
    report2 = service.append_fact(project_id, report_date, fact, "completed_work", "update_123")

    assert len(report2.source_update_ids) == 1
    assert len(report2.completed_work) == 1


def test_site_update_projection_preserves_and_merges_all_daily_log_sections() -> None:
    store = InMemoryRepositoryStore()
    service = ReportService(store)
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_report123", subject="reporter"),
        project_id="prj_report123",
        role=MemberRole.MANAGER,
    )
    now = datetime(2026, 8, 16, 10, tzinfo=UTC)
    existing = DailyReport(
        id="rpt_prj_report123_2026-08-16",
        project_id="prj_report123",
        report_date=date(2026, 8, 16),
        summary="Existing daily report.",
        crew_summary="Crew A",
        weather_summary="Dry",
        in_progress_work=[ReportFact(summary="Electrical rough-in", source_refs=["su_old123"])],
        deliveries=[ReportFact(summary="Cement delivered", source_refs=["su_old123"])],
        inspections=[ReportFact(summary="Safety inspection", source_refs=["su_old123"])],
        photo_refs=["att_old123"],
    )
    store.repository(DailyReport).create(existing)
    update = SiteUpdate(
        id="su_new123",
        project_id="prj_report123",
        submitted_by="usr_report123",
        input_type=SiteUpdateInputType.TEXT,
        raw_text="New work update.",
        client_event_id="client-report-123",
        submitted_at=now,
        created_at=now,
        updated_at=now,
    )

    report = service.project_site_update(
        access,
        update,
        completed_work=[ReportFact(summary="Blockwork completed", source_refs=[update.id])],
        active_blockers=[],
        material_risks=[],
        next_focus=[],
        in_progress_work=[ReportFact(summary="Plastering in progress", source_refs=[update.id])],
        deliveries=[ReportFact(summary="Gypsum delivered", source_refs=[update.id])],
        inspections=[ReportFact(summary="Quality check", source_refs=[update.id])],
        photo_refs=["att_new123"],
        context=MutationContext(
            project_id=access.project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key="report:projection:new",
            source_event_id="evt_report123",
            agent_run_id="run_report123",
            occurred_at=now,
        ),
    )

    assert report.crew_summary == "Crew A"
    assert report.weather_summary == "Dry"
    assert {fact.summary for fact in report.in_progress_work} == {
        "Electrical rough-in",
        "Plastering in progress",
    }
    assert {fact.summary for fact in report.deliveries} == {"Cement delivered", "Gypsum delivered"}
    assert {fact.summary for fact in report.inspections} == {"Safety inspection", "Quality check"}
    assert report.photo_refs == ["att_old123", "att_new123"]
    assert report.completed_work[0].summary == "Blockwork completed"
