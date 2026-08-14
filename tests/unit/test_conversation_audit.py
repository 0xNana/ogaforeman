from datetime import UTC, datetime

from app.domain.activity import MutationContext
from app.domain.enums import ActorType
from app.domain.models import ActivityEvent
from app.repositories.memory import InMemoryRepositoryStore
from app.services.activity import ActivityService
from app.services.conversation_audit import ConversationAuditService


def test_significant_conversation_transition_is_allowlisted_and_idempotent() -> None:
    store = InMemoryRepositoryStore()
    context = MutationContext(
        project_id="prj_audit123",
        actor_type=ActorType.USER,
        actor_id="usr_ace123",
        idempotency_key="conversation:request:123",
        occurred_at=datetime(2026, 8, 14, tzinfo=UTC),
    )
    service = ConversationAuditService(ActivityService(store))

    first = service.record(
        context,
        action="conversation.mutation_requested",
        entity_type="task",
        entity_id="tsk_plumbing123",
        summary="Task completion requested through OG.",
        reason_code="explicit_task_completion",
    )
    replay = service.record(
        context,
        action="conversation.mutation_requested",
        entity_type="task",
        entity_id="tsk_plumbing123",
        summary="Task completion requested through OG.",
        reason_code="explicit_task_completion",
    )

    assert first.duplicate is False
    assert replay.duplicate is True
    assert len(store.repository(ActivityEvent).list("prj_audit123")) == 1
