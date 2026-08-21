"""Run the read-only staging observability smoke checks.

The command intentionally exercises only liveness/readiness endpoints. It never
publishes an event or changes project state; alert smoke is a separate, manually
approved staging exercise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    name: str
    path: str
    status_code: int | None
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class SmokeEvidence:
    checked_at: str
    base_url: str
    request_id: str
    correlation_id: str
    trace_id: str
    checks: tuple[SmokeCheck, ...]
    passed: bool
    git_revision: str | None

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["checks"] = [asdict(check) for check in self.checks]
        return payload


def run_smoke(
    base_url: str,
    *,
    timeout_seconds: float = 10.0,
    bearer_token: str | None = None,
    client: httpx.Client | None = None,
) -> SmokeEvidence:
    normalized = _validate_base_url(base_url)
    request_id = f"req_smoke_{token_hex(8)}"
    correlation_id = f"cor_smoke_{token_hex(8)}"
    trace_id = f"trc_smoke_{token_hex(16)}"
    headers = {
        "X-Request-ID": request_id,
        "X-Correlation-ID": correlation_id,
        "X-Trace-ID": trace_id,
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    own_client = client is None
    http_client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
    checks: list[SmokeCheck] = []
    try:
        for name, path, expected in (
            ("liveness", "/health/live", {200}),
            ("readiness", "/health/ready", {200, 503}),
            ("metrics", "/metrics", {200}),
        ):
            try:
                response = http_client.get(f"{normalized}{path}", headers=headers)
                body = response.text[:256].replace("\n", " ")
                ok = response.status_code in expected
                checks.append(
                    SmokeCheck(
                        name=name,
                        path=path,
                        status_code=response.status_code,
                        ok=ok,
                        detail=body if ok else f"unexpected status {response.status_code}",
                    )
                )
            except httpx.HTTPError as exc:
                checks.append(
                    SmokeCheck(
                        name=name,
                        path=path,
                        status_code=None,
                        ok=False,
                        detail=type(exc).__name__,
                    )
                )
    finally:
        if own_client:
            http_client.close()

    return SmokeEvidence(
        checked_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        base_url=normalized,
        request_id=request_id,
        correlation_id=correlation_id,
        trace_id=trace_id,
        checks=tuple(checks),
        passed=all(check.ok for check in checks),
        git_revision=_git_revision(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Oga observability endpoints")
    parser.add_argument(
        "--base-url",
        default=os.getenv("OGA_STAGING_API_URL", "http://127.0.0.1:8000"),
        help="API base URL (defaults to OGA_STAGING_API_URL or local port 8000)",
    )
    parser.add_argument(
        "--token-env",
        default="OGA_STAGING_TOKEN",
        help="environment variable containing an optional bearer token",
    )
    parser.add_argument("--output", type=Path, help="write JSON evidence to this path")
    args = parser.parse_args()

    evidence = run_smoke(args.base_url, bearer_token=os.getenv(args.token_env))
    encoded = json.dumps(evidence.as_json(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if evidence.passed else 1


def _validate_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be an absolute http(s) URL")
    return candidate


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision[:64] or None


if __name__ == "__main__":
    raise SystemExit(main())
