"""Allowlisted, replay-safe audit events for observable conversation transitions."""

from __future__ import annotations

from app.domain.activity import ActivitySpec, MutationContext
from app.services.activity import ActivityService, MutationResult


class ConversationAuditService:
    def __init__(self, activities: ActivityService) -> None:
        self._activities = activities

    def record(
        self,
        context: MutationContext,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        summary: str,
        reason_code: str,
    ) -> MutationResult[None]:
        if not action.startswith("conversation."):
            raise ValueError("conversation audit actions must use the typed conversation namespace")
        return self._activities.mutate(
            context,
            ActivitySpec(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                metadata={"reason_code": reason_code},
            ),
            lambda _session: None,
        )


__all__ = ["ConversationAuditService"]
