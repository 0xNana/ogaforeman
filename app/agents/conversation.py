"""Intent classification boundary for conversational OG."""

from __future__ import annotations

from typing import Protocol

from app.domain.conversation import (
    ConversationContext,
    IntentDecision,
    IntentDestination,
    IntentRoute,
    IntentType,
)


class IntentClassifier(Protocol):
    async def classify(
        self,
        message: str,
        *,
        context: ConversationContext,
    ) -> IntentDecision: ...


class FakeIntentClassifier:
    """Deterministic classifier used only at the model boundary in tests and evals."""

    def __init__(self, responses: dict[str, IntentDecision]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, ConversationContext]] = []

    async def classify(
        self,
        message: str,
        *,
        context: ConversationContext,
    ) -> IntentDecision:
        self.calls.append((message, context))
        return self._responses.get(
            message,
            IntentDecision(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                ambiguity="The message intent could not be classified.",
                reason_code="no_classification",
            ),
        )


class IntentRoutingService:
    """Validate a classifier decision and select a non-mutating destination."""

    def __init__(
        self,
        classifier: IntentClassifier,
        *,
        mutation_confidence_threshold: float = 0.8,
    ) -> None:
        if not 0.0 <= mutation_confidence_threshold <= 1.0:
            raise ValueError("mutation confidence threshold must be between zero and one")
        self._classifier = classifier
        self._mutation_confidence_threshold = mutation_confidence_threshold

    async def route(
        self,
        message: str,
        *,
        context: ConversationContext | None = None,
    ) -> IntentRoute:
        normalized = message.strip()
        if not normalized:
            raise ValueError("conversation message cannot be empty")
        active_context = context or ConversationContext()
        decision = await self._classifier.classify(normalized, context=active_context)
        decision = _validate_contextual_response(decision, active_context)
        mutation_intent = decision.intent in {
            IntentType.PROJECT_MUTATION,
            IntentType.SITE_UPDATE,
        }

        if mutation_intent and decision.confidence < self._mutation_confidence_threshold:
            return IntentRoute(
                decision=decision,
                destination=IntentDestination.CLARIFICATION,
                mutation_allowed=False,
            )

        destination = _DESTINATIONS[decision.intent]
        return IntentRoute(
            decision=decision,
            destination=destination,
            mutation_allowed=mutation_intent,
        )


_DESTINATIONS = {
    IntentType.CASUAL: IntentDestination.CASUAL_RESPONSE,
    IntentType.PROJECT_QUERY: IntentDestination.PROJECT_CONTEXT,
    IntentType.PROJECT_ADVICE: IntentDestination.PROJECT_ADVICE,
    IntentType.PROJECT_MUTATION: IntentDestination.PROJECT_ACTION,
    IntentType.SITE_UPDATE: IntentDestination.GOLDEN_SITE_UPDATE,
    IntentType.CLARIFICATION_RESPONSE: IntentDestination.CLARIFICATION,
    IntentType.CONFIRMATION_RESPONSE: IntentDestination.CONFIRMATION,
    IntentType.UNKNOWN: IntentDestination.CLARIFICATION,
}


def _validate_contextual_response(
    decision: IntentDecision,
    context: ConversationContext,
) -> IntentDecision:
    if decision.intent is IntentType.CONFIRMATION_RESPONSE and not context.has_pending_confirmation:
        return IntentDecision(
            intent=IntentType.UNKNOWN,
            confidence=decision.confidence,
            ambiguity="There is no pending change to confirm.",
            reason_code="confirmation_without_pending_action",
        )
    if (
        decision.intent is IntentType.CLARIFICATION_RESPONSE
        and not context.has_pending_clarification
    ):
        return IntentDecision(
            intent=IntentType.UNKNOWN,
            confidence=decision.confidence,
            ambiguity="There is no pending clarification to answer.",
            reason_code="clarification_without_pending_question",
        )
    return decision


__all__ = ["FakeIntentClassifier", "IntentClassifier", "IntentRoutingService"]
