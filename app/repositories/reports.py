"""Authorized repository boundary for daily reports."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import DailyReport
from app.repositories.interfaces import ProjectRepository, RepositorySession, RepositoryStore


class ReportRepository:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def get(self, project_id: str, report_id: str) -> DailyReport | None:
        return self._store.repository(DailyReport).get(project_id, report_id)

    def require(self, project_id: str, report_id: str) -> DailyReport:
        return self._store.repository(DailyReport).require(project_id, report_id)

    def list(self, project_id: str) -> Sequence[DailyReport]:
        return self._store.repository(DailyReport).list(project_id)

    def create(self, report: DailyReport) -> DailyReport:
        return self._store.repository(DailyReport).create(report)

    def save(self, report: DailyReport, *, expected_version: int | None = None) -> DailyReport:
        return self._store.repository(DailyReport).save(report, expected_version=expected_version)

    @staticmethod
    def for_session(session: RepositorySession) -> ProjectRepository[DailyReport]:
        return session.repository(DailyReport)


__all__ = ["ReportRepository"]
