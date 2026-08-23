from datetime import date

import pytest

from app.domain.enums import Severity
from app.domain.notifications import (
    DeliveryDelayNotification,
    DeliveryDelayTaskReference,
)
from app.infrastructure.google_chat import GoogleChatNotificationProvider
from app.infrastructure.notification_gateway import (
    PermanentNotificationGatewayError,
    TransientNotificationGatewayError,
)


WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=test-key&token=test-token"


class Response:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body


class Session:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def post(self, url: str, *, json, timeout: float, allow_redirects: bool) -> Response:
        assert timeout == 10
        assert allow_redirects is False
        self.calls.append((url, json))
        return self.responses.pop(0)


def _payload() -> DeliveryDelayNotification:
    return DeliveryDelayNotification(
        project_id="prj_ridge123",
        project_name="Ridge Site",
        event_id="evt_delay123",
        material_request_id="mrq_cement123",
        material_name="Cement Bags",
        revised_delivery_date=date(2026, 8, 30),
        delay_reason="Supplier vehicle broke down.",
        affected_tasks=(DeliveryDelayTaskReference(task_id="tsk_slab123", title="Cast slab"),),
        risk_severity=Severity.HIGH,
        issue_id="iss_delay123",
        follow_up_task_id="tsk_followup123",
        action_taken="Opened a schedule risk and created a follow-up.",
        safe_link="https://oga.example/projects/prj_ridge123/issues/iss_delay123",
    )


def test_google_chat_uses_deterministic_provider_idempotency_and_minimal_text() -> None:
    session = Session([Response(200, {"name": "spaces/AAAA/messages/BBBB"})])
    gateway = GoogleChatNotificationProvider(WEBHOOK, session=session)

    result = gateway.send_delivery_delay(_payload(), idempotency_key="notify-key-123")

    assert result.provider_message_id == "spaces/AAAA/messages/BBBB"
    url, body = session.calls[0]
    assert "requestId=" in url
    assert "messageId=client-" in url
    assert "test-token" in url
    assert set(body) == {"text"}
    assert "Ridge Site" in body["text"]
    assert "evt_delay123" in body["text"]
    assert "Cement Bags" in body["text"]
    assert "Cast slab" in body["text"]
    assert "high" in body["text"]
    assert "Opened a schedule risk and created a follow-up." in body["text"]
    assert "authorization" not in body["text"].lower()


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (429, TransientNotificationGatewayError),
        (503, TransientNotificationGatewayError),
        (400, PermanentNotificationGatewayError),
        (403, PermanentNotificationGatewayError),
    ],
)
def test_google_chat_classifies_provider_failures(
    status_code: int, error_type: type[Exception]
) -> None:
    gateway = GoogleChatNotificationProvider(
        WEBHOOK,
        session=Session([Response(status_code, {})]),
    )

    with pytest.raises(error_type):
        gateway.send_delivery_delay(_payload(), idempotency_key="notify-key-123")


def test_google_chat_rejects_non_google_or_credential_free_destinations() -> None:
    with pytest.raises(ValueError, match="invalid"):
        GoogleChatNotificationProvider("https://example.com/hook")
    with pytest.raises(ValueError, match="invalid"):
        GoogleChatNotificationProvider("https://chat.googleapis.com/v1/spaces/AAAA/messages")


def test_google_chat_neutralizes_user_controlled_mention_markup() -> None:
    session = Session([Response(200, {"name": "spaces/AAAA/messages/BBBB"})])
    gateway = GoogleChatNotificationProvider(WEBHOOK, session=session)
    payload = _payload().model_copy(
        update={"delay_reason": "Vehicle failed.\n<users/all> investigate."}
    )

    gateway.send_delivery_delay(payload, idempotency_key="notify-key-mentions")

    text = session.calls[0][1]["text"]
    assert "<users/all>" not in text
    assert "[users/all]" in text


def test_google_chat_rejects_malformed_success_identity() -> None:
    gateway = GoogleChatNotificationProvider(
        WEBHOOK,
        session=Session([Response(200, {"name": "not-a-message-resource"})]),
    )

    with pytest.raises(PermanentNotificationGatewayError):
        gateway.send_delivery_delay(_payload(), idempotency_key="notify-key-invalid-id")
