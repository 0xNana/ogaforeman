from app.config.settings import Settings
from google.api_core.exceptions import NotFound
from app.observability.probes import (
    configuration_probe,
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
    assert storage_probe(
        FakeStorageClient(failure=NotFound("missing")), "oga-media"
    )() == (
        False,
        "bucket_not_found",
    )
    assert storage_probe(
        FakeStorageClient(failure=RuntimeError("secret")), "oga-media"
    )() == (False, "RuntimeError")


def test_configuration_probe_reports_local_and_deployed_contracts() -> None:
    local = Settings(_env_file=None)
    assert configuration_probe(local)() == (True, "local")

    deployed = Settings(
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
        gemini_model_id="gemini-model",
        gemini_location="global",
        auth_issuer="https://securetoken.google.com/oga-staging",
        auth_audience="oga-staging",
    )
    assert configuration_probe(deployed)() == (True, "staging")
