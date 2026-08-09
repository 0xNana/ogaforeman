from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from scripts.verify_backups import verify_backups


class StubRunner:
    def __init__(self, responses: Sequence[object]) -> None:
        self.responses = list(responses)
        self.commands: list[tuple[str, ...]] = []

    def run_json(self, arguments: Sequence[str]) -> object:
        self.commands.append(tuple(arguments))
        return self.responses.pop(0)


def test_backup_verification_defaults_to_read_only_dry_run() -> None:
    evidence = verify_backups(project_id="oga-staging", bucket="oga-media")

    assert evidence.mode == "dry_run"
    assert evidence.passed is None
    assert {check.status for check in evidence.checks} == {"planned"}


def test_live_backup_verification_accepts_recent_backup_and_soft_delete() -> None:
    runner = StubRunner(
        (
            [
                {
                    "name": "projects/oga-staging/locations/nam5/backups/backup-1",
                    "state": "READY",
                    "snapshotTime": "2026-08-08T06:00:00Z",
                }
            ],
            {"softDeletePolicy": {"retentionDurationSeconds": "604800"}},
        )
    )

    evidence = verify_backups(
        project_id="oga-staging",
        bucket="oga-media",
        live=True,
        now=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        runner=runner,
    )

    assert evidence.passed is True
    assert evidence.event == "backup_verification_completed"
    assert len(runner.commands) == 2


def test_live_backup_verification_accepts_current_gcloud_storage_shape() -> None:
    runner = StubRunner(
        (
            [
                {
                    "name": "projects/oga-staging/locations/europe-west1/backups/backup-1",
                    "state": "READY",
                    "snapshotTime": "2026-08-08T06:00:00Z",
                }
            ],
            {
                "versioning_enabled": True,
                "soft_delete_policy": {"retentionDurationSeconds": "2592000"},
            },
        )
    )

    evidence = verify_backups(
        project_id="oga-staging",
        bucket="oga-media",
        live=True,
        now=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        runner=runner,
    )

    assert evidence.passed is True
    assert "versioning enabled" in evidence.checks[1].detail
    assert "2592000 seconds" in evidence.checks[1].detail


def test_live_backup_verification_fails_closed_without_protection() -> None:
    runner = StubRunner(([], {"versioning": {"enabled": False}}))

    evidence = verify_backups(
        project_id="oga-staging",
        bucket="oga-media",
        live=True,
        now=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        runner=runner,
    )

    assert evidence.passed is False
    assert evidence.event == "backup_verification_failed"
    assert [check.status for check in evidence.checks] == ["failed", "failed"]
