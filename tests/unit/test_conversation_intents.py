from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.conversation import FakeIntentClassifier, IntentRoutingService
from app.domain.conversation import (
    ConfirmationDisposition,
    ConversationContext,
    IntentDecision,
    IntentDestination,
    IntentType,
    ReferencedEntity,
)


def decision(intent: IntentType, **overrides: object) -> IntentDecision:
    values: dict[str, object] = {
        "intent": intent,
        "confidence": 0.95,
        "reason_code": "explicit_test_intent",
    }
    values.update(overrides)
    return IntentDecision.model_validate(values)


@pytest.mark.parametrize(
    ("message", "context", "expected"),
    [
        ("yo OG", ConversationContext(), IntentType.CASUAL),
        ("how do i get started?", ConversationContext(), IntentType.HELP),
        (
            "what's up?",
            ConversationContext(has_active_project=True),
            IntentType.PROJECT_QUERY,
        ),
        ("what happened today?", ConversationContext(), IntentType.PROJECT_QUERY),
        ("wdyt about tomorrow?", ConversationContext(), IntentType.PROJECT_ADVICE),
        ("we have 35 bags of cement", ConversationContext(), IntentType.PROJECT_MUTATION),
        ("mark plumbing complete", ConversationContext(), IntentType.PROJECT_MUTATION),
        (
            "blockwork is done, electrician didn't show and cement is low",
            ConversationContext(),
            IntentType.SITE_UPDATE,
        ),
        (
            "yes, ground-floor plastering",
            ConversationContext(has_pending_clarification=True),
            IntentType.CLARIFICATION_RESPONSE,
        ),
        (
            "confirm",
            ConversationContext(has_pending_confirmation=True),
            IntentType.CONFIRMATION_RESPONSE,
        ),
        ("sort it out", ConversationContext(), IntentType.UNKNOWN),
    ],
)
@pytest.mark.asyncio
async def test_router_covers_phase_one_eval_taxonomy(
    message: str,
    context: ConversationContext,
    expected: IntentType,
) -> None:
    classifier = FakeIntentClassifier(
        {
            message: decision(
                expected,
                requires_project_context=expected is not IntentType.CASUAL,
                confirmation_disposition=(
                    ConfirmationDisposition.ACCEPT
                    if expected is IntentType.CONFIRMATION_RESPONSE
                    else None
                ),
            )
        }
    )

    result = await IntentRoutingService(classifier).route(message, context=context)

    assert result.decision.intent is expected


@pytest.mark.asyncio
async def test_site_update_routes_to_existing_golden_workflow() -> None:
    message = "Blockwork is done, electrician didn't show and cement is low."
    classifier = FakeIntentClassifier(
        {
            message: decision(
                IntentType.SITE_UPDATE,
                requires_project_context=True,
                requires_mutation=True,
                referenced_entities=(
                    ReferencedEntity(kind="task", reference="blockwork"),
                    ReferencedEntity(kind="material", reference="cement"),
                ),
            )
        }
    )

    result = await IntentRoutingService(classifier).route(message)

    assert result.destination is IntentDestination.GOLDEN_SITE_UPDATE
    assert result.decision.requires_mutation is True


@pytest.mark.asyncio
async def test_help_routes_without_project_context_or_mutation() -> None:
    message = "what can you do?"
    classifier = FakeIntentClassifier({message: decision(IntentType.HELP)})

    result = await IntentRoutingService(classifier).route(message)

    assert result.destination is IntentDestination.PRODUCT_HELP
    assert result.decision.requires_project_context is False
    assert result.mutation_allowed is False


@pytest.mark.asyncio
async def test_obvious_product_help_is_guarded_from_model_misrouting() -> None:
    message = "how do I add a site update?"
    classifier = FakeIntentClassifier(
        {message: decision(IntentType.PROJECT_ADVICE, requires_project_context=True)}
    )

    result = await IntentRoutingService(classifier).route(message)

    assert result.decision.intent is IntentType.HELP
    assert result.destination is IntentDestination.PRODUCT_HELP
    assert result.decision.requires_project_context is False


@pytest.mark.asyncio
async def test_project_setup_question_is_guarded_from_generic_status_misrouting() -> None:
    message = "do we have our project set?"
    classifier = FakeIntentClassifier({message: decision(IntentType.PROJECT_ADVICE)})

    result = await IntentRoutingService(classifier).route(
        message, context=ConversationContext(has_active_project=True)
    )

    assert result.decision.intent is IntentType.PROJECT_QUERY
    assert result.destination is IntentDestination.PROJECT_CONTEXT


@pytest.mark.parametrize(
    "message",
    [
        "create a task called How do I create a task guide",
        "mark the project setup task complete",
    ],
)
@pytest.mark.asyncio
async def test_deterministic_question_guards_do_not_override_mutation_messages(
    message: str,
) -> None:
    classifier = FakeIntentClassifier(
        {
            message: decision(
                IntentType.PROJECT_MUTATION,
                requires_project_context=True,
                requires_mutation=True,
            )
        }
    )

    result = await IntentRoutingService(classifier).route(message)

    assert result.destination is IntentDestination.PROJECT_ACTION
    assert result.mutation_allowed is True
    assert classifier.calls[0][0] == message


@pytest.mark.asyncio
async def test_low_confidence_mutation_is_blocked_before_any_action_route() -> None:
    classifier = FakeIntentClassifier(
        {
            "finish it": decision(
                IntentType.PROJECT_MUTATION,
                confidence=0.49,
                requires_project_context=True,
                requires_mutation=True,
                ambiguity="The task is not identified.",
            )
        }
    )

    result = await IntentRoutingService(classifier, mutation_confidence_threshold=0.8).route(
        "finish it"
    )

    assert result.destination is IntentDestination.CLARIFICATION
    assert result.mutation_allowed is False


@pytest.mark.asyncio
async def test_mutation_intent_cannot_evade_confidence_gate_with_inconsistent_flag() -> None:
    classifier = FakeIntentClassifier(
        {
            "finish it": decision(
                IntentType.PROJECT_MUTATION,
                confidence=0.49,
                requires_mutation=False,
                ambiguity="The task is not identified.",
            )
        }
    )

    result = await IntentRoutingService(classifier).route("finish it")

    assert result.destination is IntentDestination.CLARIFICATION
    assert result.mutation_allowed is False


def test_intent_decision_rejects_private_reasoning_and_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        IntentDecision(
            intent=IntentType.UNKNOWN,
            confidence=1.1,
            reason_code="unclear",
        )
    with pytest.raises(ValidationError):
        IntentDecision(
            intent=IntentType.UNKNOWN,
            confidence=0.3,
            reason_code="unclear",
            chain_of_thought="private reasoning",
        )


@pytest.mark.asyncio
async def test_confirmation_words_need_pending_confirmation_context() -> None:
    classifier = FakeIntentClassifier(
        {
            "confirm": decision(
                IntentType.CONFIRMATION_RESPONSE,
                confirmation_disposition=ConfirmationDisposition.ACCEPT,
            )
        }
    )

    result = await IntentRoutingService(classifier).route("confirm", context=ConversationContext())

    assert result.decision.intent is IntentType.UNKNOWN
    assert result.destination is IntentDestination.CLARIFICATION
    assert result.decision.reason_code == "confirmation_without_pending_action"


@pytest.mark.asyncio
async def test_low_confidence_confirmation_cannot_authorize_a_pending_change() -> None:
    classifier = FakeIntentClassifier(
        {
            "maybe do it": decision(
                IntentType.CONFIRMATION_RESPONSE,
                confidence=0.49,
                confirmation_disposition=ConfirmationDisposition.ACCEPT,
            )
        }
    )

    result = await IntentRoutingService(classifier).route(
        "maybe do it", context=ConversationContext(has_pending_confirmation=True)
    )

    assert result.destination is IntentDestination.CLARIFICATION
    assert result.mutation_allowed is False


def test_confirmation_requires_an_explicit_accept_or_cancel_disposition() -> None:
    with pytest.raises(ValidationError):
        decision(IntentType.CONFIRMATION_RESPONSE)
    with pytest.raises(ValidationError):
        decision(
            IntentType.PROJECT_QUERY,
            confirmation_disposition=ConfirmationDisposition.CANCEL,
        )
