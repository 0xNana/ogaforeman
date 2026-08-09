"""Integration tests for daily reports."""

from datetime import date

from app.domain.models import ReportFact
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
