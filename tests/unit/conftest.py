import pytest


@pytest.fixture(autouse=True)
def clean_unit_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure unit tests do not inherit environment variables that break Pydantic Settings."""
    keys_to_remove = [
        "FIRESTORE_EMULATOR_HOST",
        "STORAGE_EMULATOR_HOST",
        "OGA_ENV",
        "DEMO_MODE",
        "USE_FAKE_MODEL",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_REGION",
        "FIRESTORE_DATABASE",
        "MEDIA_BUCKET",
        "STORAGE_SIGNING_SERVICE_ACCOUNT",
        "PUBSUB_SITE_EVENTS_TOPIC",
        "PUBSUB_DEAD_LETTER_TOPIC",
        "PUBSUB_WORKER_SUBSCRIPTION",
        "GEMINI_MODEL_ID",
        "GEMINI_LOCATION",
        "GEMINI_API_KEY",
        "CONVERSATION_PROPOSAL_SIGNING_KEY",
        "AUTH_ISSUER",
        "AUTH_AUDIENCE",
        "CORS_ALLOWED_ORIGINS",
    ]

    for k in keys_to_remove:
        monkeypatch.delenv(k, raising=False)
