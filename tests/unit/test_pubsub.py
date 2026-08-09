from __future__ import annotations

from collections.abc import Mapping

from app.config.settings import RuntimeEnvironment, Settings
from app.infrastructure.pubsub import PubSubClient


class StubResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {"messageIds": ["msg_live123"]}


class StubSession:
    def __init__(self) -> None:
        self.url: str | None = None
        self.payload: Mapping[str, object] | None = None

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
        timeout: float,
    ) -> StubResponse:
        assert timeout == 10
        self.url = url
        self.payload = json
        return StubResponse()


def test_demo_publisher_is_explicit_and_deterministic() -> None:
    client = PubSubClient(Settings(_env_file=None, demo_mode=True))

    first = client.publish(None, b"same event")
    second = client.publish(None, b"same event")

    assert first == second
    assert first.startswith("msg_demo_")


def test_live_publisher_uses_configured_project_topic_and_attributes() -> None:
    settings = Settings(
        oga_env=RuntimeEnvironment.LOCAL,
        demo_mode=False,
        use_fake_model=True,
        google_cloud_project="oga-staging",
        allow_remote_firestore_in_local=True,
        pubsub_site_events_topic="oga-site-events",
    )
    session = StubSession()
    client = PubSubClient(settings, session=session)

    message_id = client.publish(None, b"event", attributes={"event_type": "TASK_COMPLETED"})

    assert message_id == "msg_live123"
    assert session.url == (
        "https://pubsub.googleapis.com/v1/projects/oga-staging/topics/oga-site-events:publish"
    )
    assert session.payload is not None
