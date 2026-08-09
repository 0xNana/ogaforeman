from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .enums import Severity
from .models import CanonicalId, DomainModel, IdempotencyKey


EVENT_SCHEMA_VERSION = "1.0"
MAX_EVENT_PAYLOAD_BYTES = 1_100_000
MAX_EVENT_METADATA_BYTES = 65_536
MAX_EVENT_NESTING_DEPTH = 16
MAX_EVENT_PAYLOAD_VALUES = 20_000
MAX_EVENT_METADATA_VALUES = 512
_CANONICAL_ID_ADAPTER = TypeAdapter(CanonicalId)


class _FrozenDict(dict[str, Any]):
    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("event mappings are immutable")

    __setitem__ = __delitem__ = __ior__ = clear = pop = popitem = setdefault = update = (  # type: ignore[assignment]
        _immutable
    )


class _FrozenList(list[Any]):
    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("event sequences are immutable")

    __setitem__ = __delitem__ = __iadd__ = __imul__ = _immutable  # type: ignore[assignment]
    append = extend = insert = pop = remove = reverse = sort = _immutable


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


class EventType(StrEnum):
    SITE_UPDATE_RECEIVED = "SITE_UPDATE_RECEIVED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_BLOCKED = "TASK_BLOCKED"
    MATERIAL_LOW = "MATERIAL_LOW"
    MATERIAL_REQUESTED = "MATERIAL_REQUESTED"
    DELIVERY_DELAYED = "DELIVERY_DELAYED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    TASK_OVERDUE = "TASK_OVERDUE"
    DAILY_BRIEF_REQUESTED = "DAILY_BRIEF_REQUESTED"


EVENT_REGISTRY: Mapping[EventType, tuple[str, ...]] = MappingProxyType(
    {
        EventType.SITE_UPDATE_RECEIVED: ("site_update_id",),
        EventType.TASK_COMPLETED: ("task_id", "evidence_refs"),
        EventType.TASK_BLOCKED: ("description", "severity", "task_refs"),
        EventType.MATERIAL_LOW: ("quantity", "unit"),
        EventType.MATERIAL_REQUESTED: ("request_id",),
        EventType.DELIVERY_DELAYED: ("request_id", "new_date", "reason"),
        EventType.APPROVAL_GRANTED: ("approval_id", "resolver", "notes"),
        EventType.APPROVAL_REJECTED: ("approval_id", "resolver", "notes"),
        EventType.TASK_OVERDUE: ("task_id", "expected_date"),
        EventType.DAILY_BRIEF_REQUESTED: ("report_date", "timezone"),
    }
)
SUPPORTED_EVENT_TYPES = frozenset(EVENT_REGISTRY)


class EventSource(StrEnum):
    WEB = "web"
    SCHEDULER = "scheduler"
    SUPPLIER = "supplier"
    INTEGRATION = "integration"
    SYSTEM = "system"


class EventActorType(StrEnum):
    USER = "user"
    WORKLOAD = "workload"
    SYSTEM = "system"
    INTEGRATION = "integration"


class EventActor(DomainModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    type: EventActorType
    id: CanonicalId


class ProjectEvent(DomainModel):
    """Versioned, immutable event envelope shared by all workflow inputs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    schema_version: str = Field(default=EVENT_SCHEMA_VERSION, min_length=1, max_length=16)
    event_id: CanonicalId
    project_id: CanonicalId
    event_type: EventType
    source: EventSource
    occurred_at: AwareDatetime
    received_at: AwareDatetime
    actor: EventActor
    idempotency_key: IdempotencyKey
    correlation_id: CanonicalId
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    _REQUIRED_PAYLOAD: ClassVar[Mapping[EventType, tuple[str, ...]]] = EVENT_REGISTRY

    @field_validator("payload", mode="after")
    @classmethod
    def validate_and_freeze_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_container(
            value,
            field_name="payload",
            max_bytes=MAX_EVENT_PAYLOAD_BYTES,
            max_values=MAX_EVENT_PAYLOAD_VALUES,
        )
        return _freeze(value)

    @field_validator("metadata", mode="after")
    @classmethod
    def validate_and_freeze_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json_container(
            value,
            field_name="metadata",
            max_bytes=MAX_EVENT_METADATA_BYTES,
            max_values=MAX_EVENT_METADATA_VALUES,
        )
        return _freeze(value)

    @model_validator(mode="after")
    def validate_envelope(self) -> ProjectEvent:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        if self.received_at < self.occurred_at:
            raise ValueError("received_at cannot be before occurred_at")

        required = self._REQUIRED_PAYLOAD[self.event_type]
        missing = [key for key in required if key not in self.payload]
        if missing:
            raise ValueError(f"payload missing required field(s): {', '.join(missing)}")
        if self.event_type is EventType.SITE_UPDATE_RECEIVED and not any(
            self.payload.get(key) for key in ("text", "transcript", "attachment_ids")
        ):
            raise ValueError(
                "SITE_UPDATE_RECEIVED payload requires text, transcript, or attachments"
            )
        self._validate_typed_payload()
        return self

    def _validate_typed_payload(self) -> None:
        id_fields: dict[EventType, tuple[str, ...]] = {
            EventType.SITE_UPDATE_RECEIVED: ("site_update_id",),
            EventType.TASK_COMPLETED: ("task_id",),
            EventType.MATERIAL_REQUESTED: ("request_id",),
            EventType.DELIVERY_DELAYED: ("request_id",),
            EventType.APPROVAL_GRANTED: ("approval_id", "resolver"),
            EventType.APPROVAL_REJECTED: ("approval_id", "resolver"),
            EventType.TASK_OVERDUE: ("task_id",),
        }
        for field_name in id_fields.get(self.event_type, ()):
            _validate_canonical_id(self.payload[field_name], field_name=field_name)

        if self.event_type is EventType.SITE_UPDATE_RECEIVED:
            _validate_optional_text(self.payload, "text", max_length=1_000_000)
            _validate_optional_text(self.payload, "transcript", max_length=1_000_000)
            _validate_reference_list(self.payload.get("attachment_ids", []), "attachment_ids", 32)
        if self.event_type is EventType.TASK_COMPLETED:
            _validate_text_list(self.payload["evidence_refs"], "evidence_refs", 100)
            if "completion_percent" in self.payload:
                _validate_percentage(self.payload["completion_percent"])
        if self.event_type is EventType.TASK_BLOCKED:
            _validate_required_text(self.payload["description"], "description", 10_000)
            try:
                Severity(self.payload["severity"])
            except (TypeError, ValueError) as exc:
                raise ValueError("severity is invalid") from exc
            _validate_reference_list(self.payload["task_refs"], "task_refs", 100)
        if self.event_type is EventType.MATERIAL_LOW:
            if not self.payload.get("material_ref") and not self.payload.get("material_name"):
                raise ValueError("MATERIAL_LOW requires material_ref or material_name")
            if self.payload.get("material_ref"):
                _validate_canonical_id(self.payload["material_ref"], field_name="material_ref")
            if self.payload.get("material_name"):
                _validate_required_text(self.payload["material_name"], "material_name", 300)
            quantity = self.payload["quantity"]
            if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
                raise ValueError("quantity must be numeric")
            if not math.isfinite(float(quantity)) or quantity < 0:
                raise ValueError("quantity cannot be negative")
            _validate_required_text(self.payload["unit"], "unit", 100)
        if self.event_type is EventType.DELIVERY_DELAYED:
            _validate_iso_date(self.payload["new_date"], "new_date")
            _validate_required_text(self.payload["reason"], "reason", 5_000)
        if self.event_type in {EventType.APPROVAL_GRANTED, EventType.APPROVAL_REJECTED}:
            _validate_optional_text(self.payload, "notes", max_length=5_000)
        if self.event_type is EventType.TASK_OVERDUE:
            _validate_iso_date(self.payload["expected_date"], "expected_date")
        if self.event_type is EventType.DAILY_BRIEF_REQUESTED:
            _validate_iso_date(self.payload["report_date"], "report_date")
            timezone = self.payload["timezone"]
            if not isinstance(timezone, str):
                raise ValueError("timezone must be a string")
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("timezone must be a valid IANA timezone") from exc

    @property
    def fingerprint(self) -> str:
        canonical: Mapping[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "project_id": self.project_id,
            "event_type": self.event_type.value,
            "source": self.source.value,
            "occurred_at": _canonical_datetime(self.occurred_at),
            "received_at": _canonical_datetime(self.received_at),
            "actor": {"type": self.actor.type.value, "id": self.actor.id},
            "idempotency_key": self.idempotency_key,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_percentage(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("completion_percent must be numeric")
    if not math.isfinite(float(value)) or not 0 <= value <= 100:
        raise ValueError("completion_percent must be between 0 and 100")


def _validate_canonical_id(value: Any, *, field_name: str) -> None:
    try:
        _CANONICAL_ID_ADAPTER.validate_python(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical ID") from exc


def _validate_required_text(value: Any, field_name: str, max_length: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{field_name} must contain between 1 and {max_length} characters")


def _validate_optional_text(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    max_length: int,
) -> None:
    value = payload.get(field_name)
    if value is not None:
        _validate_required_text(value, field_name, max_length)


def _validate_reference_list(value: Any, field_name: str, max_items: int) -> None:
    if not isinstance(value, list) or len(value) > max_items:
        raise ValueError(f"{field_name} must be a list with at most {max_items} items")
    for item in value:
        _validate_canonical_id(item, field_name=field_name)
    if len(value) != len(set(value)):
        raise ValueError(f"{field_name} cannot contain duplicates")


def _validate_text_list(value: Any, field_name: str, max_items: int) -> None:
    if not isinstance(value, list) or len(value) > max_items:
        raise ValueError(f"{field_name} must be a list with at most {max_items} items")
    for item in value:
        _validate_required_text(item, field_name, 2_000)


def _validate_iso_date(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _validate_json_container(
    value: Any,
    *,
    field_name: str,
    max_bytes: int,
    max_values: int,
) -> None:
    value_count = [0]
    _validate_json_value(
        value,
        field_name=field_name,
        depth=0,
        value_count=value_count,
        max_values=max_values,
    )
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} exceeds {max_bytes} bytes")


def _validate_json_value(
    value: Any,
    *,
    field_name: str,
    depth: int,
    value_count: list[int],
    max_values: int,
) -> None:
    if depth > MAX_EVENT_NESTING_DEPTH:
        raise ValueError(f"{field_name} exceeds maximum nesting depth")
    value_count[0] += 1
    if value_count[0] > max_values:
        raise ValueError(f"{field_name} contains too many values")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} cannot contain non-finite numbers")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(
                item,
                field_name=field_name,
                depth=depth + 1,
                value_count=value_count,
                max_values=max_values,
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} keys must be strings")
            _validate_json_value(
                item,
                field_name=field_name,
                depth=depth + 1,
                value_count=value_count,
                max_values=max_values,
            )
        return
    raise ValueError(f"{field_name} contains a non-JSON value")


def _canonical_datetime(value: AwareDatetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
