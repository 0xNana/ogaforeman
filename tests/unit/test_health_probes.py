from app.config.settings import NotificationProviderName, Settings
from google.api_core.exceptions import NotFound
from app.observability.probes import (
    configuration_probe,
    external_notification_configuration_probe,
    firestore_probe,
    storage_probe,
)


class FakeQuery:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure

    def limit(self, _limit: int) -> "FakeQuery":
        return self

    def stream(self, *, timeout: float):
        assert timeout == 5.0
        if self.failure:
            raise self.failure
        return iter(())


class FakeFirestoreClient:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure

    def collection(self, name: str) -> FakeQuery:
        assert name == "projects"
        return FakeQuery(failure=self.failure)


class FakeStorageClient:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure

    def list_blobs(self, name: str, *, max_results: int, timeout: float):
        assert name == "oga-media"
        assert max_results == 1
        assert timeout == 5.0
        if self.failure:
            raise self.failure
        return iter(())


def test_firestore_probe_reports_bounded_dependency_state() -> None:
    assert firestore_probe(FakeFirestoreClient())() == (True, "reachable")
    assert firestore_probe(FakeFirestoreClient(failure=RuntimeError("secret")))() == (
        False,
        "RuntimeError",
    )


def test_storage_probe_checks_object_data_plane_without_leaking_details() -> None:
    assert storage_probe(FakeStorageClient(), "oga-media")() == (True, "reachable")
    assert storage_probe(FakeStorageClient(failure=NotFound("missing")), "oga-media")() == (
        False,
        "bucket_not_found",
    )
    assert storage_probe(FakeStorageClient(failure=RuntimeError("secret")), "oga-media")() == (
        False,
        "RuntimeError",
    )


def test_configuration_probe_reports_local_and_deployed_contracts() -> None:
    local = Settings(_env_file=None)
    assert configuration_probe(local)() == (True, "local")
    assert external_notification_configuration_probe(local)() == (
        True,
        "logging_development_only",
    )

    deployed = Settings(
        _env_file=None,
        oga_env="staging",
        demo_mode=False,
        use_fake_model=False,
        google_cloud_project="oga-staging",
        google_cloud_region="us-central1",
        firestore_database="(default)",
        media_bucket="oga-staging-media",
        storage_signing_service_account="oga-api@oga-staging.iam.gserviceaccount.com",
        pubsub_site_events_topic="oga-site-events",
        pubsub_dead_letter_topic="oga-dead-letter",
        pubsub_worker_subscription="oga-worker",
        gemini_model_id="gemini-model",
        gemini_location="global",
        conversation_proposal_signing_key="a" * 32,
        notification_provider="google_chat",
        google_chat_webhook_url=(
            "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=test-key&token=test-token"
        ),
        public_app_base_url="https://oga-staging.web.app",
        adk_agent_engine_id="agent-engine-staging",
        auth_issuer="https://securetoken.google.com/oga-staging",
        auth_audience="oga-staging",
        cors_allowed_origins=("https://oga-staging.web.app",),
        app_git_sha="b134039daa3bc1528f9e869678dd6d59a4f9d1f9",
        app_build_time="2026-08-23T14:05:06Z",
        app_source_tree_dirty=False,
    )
    assert configuration_probe(deployed)() == (True, "staging")
    assert external_notification_configuration_probe(deployed)() == (
        True,
        "google_chat_configured",
    )

    disabled = deployed.model_copy(
        update={
            "notification_provider": NotificationProviderName.DISABLED,
            "google_chat_webhook_url": None,
        }
    )
    assert external_notification_configuration_probe(disabled)() == (
        True,
        "external_notifications_disabled",
    )
