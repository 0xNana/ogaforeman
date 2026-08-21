from enum import StrEnum
from functools import lru_cache
from typing import Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PREVIEW = "preview"
    STAGING = "staging"
    PRODUCTION = "production"


# Keep the local agent factory aligned with the minimum model generation used by
# the current hackathon and deployment contract. Deployed environments must
# still provide GEMINI_MODEL_ID explicitly.
DEFAULT_GEMINI_MODEL_ID = "gemini-3.6-flash"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    oga_env: RuntimeEnvironment = RuntimeEnvironment.LOCAL
    demo_mode: bool = True
    use_fake_model: bool = True
    default_project_timezone: str = "Africa/Accra"

    google_cloud_project: str | None = None
    google_cloud_region: str | None = None
    firestore_database: str | None = None
    firestore_emulator_host: str | None = None
    allow_remote_firestore_in_local: bool = False
    media_bucket: str | None = None
    storage_signing_service_account: str | None = None

    pubsub_site_events_topic: str | None = None
    pubsub_dead_letter_topic: str | None = None
    pubsub_worker_subscription: str | None = None

    gemini_model_id: str | None = None
    gemini_fallback_model_id: str | None = None
    gemini_location: str | None = None
    gemini_api_key: SecretStr | None = None
    conversation_proposal_signing_key: SecretStr | None = None

    # A lease must cover the longest bounded local SQLite ADK queue as well as
    # a single workflow attempt.  Local SQLite serializes its one writer; a
    # five-minute default keeps the documented 100-event capacity envelope
    # claim-safe without weakening the persisted owner-token check.
    event_claim_lease_seconds: int = Field(default=300, ge=30, le=600)
    event_claim_max_attempts: int = Field(default=3, ge=1, le=10)
    agent_workflow_timeout_seconds: int = Field(default=45, ge=5, le=300)
    project_import_extraction_timeout_seconds: int = Field(default=90, ge=5, le=300)
    adk_session_backend: str = "auto"
    adk_session_database_url: str = "sqlite+aiosqlite:///./.adk/sessions.db"
    adk_agent_engine_id: str | None = None

    auth_issuer: str | None = None
    auth_audience: str | None = None
    cors_allowed_origins: tuple[str, ...] = ()

    signed_upload_ttl_seconds: int = Field(default=900, ge=60, le=3_600)
    max_upload_bytes: int = Field(default=52_428_800, gt=0, le=524_288_000)
    max_attachment_count: int = Field(default=10, ge=1, le=25)
    max_model_media_bytes: int = Field(default=18_000_000, gt=0, le=20_000_000)
    max_event_text_chars: int = Field(default=20_000, ge=256, le=1_000_000)
    rate_limit_per_user: int = Field(default=30, ge=1, le=10_000)
    rate_limit_per_project: int = Field(default=300, ge=1, le=100_000)
    approval_policy_version: str = Field(default="v1", min_length=1, max_length=64)

    @field_validator("default_project_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("default_project_timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw_origin in values:
            origin = raw_origin.strip()
            parsed = urlsplit(origin)
            is_local_http = parsed.scheme == "http" and parsed.hostname in {
                "127.0.0.1",
                "localhost",
            }
            if (
                origin == "*"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or (parsed.scheme != "https" and not is_local_http)
                or origin != f"{parsed.scheme}://{parsed.netloc}"
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS entries must be exact HTTPS origins "
                    "or loopback HTTP origins"
                )
            if origin not in normalized:
                normalized.append(origin)
        return tuple(normalized)

    @field_validator("conversation_proposal_signing_key")
    @classmethod
    def validate_conversation_proposal_signing_key(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode()) < 32:
            raise ValueError("conversation proposal signing key must be at least 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_environment_requirements(self) -> Self:
        if self.agent_workflow_timeout_seconds >= self.event_claim_lease_seconds:
            raise ValueError(
                "agent_workflow_timeout_seconds must be shorter than event_claim_lease_seconds"
            )
        if self.project_import_extraction_timeout_seconds >= self.event_claim_lease_seconds:
            raise ValueError(
                "project_import_extraction_timeout_seconds must be shorter than "
                "event_claim_lease_seconds"
            )
        if self.allow_remote_firestore_in_local:
            if self.oga_env is not RuntimeEnvironment.LOCAL:
                raise ValueError("allow_remote_firestore_in_local is valid only in local mode")
            if not self.google_cloud_project:
                raise ValueError(
                    "google_cloud_project is required when local remote Firestore is enabled"
                )
            if self.firestore_emulator_host:
                raise ValueError(
                    "firestore_emulator_host and local remote Firestore are mutually exclusive"
                )
            if self.demo_mode:
                raise ValueError("demo_mode must be false when local remote Firestore is enabled")

        if self.oga_env is RuntimeEnvironment.PRODUCTION and self.demo_mode:
            raise ValueError("demo_mode must be false in production")

        if self.oga_env is RuntimeEnvironment.PRODUCTION and self.use_fake_model:
            raise ValueError("use_fake_model must be false in production")

        if self.oga_env in {
            RuntimeEnvironment.PREVIEW,
            RuntimeEnvironment.STAGING,
            RuntimeEnvironment.PRODUCTION,
        }:
            if self.adk_session_backend == "database":
                raise ValueError(
                    "deployed environments require Vertex AI ADK sessions; "
                    "ADK_SESSION_BACKEND=database is local/test only"
                )
            if self.firestore_emulator_host:
                raise ValueError("deployed environments cannot use FIRESTORE_EMULATOR_HOST")
            required_fields = (
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
            )
            missing_fields = [
                field_name for field_name in required_fields if not getattr(self, field_name)
            ]
            if missing_fields:
                raise ValueError("Deployed environments require: " + ", ".join(missing_fields))
        if self.adk_session_backend not in {"auto", "database", "vertex_ai"}:
            raise ValueError("ADK_SESSION_BACKEND must be auto, database, or vertex_ai")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
