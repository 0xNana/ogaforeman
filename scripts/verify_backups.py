"""Verify Firestore backup visibility and Cloud Storage deletion protection.

The command is dry-run by default. `--live` executes read-only gcloud commands
and writes bounded JSON evidence suitable for a release artifact or Cloud log.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BackupCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class BackupEvidence:
    event: str
    mode: str
    project_id: str
    bucket: str
    checked_at: str
    passed: bool | None
    checks: tuple[BackupCheck, ...]

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["checks"] = [asdict(check) for check in self.checks]
        return payload


class JsonCommandRunner(Protocol):
    def run_json(self, arguments: Sequence[str]) -> object: ...


class GcloudRunner:
    def run_json(self, arguments: Sequence[str]) -> object:
        completed = subprocess.run(
            list(arguments),
            capture_output=True,
            check=True,
            text=True,
            timeout=60,
        )
        return json.loads(completed.stdout or "null")


def verify_backups(
    *,
    project_id: str,
    bucket: str,
    live: bool = False,
    max_backup_age_hours: int = 36,
    now: datetime | None = None,
    runner: JsonCommandRunner | None = None,
) -> BackupEvidence:
    checked_at = _aware_now(now)
    if not project_id.strip():
        raise ValueError("project_id is required")
    if not bucket.strip():
        raise ValueError("bucket is required")
    if max_backup_age_hours < 1 or max_backup_age_hours > 168:
        raise ValueError("max_backup_age_hours must be between 1 and 168")

    if not live:
        return BackupEvidence(
            event="backup_verification_planned",
            mode="dry_run",
            project_id=project_id,
            bucket=bucket,
            checked_at=_iso(checked_at),
            passed=None,
            checks=(
                BackupCheck(
                    name="firestore_backup_visibility",
                    status="planned",
                    detail="would list READY Firestore backups and enforce maximum age",
                ),
                BackupCheck(
                    name="storage_deletion_protection",
                    status="planned",
                    detail="would require bucket versioning or a non-zero soft-delete policy",
                ),
            ),
        )

    command_runner = runner or GcloudRunner()
    checks: list[BackupCheck] = []
    try:
        backups_payload = command_runner.run_json(
            (
                "gcloud",
                "firestore",
                "backups",
                "list",
                "--project",
                project_id,
                "--format=json",
            )
        )
        checks.append(
            _check_backups(
                backups_payload,
                checked_at=checked_at,
                max_age=timedelta(hours=max_backup_age_hours),
            )
        )
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        checks.append(
            BackupCheck(
                name="firestore_backup_visibility",
                status="failed",
                detail=type(exc).__name__,
            )
        )

    try:
        bucket_payload = command_runner.run_json(
            (
                "gcloud",
                "storage",
                "buckets",
                "describe",
                f"gs://{bucket}",
                "--project",
                project_id,
                "--format=json",
            )
        )
        checks.append(_check_bucket(bucket_payload))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        checks.append(
            BackupCheck(
                name="storage_deletion_protection",
                status="failed",
                detail=type(exc).__name__,
            )
        )

    passed = all(check.status == "passed" for check in checks)
    return BackupEvidence(
        event="backup_verification_completed" if passed else "backup_verification_failed",
        mode="live",
        project_id=project_id,
        bucket=bucket,
        checked_at=_iso(checked_at),
        passed=passed,
        checks=tuple(checks),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Oga backup protection")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-backup-age-hours", type=int, default=36)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    evidence = verify_backups(
        project_id=args.project_id,
        bucket=args.bucket,
        live=args.live,
        max_backup_age_hours=args.max_backup_age_hours,
    )
    encoded = json.dumps(evidence.as_json(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if evidence.passed is not False else 1


def _check_backups(
    payload: object,
    *,
    checked_at: datetime,
    max_age: timedelta,
) -> BackupCheck:
    if not isinstance(payload, list):
        raise ValueError("Firestore backup output must be a list")
    ready_backups = [item for item in payload if _backup_is_ready(item)]
    timestamps = [timestamp for item in ready_backups if (timestamp := _backup_time(item))]
    if not timestamps:
        return BackupCheck(
            name="firestore_backup_visibility",
            status="failed",
            detail="no READY Firestore backup with a timestamp was visible",
        )
    latest = max(timestamps)
    age = checked_at - latest
    if age < timedelta(0) or age > max_age:
        return BackupCheck(
            name="firestore_backup_visibility",
            status="failed",
            detail=f"latest READY backup age is {round(age.total_seconds() / 3600, 2)} hours",
        )
    return BackupCheck(
        name="firestore_backup_visibility",
        status="passed",
        detail=(
            f"{len(ready_backups)} READY backup(s); latest is "
            f"{round(age.total_seconds() / 3600, 2)} hours old"
        ),
    )


def _check_bucket(payload: object) -> BackupCheck:
    if not isinstance(payload, dict):
        raise ValueError("bucket description must be an object")
    versioning = _nested_bool(payload, ("versioning", "enabled"))
    retention = _first_positive_number(
        _nested(payload, ("softDeletePolicy", "retentionDurationSeconds")),
        _nested(payload, ("soft_delete_policy", "retention_duration_seconds")),
    )
    if versioning or retention > 0:
        protections = []
        if versioning:
            protections.append("versioning enabled")
        if retention > 0:
            protections.append(f"soft delete retained for {int(retention)} seconds")
        return BackupCheck(
            name="storage_deletion_protection",
            status="passed",
            detail=", ".join(protections),
        )
    return BackupCheck(
        name="storage_deletion_protection",
        status="failed",
        detail="neither object versioning nor soft delete is enabled",
    )


def _backup_is_ready(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    state = item.get("state")
    return state in {"READY", "STATE_UNSPECIFIED", None}


def _backup_time(item: object) -> datetime | None:
    if not isinstance(item, dict):
        return None
    for key in ("snapshotTime", "createTime", "snapshot_time", "create_time"):
        value = item.get(key)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                continue
    return None


def _nested(payload: dict[str, object], path: tuple[str, ...]) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _nested_bool(payload: dict[str, object], path: tuple[str, ...]) -> bool:
    return _nested(payload, path) is True


def _first_positive_number(*values: object) -> float:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float) and value > 0:
            return float(value)
        if isinstance(value, str):
            try:
                number = float(value.rstrip("s"))
            except ValueError:
                continue
            if number > 0:
                return number
    return 0


def _aware_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
