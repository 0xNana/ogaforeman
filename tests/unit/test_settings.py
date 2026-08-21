from collections.abc import Mapping
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError
from pydantic import SecretStr

from app.config.settings import RuntimeEnvironment, Settings


PRODUCTION_CONFIG: Mapping[str, object] = {
    "oga_env": "production",
    "demo_mode": False,
    "use_fake_model": False,
    "google_cloud_project": "oga-production",
    "google_cloud_region": "europe-west1",
    "firestore_database": "(default)",
    "media_bucket": "oga-production-media",
    "storage_signing_service_account": "oga-api@oga-production.iam.gserviceaccount.com",
    "pubsub_site_events_topic": "oga-site-events",
    "pubsub_dead_letter_topic": "oga-site-events-dead-letter",
    "pubsub_worker_subscription": "oga-worker",
    "gemini_model_id": "gemini-production-model",
    "gemini_location": "global",
    "conversation_proposal_signing_key": "a" * 32,
    "adk_agent_engine_id": "agent-engine-production",
    "auth_issuer": "https://securetoken.google.com/oga-production",
    "auth_audience": "oga-production",
    "cors_allowed_origins": ["https://oga-production.web.app"],
}


def test_local_defaults_are_explicit_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.oga_env is RuntimeEnvironment.LOCAL
    assert settings.demo_mode is True
    assert settings.use_fake_model is True
    assert settings.default_project_timezone == "Africa/Accra"
    assert settings.google_cloud_project is None
    assert settings.allow_remote_firestore_in_local is False
    assert settings.firestore_emulator_host is None
    assert settings.cors_allowed_origins == ()
    assert settings.agent_workflow_timeout_seconds < settings.event_claim_lease_seconds
    assert settings.project_import_extraction_timeout_seconds == 90


def test_local_remote_firestore_requires_explicit_project_and_no_emulator() -> None:
    settings = Settings(
        _env_file=None,
        demo_mode=False,
        google_cloud_project="ogaforeman",
        firestore_database="(default)",
        allow_remote_firestore_in_local=True,
    )

    assert settings.allow_remote_firestore_in_local is True
    assert settings.google_cloud_project == "ogaforeman"

    with pytest.raises(ValidationError, match="google_cloud_project"):
        Settings(_env_file=None, allow_remote_firestore_in_local=True)

    with pytest.raises(ValidationError, match="mutually exclusive"):
        Settings(
            _env_file=None,
            demo_mode=False,
            google_cloud_project="ogaforeman",
            allow_remote_firestore_in_local=True,
            firestore_emulator_host="127.0.0.1:8086",
        )


def test_complete_production_configuration_is_valid() -> None:
    settings = Settings(_env_file=None, firestore_emulator_host=None, **PRODUCTION_CONFIG)

    assert settings.oga_env is RuntimeEnvironment.PRODUCTION
    assert settings.demo_mode is False
    assert settings.use_fake_model is False
    assert settings.google_cloud_project == "oga-production"
    assert settings.cors_allowed_origins == ("https://oga-production.web.app",)


def test_deployed_environment_rejects_local_adk_database_sessions() -> None:
    config = dict(PRODUCTION_CONFIG)
    config["adk_session_backend"] = "database"

    with pytest.raises(ValidationError, match="Vertex AI ADK sessions"):
        Settings(_env_file=None, firestore_emulator_host=None, **config)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://oga.example/path",
        "https://oga.example?query=yes",
        "http://oga.example",
    ],
)
def test_cors_origins_reject_wildcards_paths_and_insecure_remote_hosts(origin: str) -> None:
    config = dict(PRODUCTION_CONFIG)
    config["cors_allowed_origins"] = [origin]

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(_env_file=None, **config)


def test_settings_load_cors_origins_from_json_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["https://ogaforeman.example","http://127.0.0.1:3100"]',
    )

    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == (
        "https://ogaforeman.example",
        "http://127.0.0.1:3100",
    )


def test_production_rejects_missing_cloud_model_and_auth_configuration() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            oga_env="production",
            demo_mode=False,
            use_fake_model=False,
            firestore_emulator_host=None,
        )

    message = str(exc_info.value)
    for field_name in (
        "google_cloud_project",
        "google_cloud_region",
        "firestore_database",
        "media_bucket",
        "storage_signing_service_account",
        "pubsub_site_events_topic",
        "pubsub_dead_letter_topic",
        "pubsub_worker_subscription",
        "gemini_model_id",
        "gemini_location",
        "conversation_proposal_signing_key",
        "adk_agent_engine_id",
        "auth_issuer",
        "auth_audience",
        "cors_allowed_origins",
    ):
        assert field_name in message


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("signed_upload_ttl_seconds", 59),
        ("signed_upload_ttl_seconds", 3601),
        ("max_upload_bytes", 0),
        ("max_model_media_bytes", 20_000_001),
        ("max_event_text_chars", 255),
        ("rate_limit_per_user", 0),
        ("rate_limit_per_project", 0),
    ],
)
def test_limits_reject_unsafe_values(field_name: str, invalid_value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field_name: invalid_value})


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("demo_mode", True),
        ("use_fake_model", True),
    ],
)
def test_production_rejects_demo_or_fake_model_mode(
    field_name: str,
    invalid_value: bool,
) -> None:
    config = dict(PRODUCTION_CONFIG)
    config[field_name] = invalid_value
    config["firestore_emulator_host"] = None

    with pytest.raises(ValidationError, match=field_name):
        Settings(_env_file=None, **config)


def test_timezone_must_be_a_real_iana_zone() -> None:
    with pytest.raises(ValidationError, match="IANA timezone"):
        Settings(_env_file=None, default_project_timezone="Accra/Invalid")


def test_workflow_timeout_must_fit_inside_event_claim_lease() -> None:
    with pytest.raises(ValidationError, match="shorter than event_claim_lease_seconds"):
        Settings(
            _env_file=None,
            event_claim_lease_seconds=60,
            agent_workflow_timeout_seconds=60,
        )


def test_settings_load_documented_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OGA_ENV", "test")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("USE_FAKE_MODEL", "true")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1048576")
    monkeypatch.setenv("MAX_MODEL_MEDIA_BYTES", "1000000")

    settings = Settings(_env_file=None)

    assert settings.oga_env is RuntimeEnvironment.TEST
    assert settings.demo_mode is False
    assert settings.use_fake_model is True
    assert settings.max_upload_bytes == 1_048_576
    assert settings.max_model_media_bytes == 1_000_000


def test_gemini_api_key_is_loaded_as_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "local-development-key")

    settings = Settings(_env_file=None)

    assert isinstance(settings.gemini_api_key, SecretStr)
    assert settings.gemini_api_key.get_secret_value() == "local-development-key"
    assert "local-development-key" not in repr(settings)


def test_api_entrypoint_fails_fast_for_incomplete_production_config(tmp_path: Path) -> None:
    environment = os.environ.copy()
    repository_root = Path(__file__).parents[2]
    for field_name in PRODUCTION_CONFIG:
        environment.pop(field_name.upper(), None)
    environment.update(
        {
            "OGA_ENV": "production",
            "DEMO_MODE": "false",
            "USE_FAKE_MODEL": "false",
            "ALLOW_REMOTE_FIRESTORE_IN_LOCAL": "false",
        }
    )
    environment.pop("FIRESTORE_EMULATOR_HOST", None)
    environment["PYTHONPATH"] = str(repository_root)

    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "google_cloud_project" in result.stderr
