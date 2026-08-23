"""Send one explicitly confirmed Google Chat notification and record bounded evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import NotificationProviderName, Settings
from app.domain.enums import Severity
from app.domain.notifications import (
    DeliveryDelayNotification,
    DeliveryDelayTaskReference,
)
from app.infrastructure.google_chat import GoogleChatNotificationProvider


CONFIRMATION = "send-google-chat-live-check"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-send",
        choices=(CONFIRMATION,),
        required=True,
        help="Required acknowledgement that this command sends to the real destination.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/operations/google-chat-live-current.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    if settings.notification_provider is not NotificationProviderName.GOOGLE_CHAT:
        raise RuntimeError("Live check requires NOTIFICATION_PROVIDER=google_chat")
    if settings.google_chat_webhook_url is None:
        raise RuntimeError("GOOGLE_CHAT_WEBHOOK_URL is required for the live check")

    git_sha = _git("rev-parse", "HEAD")
    source_tree_dirty = bool(_git("status", "--porcelain"))
    if source_tree_dirty:
        raise RuntimeError("Google Chat live evidence requires a clean committed worktree")
    sent_at = datetime.now(UTC)
    check_id = sha256(
        f"{git_sha}\x00{sent_at.date().isoformat()}\x00google-chat-live-check".encode()
    ).hexdigest()[:24]
    payload = DeliveryDelayNotification(
        project_id="prj_livecheck123",
        project_name="OG Foreman live integration check",
        event_id="evt_livecheck123",
        material_request_id="mrq_livecheck123",
        material_name="Cement",
        revised_delivery_date=sent_at.date(),
        delay_reason="Explicitly gated provider connectivity check.",
        affected_tasks=(
            DeliveryDelayTaskReference(
                task_id="tsk_livecheck123",
                title="Provider connectivity check",
            ),
        ),
        risk_severity=Severity.INFO,
        issue_id="iss_livecheck123",
        follow_up_task_id="tsk_followup123",
        action_taken="Verified the configured external notification destination.",
    )
    result = GoogleChatNotificationProvider(
        settings.google_chat_webhook_url.get_secret_value()
    ).send_delivery_delay(
        payload,
        idempotency_key=f"google-chat-live-check:{check_id}",
    )
    evidence = {
        "passed": True,
        "provider": result.provider,
        "provider_message_id": result.provider_message_id,
        "check_id": check_id,
        "git_commit": git_sha,
        "source_tree_dirty": source_tree_dirty,
        "sent_at": sent_at.isoformat(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(
        f"Google Chat live check passed provider={result.provider} "
        f"source_tree_dirty={source_tree_dirty} artifact={output}"
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    main()
