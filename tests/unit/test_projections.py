from datetime import UTC, date, datetime

from app.api.v1.projections import daily_log_projection, report_projection
from app.domain.models import DailyReport, ReportFact


def _report() -> DailyReport:
    now = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)
    return DailyReport(
        id="rpt_project_2026-08-16",
        project_id="prj_project",
        report_date=date(2026, 8, 16),
        summary="Daily report",
        active_blockers=[
            ReportFact(
                summary="Electrical work is blocked.",
                source_refs=["iss_electrical"],
                metadata={"issue_type": "blocker"},
            ),
            ReportFact(
                summary="Plasterboard delivery postponed to tomorrow morning due to access issues.",
                source_refs=["iss_delivery"],
                metadata={"issue_type": "delay_risk"},
            ),
        ],
        created_at=now,
        updated_at=now,
    )


def test_delay_risk_is_not_presented_as_a_blocked_task() -> None:
    report = _report()

    assert daily_log_projection(report)["blocked"] == ["Electrical work is blocked."]
    assert report_projection(report)["blocked"] == ["Electrical work is blocked."]
    assert "Plasterboard delivery postponed to tomorrow morning due to access issues." in report_projection(report)["risks"]
