from datetime import UTC, datetime

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import SiteUpdateRouteCommand
from app.domain.enums import MemberRole
from app.domain.models import ActivityEvent, AgentRun, SiteUpdate
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_site_update_routing import ConversationSiteUpdateRouter
from app.services.site_update_intake import SiteUpdateIntakeService


class Publisher:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def publish(self, topic, data, *, attributes=None) -> str:
        del topic, attributes
        self.payloads.append(data)
        return f"msg_{len(self.payloads)}"


def test_text_chat_routes_to_existing_durable_site_update_intake() -> None:
    data = InMemoryRepositoryStore()
    publisher = Publisher()
    router = ConversationSiteUpdateRouter(SiteUpdateIntakeService(data, publisher))
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager"),
        project_id="prj_route123",
        role=MemberRole.MANAGER,
    )
    result = router.submit(
        access,
        SiteUpdateRouteCommand(
            project_id="prj_route123",
            text="Blockwork is done and cement is low.",
            idempotency_key="chat:route:001",
            occurred_at=datetime(2020, 8, 14, 13, tzinfo=UTC),
        ),
    )
    assert result.site_update_id.startswith("sup_")
    assert (
        data.repository(SiteUpdate).require("prj_route123", result.site_update_id).raw_text
        == "Blockwork is done and cement is low."
    )
    assert (
        data.repository(AgentRun).require("prj_route123", result.agent_run_id).trigger_event_id
        == result.event_id
    )
    assert len(data.repository(ActivityEvent).list("prj_route123")) == 1
    assert len(publisher.payloads) == 1
