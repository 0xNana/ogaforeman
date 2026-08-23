from datetime import UTC, datetime
from decimal import Decimal
import os

import pytest

import app.infrastructure.firestore as firestore_infrastructure
from app.config.settings import RuntimeEnvironment, Settings
from app.infrastructure.firestore import (
    assert_demo_environment,
    decode_firestore_value,
    encode_firestore_value,
    create_firestore_client,
)


def test_local_client_refuses_network_without_firestore_emulator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    settings = Settings(_env_file=None, oga_env=RuntimeEnvironment.LOCAL, demo_mode=True)

    with pytest.raises(RuntimeError, match="FIRESTORE_EMULATOR_HOST"):
        create_firestore_client(settings)


def test_client_uses_emulator_and_explicit_local_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    settings = Settings(
        _env_file=None,
        oga_env=RuntimeEnvironment.TEST,
        demo_mode=True,
        firestore_emulator_host="127.0.0.1:8080",
    )
    captured: dict[str, str] = {}

    def fake_client(*, project: str, database: str) -> object:
        assert os.environ["FIRESTORE_EMULATOR_HOST"] == "127.0.0.1:8080"
        captured.update(project=project, database=database)
        return object()

    monkeypatch.setattr(firestore_infrastructure.firestore, "Client", fake_client)

    client = create_firestore_client(settings)

    assert client is not None
    assert captured == {"project": "oga-foreman-local", "database": "(default)"}
    assert "FIRESTORE_EMULATOR_HOST" not in os.environ


def test_local_client_allows_explicit_remote_project_without_emulator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    settings = Settings(
        _env_file=None,
        oga_env=RuntimeEnvironment.LOCAL,
        demo_mode=False,
        google_cloud_project="ogaforeman",
        firestore_database="(default)",
        allow_remote_firestore_in_local=True,
    )
    captured: dict[str, str] = {}

    def fake_client(*, project: str, database: str) -> object:
        captured.update(project=project, database=database)
        return object()

    monkeypatch.setattr(firestore_infrastructure.firestore, "Client", fake_client)

    client = create_firestore_client(settings)

    assert client is not None
    assert captured == {"project": "ogaforeman", "database": "(default)"}
    assert "FIRESTORE_EMULATOR_HOST" not in os.environ


def test_demo_environment_is_local_or_test_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    assert_demo_environment(
        Settings(_env_file=None, oga_env=RuntimeEnvironment.LOCAL, demo_mode=True)
    )
    assert_demo_environment(
        Settings(_env_file=None, oga_env=RuntimeEnvironment.TEST, demo_mode=True)
    )

    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    with pytest.raises(RuntimeError, match="demo mutations"):
        assert_demo_environment(
            Settings(
                _env_file=None,
                oga_env=RuntimeEnvironment.STAGING,
                demo_mode=True,
                google_cloud_project="oga-staging",
                google_cloud_region="africa-south1",
                firestore_database="(default)",
                media_bucket="oga-staging-media",
                storage_signing_service_account="oga-api@oga-staging.iam.gserviceaccount.com",
                pubsub_site_events_topic="site-events",
                pubsub_dead_letter_topic="dead-letter",
                pubsub_worker_subscription="worker",
                    gemini_model_id="gemini-test",
                    gemini_location="global",
                    conversation_proposal_signing_key="a" * 32,
                    notification_provider="google_chat",
                    google_chat_webhook_url=(
                        "https://chat.googleapis.com/v1/spaces/AAAA/messages?"
                        "key=test-key&token=test-token"
                    ),
                    public_app_base_url="https://oga-staging.web.app",
                    adk_agent_engine_id="4706041708276613120",
                    app_git_sha="b" * 40,
                    app_build_time="2026-08-23T14:05:06Z",
                    auth_issuer="https://issuer.example",
                auth_audience="oga-staging",
                cors_allowed_origins=("https://oga-staging.web.app",),
            )
        )


def test_firestore_codec_preserves_aware_time_and_decimal_precision() -> None:
    timestamp = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
    encoded = encode_firestore_value({"quantity": Decimal("10.25"), "at": timestamp})

    assert encoded == {"quantity": "10.25", "at": timestamp}
    assert decode_firestore_value(encoded) == encoded

    with pytest.raises(ValueError, match="timezone-aware"):
        encode_firestore_value(datetime(2026, 8, 7, 10, 0))

    with pytest.raises(TypeError, match="mapping keys"):
        encode_firestore_value({1: "unsafe-key"})
