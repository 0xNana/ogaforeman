from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from os import environ
from typing import Any

from google.cloud import firestore
from pydantic import BaseModel

from app.config.settings import RuntimeEnvironment, Settings, get_settings


LOCAL_FIRESTORE_PROJECT = "oga-foreman-local"
DEFAULT_FIRESTORE_DATABASE = "(default)"


def create_firestore_client(settings: Settings | None = None) -> firestore.Client:
    """Create an explicit Firestore client without retaining process-global state.

    The Google server client automatically uses ``FIRESTORE_EMULATOR_HOST`` when it
    is set. Local and test environments require that variable so a developer cannot
    accidentally write demo data to a real Firestore project.
    """

    runtime = settings or get_settings()
    emulator_host = runtime.firestore_emulator_host
    local_remote_enabled = (
        runtime.oga_env is RuntimeEnvironment.LOCAL and runtime.allow_remote_firestore_in_local
    )
    if (
        runtime.oga_env in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}
        and not emulator_host
        and not local_remote_enabled
    ):
        raise RuntimeError(
            "FIRESTORE_EMULATOR_HOST is required unless local remote Firestore is explicitly enabled"
        )

    if emulator_host:
        environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
    else:
        environ.pop("FIRESTORE_EMULATOR_HOST", None)

    project_id = runtime.google_cloud_project or LOCAL_FIRESTORE_PROJECT
    database = runtime.firestore_database or DEFAULT_FIRESTORE_DATABASE
    return firestore.Client(project=project_id, database=database)


def assert_demo_environment(settings: Settings | None = None) -> None:
    """Reject seed/reset operations outside an explicit disposable environment."""

    runtime = settings or get_settings()
    if (
        runtime.oga_env not in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}
        or not runtime.demo_mode
    ):
        raise RuntimeError("demo mutations are allowed only in local/test demo mode")
    if not runtime.firestore_emulator_host:
        raise RuntimeError("demo mutations require FIRESTORE_EMULATOR_HOST")


def encode_firestore_value(value: Any) -> Any:
    """Convert domain values to Firestore-supported values without losing UTC timestamps."""

    if isinstance(value, BaseModel):
        return encode_firestore_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return encode_firestore_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Firestore datetimes must be timezone-aware")
        return value.astimezone(UTC)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Firestore mapping keys must be strings")
        return {key: encode_firestore_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [encode_firestore_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    raise TypeError(f"unsupported Firestore value type: {type(value).__name__}")


def decode_firestore_value(value: Any) -> Any:
    """Recursively detach Firestore mappings/lists before Pydantic validation."""

    if isinstance(value, Mapping):
        return {str(key): decode_firestore_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [decode_firestore_value(item) for item in value]
    return value
