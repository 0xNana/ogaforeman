"""Typed, non-mutating contracts for conversational intent routing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IntentType(StrEnum):
    CASUAL = "casual"
    PROJECT_QUERY = "project_query"
    PROJECT_ADVICE = "project_advice"
    PROJECT_MUTATION = "project_mutation"
    SITE_UPDATE = "site_update"
    CLARIFICATION_RESPONSE = "clarification_response"
    CONFIRMATION_RESPONSE = "confirmation_response"
    UNKNOWN = "unknown"


class IntentDestination(StrEnum):
    CASUAL_RESPONSE = "casual_response"
    PROJECT_CONTEXT = "project_context"
    PROJECT_ADVICE = "project_advice"
    PROJECT_ACTION = "project_action"
    GOLDEN_SITE_UPDATE = "golden_site_update"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"


class ReferencedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    reference: str = Field(min_length=1, max_length=160)


class IntentDecision(BaseModel):
    """Observable classification output; private model reasoning is forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    requested_action: str | None = Field(default=None, max_length=160)
    referenced_entities: tuple[ReferencedEntity, ...] = Field(default_factory=tuple)
    requires_project_context: bool = False
    requires_mutation: bool = False
    ambiguity: str | None = Field(default=None, max_length=240)
    reason_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")


class ConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    has_active_project: bool = False
    has_pending_clarification: bool = False
    has_pending_confirmation: bool = False


class IntentRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: IntentDecision
    destination: IntentDestination
    mutation_allowed: bool = False


__all__ = [
    "ConversationContext",
    "IntentDecision",
    "IntentDestination",
    "IntentRoute",
    "IntentType",
    "ReferencedEntity",
]
