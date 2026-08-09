"""Reporter agent for summarizing daily events."""

from typing import Any
from app.agents.registry import registry
from app.domain.models import DailyReport


class ReporterAgent:
    def __init__(self) -> None:
        self.config = registry.get_agent_config("communicator")

    def format_daily_report(self, report: DailyReport) -> dict[str, Any]:
        """Convert a DailyReport domain entity into a formatted presentation."""
        return {
            "report_id": report.id,
            "project_id": report.project_id,
            "date": report.report_date.isoformat(),
            "summary": report.summary,
            "completed_work": [fact.model_dump() for fact in report.completed_work],
            "active_blockers": [fact.model_dump() for fact in report.active_blockers],
            "material_risks": [fact.model_dump() for fact in report.material_risks],
            "next_focus": [fact.model_dump() for fact in report.next_focus],
            "status": report.status.value,
        }


reporter_agent = ReporterAgent()

__all__ = ["ReporterAgent", "reporter_agent"]
