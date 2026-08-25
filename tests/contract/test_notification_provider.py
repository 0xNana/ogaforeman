from datetime import date

from app.domain.enums import Severity
from app.domain.notifications import (
    DeliveryDelayNotification,
    DeliveryDelayTaskReference,
)
from app.infrastructure.disabled_notification import DisabledNotificationProvider
from app.infrastructure.google_chat import GoogleChatNotificationProvider
from app.infrastructure.logging_notification import LoggingNotificationProvider
from app.infrastructure.notification_gateway import (
    NotificationProvider,
    RealExternalNotificationProvider,
)


WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=test-key&token=test-token"


class Response:
    status_code = 200

    def json(self) -> object:
        return {"name": "spaces/AAAA/messages/BBBB"}


class Session:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, str],
        timeout: float,
        allow_redirects: bool,
    ) -> Response:
        assert set(json) == {"text"}
        assert timeout == 10
        assert allow_redirects is False
        self.urls.append(url)
        return Response()


def _payload() -> DeliveryDelayNotification:
    return DeliveryDelayNotification(
        project_id="prj_contract123",
        project_name="Contract Project",
        event_id="evt_contract123",
        material_request_id="mrq_contract123",
        material_name="Cement Bags",
        revised_delivery_date=date(2026, 8, 30),
        delay_reason="Vehicle breakdown.",
        affected_tasks=(
            DeliveryDelayTaskReference(
                task_id="tsk_plastering123",
                title="First-floor plastering",
            ),
        ),
        risk_severity=Severity.HIGH,
        issue_id="iss_contract123",
        follow_up_task_id="tsk_followup123",
        action_taken="Opened a risk and created a delivery follow-up.",
        safe_link="https://oga.example/projects/prj_contract123/issues/iss_contract123",
    )


def test_logging_provider_satisfies_contract_without_claiming_external_delivery() -> None:
    provider = LoggingNotificationProvider()
    assert isinstance(provider, NotificationProvider)
    assert not isinstance(provider, RealExternalNotificationProvider)

    first = provider.send_delivery_delay(_payload(), idempotency_key="contract-key")
    replay = provider.send_delivery_delay(_payload(), idempotency_key="contract-key")

    assert provider.is_external is False
    assert first == replay
    assert first.provider == "logging"


def test_disabled_provider_satisfies_contract_but_cannot_send() -> None:
    provider = DisabledNotificationProvider()

    assert isinstance(provider, NotificationProvider)
    assert not isinstance(provider, RealExternalNotificationProvider)
    assert provider.is_enabled is False
    assert provider.is_external is False

    try:
        provider.send_delivery_delay(_payload(), idempotency_key="contract-key")
    except RuntimeError as exc:
        assert str(exc) == "disabled notification provider cannot send"
    else:
        raise AssertionError("disabled provider unexpectedly represented a send")


def test_google_chat_provider_satisfies_real_external_contract_idempotently() -> None:
    session = Session()
    provider = GoogleChatNotificationProvider(WEBHOOK, session=session)
    assert isinstance(provider, NotificationProvider)
    assert isinstance(provider, RealExternalNotificationProvider)

    first = provider.send_delivery_delay(_payload(), idempotency_key="contract-key")
    replay = provider.send_delivery_delay(_payload(), idempotency_key="contract-key")

    assert provider.is_external is True
    assert first == replay
    assert first.provider == "google_chat"
    assert session.urls[0] == session.urls[1]
