"""Exercise an authenticated staging workflow with a dedicated Firebase identity."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import google.auth
from google.auth import iam, jwt
from google.auth.transport.requests import Request
import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    service_account = os.environ["FIREBASE_SERVICE_ACCOUNT"]
    api_key = os.environ["NEXT_PUBLIC_FIREBASE_API_KEY"]
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/iam"])
    credentials.refresh(Request())
    signer = iam.Signer(Request(), credentials, service_account)
    now = int(time.time())
    custom_token = jwt.encode(
        signer,
        {
            "aud": "https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit",
            "iat": now,
            "exp": now + 3600,
            "iss": service_account,
            "sub": service_account,
            "uid": "oga-staging-smoke",
            "claims": {"smoke": True},
        },
    ).decode()
    with httpx.Client(timeout=30) as identity:
        exchange = identity.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={api_key}",
            json={"token": custom_token, "returnSecureToken": True},
        )
        exchange.raise_for_status()
        id_token = exchange.json()["idToken"]

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    headers = {"Authorization": f"Bearer {id_token}"}
    checks: list[dict[str, object]] = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=30) as client:
        def call(name: str, method: str, path: str, **kwargs: object) -> httpx.Response:
            response = client.request(method, path, **kwargs)
            checks.append({"name": name, "status_code": response.status_code, "ok": response.is_success})
            response.raise_for_status()
            return response

        call("bootstrap", "POST", "/api/v1/auth/bootstrap", json={"display_name": "Staging Smoke Operator"})
        project = call(
            "create_project",
            "POST",
            "/api/v1/projects",
            headers={**headers, "Idempotency-Key": f"smoke-project-{stamp}"},
            json={"name": f"Staging workflow smoke {stamp}", "location": "Staging", "timezone": "Africa/Accra"},
        ).json()
        project_id = project["id"]
        accepted = call(
            "submit_site_update",
            "POST",
            f"/api/v1/projects/{project_id}/site-updates",
            headers={**headers, "Idempotency-Key": f"smoke-update-{stamp}"},
            json={"text": "Work started on the staging smoke area. No task should be marked complete."},
        ).json()
        run_id = accepted["agent_run_id"]
        terminal = None
        for _ in range(20):
            terminal = call("poll_agent_run", "GET", f"/api/v1/projects/{project_id}/agent-runs/{run_id}").json()
            if terminal["status"] in {"completed", "failed", "waiting_approval", "blocked"}:
                break
            time.sleep(2)
        call("read_snapshot", "GET", f"/api/v1/projects/{project_id}/snapshot")

    evidence = {
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "base_url": args.base_url,
        "project_id": project_id,
        "agent_run_id": run_id,
        "agent_run_status": terminal["status"] if terminal else None,
        "checks": checks,
        "passed": all(bool(check["ok"]) for check in checks) and terminal is not None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
