"""Route conversational text into the existing Golden site-update intake."""

from app.domain.authorization import ProjectAccessContext, ensure_project_scope
from app.domain.conversation import SiteUpdateRouteCommand
from app.services.site_update_intake import SiteUpdateIntakeResult, SiteUpdateIntakeService


class ConversationSiteUpdateRouter:
    def __init__(self, intake: SiteUpdateIntakeService) -> None:
        self._intake = intake

    def submit(
        self, access: ProjectAccessContext, command: SiteUpdateRouteCommand
    ) -> SiteUpdateIntakeResult:
        ensure_project_scope(access, command.project_id)
        return self._intake.submit(
            access,
            idempotency_key=command.idempotency_key,
            raw_text=command.text,
            occurred_at=command.occurred_at,
        )


__all__ = ["ConversationSiteUpdateRouter"]
