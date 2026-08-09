from unittest.mock import Mock

import pytest

from app.config.settings import Settings
from app.infrastructure.gemini import GeminiSiteInterpreter, create_gemini_client


def test_local_api_key_uses_gemini_developer_api(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client_constructor = Mock(return_value=client)
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        gemini_api_key="developer-key",
        gemini_model_id="configured-model",
    )

    result = create_gemini_client(settings)

    assert result is client
    client_constructor.assert_called_once_with(api_key="developer-key")


def test_vertex_client_is_used_without_local_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client_constructor = Mock(return_value=client)
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        google_cloud_project="oga-project",
        gemini_location="global",
        gemini_model_id="configured-model",
    )

    result = create_gemini_client(settings)

    assert result is client
    client_constructor.assert_called_once_with(
        vertexai=True,
        project="oga-project",
        location="global",
    )


def test_deployed_runtime_uses_vertex_even_when_api_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_constructor = Mock(return_value=Mock())
    monkeypatch.setattr("app.infrastructure.gemini.genai.Client", client_constructor)
    settings = Settings(
        _env_file=None,
        oga_env="staging",
        demo_mode=False,
        use_fake_model=False,
        google_cloud_project="oga-staging",
        google_cloud_region="us-central1",
        firestore_database="(default)",
        media_bucket="oga-staging-media",
        pubsub_site_events_topic="oga-site-events",
        pubsub_dead_letter_topic="oga-dead-letter",
        pubsub_worker_subscription="oga-worker",
        gemini_model_id="configured-model",
        gemini_location="global",
        gemini_api_key="developer-key",
        auth_issuer="https://securetoken.google.com/oga-staging",
        auth_audience="oga-staging",
        cors_allowed_origins=("https://oga-staging.web.app",),
    )

    create_gemini_client(settings)

    client_constructor.assert_called_once_with(
        vertexai=True,
        project="oga-staging",
        location="global",
    )


def test_live_gemini_rejects_fake_mode() -> None:
    settings = Settings(
        _env_file=None,
        use_fake_model=True,
        gemini_api_key="developer-key",
        gemini_model_id="configured-model",
    )

    with pytest.raises(RuntimeError, match="USE_FAKE_MODEL=false"):
        create_gemini_client(settings)


def test_interpreter_requires_configured_model() -> None:
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        gemini_api_key="developer-key",
    )

    with pytest.raises(RuntimeError, match="GEMINI_MODEL_ID"):
        GeminiSiteInterpreter(settings)
