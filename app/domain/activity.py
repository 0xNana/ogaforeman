"""Contracts shared by every durable domain mutation.

The activity contract deliberately contains business-facing data only.  Model
reasoning, credentials, signed URLs, and other operational secrets must never
cross this boundary.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Self

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from .enums import ActorType
from .models import CanonicalId, DomainModel, IdempotencyKey


class MutationContextRequiredError(ValueError):
    """Raised when a mutation is attempted without its audit context."""

    code = "MUTATION_CONTEXT_REQUIRED"


class UnsafeActivityDataError(ValueError):
    """Raised when user-facing activity data contains restricted information."""

    code = "ACTIVITY_DATA_UNSAFE"


class MutationContext(DomainModel):
    """Immutable identity and causality context for one mutation attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: CanonicalId
    actor_type: ActorType
    actor_id: CanonicalId | None = None
    source_event_id: CanonicalId | None = None
    agent_run_id: CanonicalId | None = None
    idempotency_key: IdempotencyKey
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_causality(self) -> Self:
        if self.actor_type in {ActorType.USER, ActorType.AGENT} and self.actor_id is None:
            raise MutationContextRequiredError("actor_id is required for user and agent mutations")
        if self.actor_type is ActorType.SYSTEM and self.actor_id is not None:
            raise ValueError("system mutations must not impersonate a user or agent")
        if self.source_event_id is None and self.actor_type is not ActorType.USER:
            raise MutationContextRequiredError(
                "agent and system mutations require a source_event_id"
            )
        return self


# The public ToolContext name is used by the tool contract document.  Keeping
# the alias here avoids two subtly different context contracts.
ToolContext = MutationContext


class ActivitySpec(DomainModel):
    """Safe, user-facing description of a mutation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=1, max_length=300)
    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: CanonicalId
    summary: str = Field(min_length=1, max_length=5_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_safe_payload(self) -> Self:
        _validate_safe_text(self.action, field_name="action")
        _validate_safe_text(self.summary, field_name="summary")
        _validate_json(self.metadata, path="metadata")
        return self


def activity_id(context: MutationContext) -> str:
    """Derive a stable, opaque activity ID from the scoped idempotency key."""

    material = (
        f"{context.project_id}\x00{context.actor_id or 'system'}\x00{context.idempotency_key}"
    )
    return f"act_{sha256(material.encode('utf-8')).hexdigest()[:32]}"


def mutation_fingerprint(context: MutationContext, spec: ActivitySpec) -> str:
    """Fingerprint the complete safe mutation envelope for replay protection."""

    canonical = json.dumps(
        {
            "project_id": context.project_id,
            "actor_type": context.actor_type.value,
            "actor_id": context.actor_id,
            "source_event_id": context.source_event_id,
            "agent_run_id": context.agent_run_id,
            "idempotency_key": context.idempotency_key,
            "action": spec.action,
            "entity_type": spec.entity_type,
            "entity_id": spec.entity_id,
            "summary": spec.summary,
            "metadata": spec.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


_FORBIDDEN_NAME_PARTS = (
    "chain_of_thought",
    "chain-of-thought",
    "hidden_reasoning",
    "internal_reasoning",
    "prompt_tokens",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "credential",
    "private_key",
    "signed_url",
)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)


def _validate_safe_text(value: str, *, field_name: str) -> None:
    lowered = value.casefold()
    if any(part in lowered for part in _FORBIDDEN_NAME_PARTS) or _BEARER_RE.search(value):
        raise UnsafeActivityDataError(f"{field_name} contains restricted operational data")


def _validate_json(value: Any, *, path: str, depth: int = 0) -> None:
    if depth > 8:
        raise UnsafeActivityDataError("activity metadata is too deeply nested")
    if isinstance(value, str):
        if len(value) > 5_000:
            raise UnsafeActivityDataError(f"{path} contains an oversized text value")
        _validate_safe_text(value, field_name=path)
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, list | tuple):
        if len(value) > 100:
            raise UnsafeActivityDataError(f"{path} contains too many values")
        for index, item in enumerate(value):
            _validate_json(item, path=f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 100:
            raise UnsafeActivityDataError(f"{path} contains too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 100:
                raise UnsafeActivityDataError(f"{path} contains an invalid field name")
            _validate_safe_text(key, field_name=f"{path}.{key}")
            _validate_json(item, path=f"{path}.{key}", depth=depth + 1)
        return
    raise UnsafeActivityDataError(f"{path} contains unsupported data")


__all__ = [
    "ActivitySpec",
    "MutationContext",
    "MutationContextRequiredError",
    "ToolContext",
    "UnsafeActivityDataError",
    "activity_id",
    "mutation_fingerprint",
]
