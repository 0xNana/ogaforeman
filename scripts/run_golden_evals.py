"""Run the eight-check Golden operational release evaluation."""

from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
from pathlib import Path

from app.agents.interpreter import FakeSiteInterpreter, SiteInterpreter
from app.config.settings import NotificationProviderName, RuntimeEnvironment, Settings
from app.evals.golden import (
    GOLDEN_UPDATE_TEXT,
    golden_fixture_fact_set,
    run_golden_evaluation,
)
from app.infrastructure.gemini import GeminiSiteInterpreter
from app.infrastructure.google_chat import GoogleChatNotificationProvider
from app.domain.notifications import DeliveryDelayNotification, NotificationDeliveryResult
from app.infrastructure.notification_gateway import NotificationProvider


class _FixtureEvalNotificationGateway:
    """Deterministic external boundary used only by the fixture evaluation."""

    provider = "google_chat"
    destination_key = "f" * 24
    is_external = True

    def send_delivery_delay(
        self,
        _payload: DeliveryDelayNotification,
        *,
        idempotency_key: str,
    ) -> NotificationDeliveryResult:
        message_id = sha256(idempotency_key.encode()).hexdigest()[:20]
        return NotificationDeliveryResult(
            provider=self.provider,
            provider_message_id=f"spaces/fixture/messages/{message_id}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapter",
        choices=("fixture", "gemini"),
        default="fixture",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "vertex"),
        default="auto",
        help="Gemini backend; vertex forces the billed Google Cloud route",
    )
    parser.add_argument(
        "--output",
        default="artifacts/evals/golden-latest.json",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    interpreter: SiteInterpreter
    model_id: str | None
    backend: str
    cloud_project: str | None = None
    cloud_location: str | None = None
    notification_gateway: NotificationProvider
    if args.adapter == "fixture":
        interpreter = FakeSiteInterpreter(responses={GOLDEN_UPDATE_TEXT: golden_fixture_fact_set()})
        model_id = None
        backend = "fixture"
        notification_gateway = _FixtureEvalNotificationGateway()
    else:
        if settings.notification_provider is not NotificationProviderName.GOOGLE_CHAT:
            raise RuntimeError("Live Golden evaluation requires NOTIFICATION_PROVIDER=google_chat")
        interpreter = GeminiSiteInterpreter(
            settings,
            prefer_vertex=args.backend == "vertex",
        )
        model_id = settings.gemini_model_id
        cloud_project = settings.google_cloud_project
        cloud_location = settings.gemini_location
        uses_developer_api = (
            args.backend == "auto"
            and settings.oga_env in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}
            and settings.gemini_api_key is not None
        )
        backend = "developer_api" if uses_developer_api else "vertex"
        if settings.google_chat_webhook_url is None:
            raise RuntimeError("GOOGLE_CHAT_WEBHOOK_URL is required for live Golden evaluation")
        notification_gateway = GoogleChatNotificationProvider(
            settings.google_chat_webhook_url.get_secret_value()
        )
    report = await run_golden_evaluation(
        interpreter,
        adapter=args.adapter,
        model_id=model_id,
        backend=backend,
        cloud_project=cloud_project,
        cloud_location=cloud_location,
        settings=settings,
        notification_gateway=notification_gateway,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    passed_checks = sum(check.passed for check in report.checks)
    print(
        f"Golden eval adapter={report.adapter} backend={report.backend} "
        f"passed={report.passed} checks={passed_checks}/{len(report.checks)} "
        f"source_tree_dirty={report.source_tree_dirty} "
        f"artifact={output}"
    )
    return 0 if report.passed else 1


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
