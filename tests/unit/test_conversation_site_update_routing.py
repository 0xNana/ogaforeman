from datetime import UTC, datetime
from hashlib import sha256

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import SiteUpdateRouteCommand
from app.domain.enums import AttachmentUploadStatus, MemberRole, SiteUpdateInputType
from app.domain.models import ActivityEvent, AgentRun, Attachment, SiteUpdate
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


def test_multimodal_input_routes_attachments_through_the_same_intake() -> None:
    data = InMemoryRepositoryStore()
    photo = b"site-photo"
    data.repository(Attachment).create(
        Attachment(
            id="att_sitephoto123",
            project_id="prj_route123",
            object_path="projects/prj_route123/attachments/att_sitephoto123",
            content_type="image/jpeg",
            byte_size=len(photo),
            sha256=sha256(photo).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
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
            text=None,
            attachment_ids=("att_sitephoto123",),
            input_type=SiteUpdateInputType.PHOTO,
            idempotency_key="conversation:media:001",
        ),
    )

    saved = data.repository(SiteUpdate).require("prj_route123", result.site_update_id)
    assert saved.raw_text is None
    assert saved.attachment_ids == ["att_sitephoto123"]
    assert saved.input_type is SiteUpdateInputType.PHOTO
