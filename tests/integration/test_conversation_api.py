from decimal import Decimal
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.agents.conversation import FakeIntentClassifier
from app.domain.activity import MutationContext
from app.api.errors import install_error_handlers
from app.api.v1.router import api_router
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectForbiddenError
from app.domain.conversation import (
    AgenticConversationAnswer,
    ConversationalProjectContext,
    IntentDecision,
    IntentType,
    PendingConversationCommand,
)
from app.domain.conversation import IssueOperation, MaterialOperation, TaskOperation
from app.domain.enums import (
    AgentRunStatus,
    AttachmentUploadStatus,
    ActorType,
    ApprovalStatus,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MemberRole,
    MemberStatus,
    MaterialRequestStatus,
    ProjectStatus,
    Severity,
    TaskStatus,
)
from app.domain.models import (
    AgentRun,
    ActivityEvent,
    Approval,
    Attachment,
    ConversationMemory,
    ConversationProposalClaim,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    Project,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_action_composer import (
    IssueActionInterpretation,
    MaterialActionInterpretation,
    PurchaseActionInterpretation,
    TaskActionInterpretation,
    ScheduleActionInterpretation,
)
from app.services.approvals import ApprovalService, ResolutionCommand
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_schedule_operations import ConversationScheduleService
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService
from app.services.site_update_intake import SiteUpdateIntakeService
from app.workflows.resume import ResumeWorkflow


PROJECT_ID = "prj_conversation123"
PROPOSAL_SIGNING_KEY = b"conversation-api-envelope-signing-key-32-bytes"


class Publisher:
    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: dict[str, str] | None = None,
    ) -> str:
        del topic, data, attributes
        return "msg_conversation123"


class FakeActionInterpreter:
    async def interpret(
        self, message: str, *, context: object
    ) -> (
        MaterialActionInterpretation
        | TaskActionInterpretation
        | IssueActionInterpretation
        | ScheduleActionInterpretation
        | PurchaseActionInterpretation
    ):
        assert context is not None
        assert context.project is not None
        assert context.project.timezone == "Africa/Accra"
        if message in {
            "we've got 100 bags of cement now",
            "cement count confirms one hundred bags",
        }:
            return MaterialActionInterpretation(
                operation=MaterialOperation.SET_ON_SITE,
                material_reference="cement",
                quantity=Decimal("100"),
                unit="bags",
                reason="User reported current stock count.",
            )
        if message == "we've got 90 bags of cement now":
            return MaterialActionInterpretation(
                operation=MaterialOperation.SET_ON_SITE,
                material_reference="cement",
                quantity=Decimal("90"),
                unit="bags",
                reason="User reported current stock count.",
            )
        if message == "add additional 60 bags of cement":
            return MaterialActionInterpretation(
                operation=MaterialOperation.ADJUST_ON_SITE,
                material_reference="cement",
                quantity_delta=Decimal("60"),
                unit="bags",
                reason="User requested an additional stock increment.",
            )
        if message == "add 20 bags of cement to our inventory":
            return MaterialActionInterpretation(
                operation=MaterialOperation.ADJUST_ON_SITE,
                material_reference="cement",
                quantity_delta=Decimal("20"),
                unit="bags",
                reason="User requested an inventory increment.",
            )
        if message == "plastering is complete":
            return TaskActionInterpretation(
                operation=TaskOperation.COMPLETE,
                task_reference="plastering",
                evidence="User explicitly reported plastering complete.",
            )
        if message == "cancel plastering":
            return TaskActionInterpretation(
                operation=TaskOperation.CHANGE_STATUS,
                task_reference="plastering",
                target_status=TaskStatus.CANCELLED,
            )
        if message == "electrical is sorted":
            return IssueActionInterpretation(
                operation=IssueOperation.RESOLVE,
                issue_reference="electrical",
                evidence="User explicitly reported electrical is sorted.",
            )
        if message == "move plastering to Friday":
            return ScheduleActionInterpretation(
                task_reference="plastering",
                planned_start=datetime(2026, 8, 21, 8, tzinfo=UTC),
                planned_end=datetime(2026, 8, 21, 17, tzinfo=UTC),
            )
        if message == "buy 100 bags of cement":
            return PurchaseActionInterpretation(
                material_reference="cement",
                quantity=Decimal("100"),
                unit="bags",
                reason="Cement requested for upcoming work.",
            )
        raise AssertionError(f"unexpected action message: {message}")


class Projects:
    def __init__(self, project: Project) -> None:
        self.project = project

    def require(self, access: ProjectAccessContext) -> Project:
        assert access.project_id == self.project.id
        return self.project

    def list_for_user(self, actor: AuthenticatedUser) -> tuple[Project, ...]:
        assert actor.user_id == "usr_ace123"
        return (self.project,)


def make_app() -> tuple[FastAPI, InMemoryRepositoryStore]:
    store = InMemoryRepositoryStore()
    project = Project(
        id=PROJECT_ID,
        name="Ridge House",
        location="Accra",
        timezone="Africa/Accra",
        status=ProjectStatus.ACTIVE,
        created_by="usr_ace123",
    )
    store.repository(Task).create(
        Task(
            id="tsk_plaster123",
            project_id=PROJECT_ID,
            title="Plastering",
            status=TaskStatus.IN_PROGRESS,
            assigned_to="usr_kofi123",
        )
    )
    store.repository(Issue).create(
        Issue(
            id="iss_electrical123",
            project_id=PROJECT_ID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrical rough-in remains blocked",
            status=IssueStatus.OPEN,
            detected_by=IssueDetectedBy.USER,
            task_ids=["tsk_plaster123"],
        )
    )
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement",
            normalized_name="cement",
            unit="bags",
            available_quantity=Decimal("10"),
            minimum_required_quantity=Decimal("40"),
        )
    )
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=PROJECT_ID,
            user_id="usr_kofi123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    classifier = FakeIntentClassifier(
        {
            "how do i get started?": IntentDecision(
                intent=IntentType.HELP,
                confidence=0.99,
                reason_code="product_help",
            ),
            "what can you do?": IntentDecision(
                intent=IntentType.HELP,
                confidence=0.99,
                reason_code="product_help",
            ),
            "Add 50 bags of cement": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="material_quantity",
            ),
            "do we have our project set?": IntentDecision(
                intent=IntentType.PROJECT_QUERY,
                confidence=0.99,
                requires_project_context=True,
                reason_code="project_setup",
            ),
            "wdyt about plastering tomorrow?": IntentDecision(
                intent=IntentType.PROJECT_ADVICE,
                confidence=0.99,
                requires_project_context=True,
                reason_code="project_advice",
            ),
            "move plastering to Friday": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                requested_action="Move plastering to Friday",
                reason_code="schedule_change",
            ),
            "we've got 100 bags of cement now": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                requested_action="Set cement stock to 100 bags",
                reason_code="material_quantity",
            ),
            "we've got 90 bags of cement now": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="material_quantity",
            ),
            "add additional 60 bags of cement": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                requested_action="Add 60 bags to cement stock",
                reason_code="material_quantity_adjustment",
            ),
            "add 20 bags of cement to our inventory": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="material_quantity_adjustment",
            ),
            "cement count confirms one hundred bags": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="material_quantity",
            ),
            "cancel plastering": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="task_cancel",
            ),
            "plastering is complete": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="task_complete",
            ),
            "electrical is sorted": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="issue_resolve",
            ),
            "buy 100 bags of cement": IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=0.99,
                requires_project_context=True,
                requires_mutation=True,
                reason_code="material_purchase",
            ),
            "what's blocking plastering?": IntentDecision(
                intent=IntentType.PROJECT_QUERY,
                confidence=0.99,
                requires_project_context=True,
                reason_code="blocker_query",
            ),
            "who owns it?": IntentDecision(
                intent=IntentType.PROJECT_QUERY,
                confidence=0.99,
                requires_project_context=True,
                reason_code="ownership_query",
            ),
        }
    )
    app = FastAPI()
    app.state.auth_runtime = SimpleNamespace(
        store=store,
        projects=Projects(project),
        authenticate=lambda _request: AuthenticatedUser(user_id="usr_ace123", subject="ace"),
        project_member_names=lambda _project_id: {"usr_kofi123": "Kofi Mensah"},
    )
    app.state.project_access_provider = lambda _request, project_id, _permission: (
        ProjectAccessContext(
            actor=AuthenticatedUser(user_id="usr_ace123", subject="ace"),
            project_id=project_id,
            role=MemberRole.MANAGER,
        )
    )
    app.state.intent_classifier = classifier
    app.state.action_interpreter = FakeActionInterpreter()
    app.state.conversation_proposal_signing_key = PROPOSAL_SIGNING_KEY
    app.state.conversation_schedule_service = ConversationScheduleService(
        store,
        MutationPolicyService(),
        proposal_signing_key=b"conversation-api-schedule-signing-key-32-bytes",
    )
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app, store


@pytest.mark.asyncio
async def test_product_help_needs_no_project_data_and_exposes_og_author() -> None:
    app, _store = make_app()
    app.state.project_access_provider = lambda *_args: (_ for _ in ()).throw(
        AssertionError("product help must not authorize or read a project")
    )
    del app.state.intent_classifier
    app.state.auth_runtime = SimpleNamespace(
        authenticate=lambda _request: AuthenticatedUser(user_id="usr_ace123", subject="ace")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "how do i get started?"},
            headers={"Idempotency-Key": "conversation:help:1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "help"
    assert body["assistant_name"] == "OG"
    assert body["intent"] == "help"
    assert "type an update" in body["text"]
    assert body["mutation_performed"] is False


@pytest.mark.asyncio
async def test_user_scoped_setup_reports_when_no_project_exists() -> None:
    app, _store = make_app()
    app.state.auth_runtime.projects = SimpleNamespace(list_for_user=lambda _actor: ())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/conversations/messages",
            json={"message": "is my project set up?"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "project"
    assert "create or open a project" in response.json()["text"].casefold()


@pytest.mark.asyncio
async def test_project_setup_question_reports_live_readiness_and_counts() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "do we have our project set?"},
            headers={"Idempotency-Key": "conversation:setup:1"},
        )

    assert response.status_code == 200
    assert response.json()["text"] == (
        "Yes. Ridge House is operational. I have One task, One open issue, "
        "and materials are being tracked."
    )
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


@pytest.mark.asyncio
async def test_project_answer_is_generated_from_authorized_live_context() -> None:
    app, _store = make_app()

    class CapturingConversationAgent:
        def __init__(self) -> None:
            self.contexts: list[object] = []

        async def respond(
            self,
            message: str,
            *,
            intent: IntentType,
            context: ConversationalProjectContext,
        ) -> AgenticConversationAnswer:
            self.contexts.append(context)
            assert message == "what's blocking plastering?"
            assert intent is IntentType.PROJECT_QUERY
            issue = next(item for item in context.issues if "electrical" in item.description)
            return AgenticConversationAnswer(
                text="Gemini grounded answer: electrical clearance is blocking plastering.",
                cited_record_ids=(issue.id,),
            )

    agent = CapturingConversationAgent()
    app.state.conversation_agent = agent
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "what's blocking plastering?"},
            headers={"Idempotency-Key": "conversation:grounded-agent:1"},
        )

    assert response.status_code == 200
    assert response.json()["text"].startswith("Gemini grounded answer:")
    assert response.json()["cited_record_ids"]
    assert len(agent.contexts) == 1


@pytest.mark.asyncio
async def test_project_status_follow_up_returns_grounded_entity_state() -> None:
    app, store = make_app()
    store.repository(Task).create(
        Task(
            id="tsk_clearance123",
            project_id=PROJECT_ID,
            title="Site clearance",
            status=TaskStatus.COMPLETED,
            completion_percent=Decimal("100"),
            actual_completion=datetime(2026, 8, 12, 12, tzinfo=UTC),
        )
    )
    classifier = app.state.intent_classifier
    classifier._responses.update(
        {
            "OG where are we with our project": IntentDecision(
                intent=IntentType.PROJECT_QUERY,
                confidence=0.99,
                requires_project_context=True,
                reason_code="project_status",
            ),
            "how about site clearance": IntentDecision(
                intent=IntentType.PROJECT_QUERY,
                confidence=0.99,
                requires_project_context=True,
                reason_code="entity_status",
            ),
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "OG where are we with our project"},
        )
        second = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "how about site clearance"},
        )

    assert first.status_code == 200
    assert "Ridge House is active" in first.json()["text"]
    assert second.status_code == 200
    assert "Site clearance is completed" in second.json()["text"]
    assert "urgent project changes" not in second.json()["text"]


@pytest.mark.asyncio
async def test_malformed_action_interpretation_is_recoverable_without_mutation() -> None:
    app, store = make_app()

    class MalformedInterpreter:
        async def interpret(self, message: str, *, context: object) -> object:
            from app.services.conversation_action_composer import ActionInterpretationEnvelope

            return ActionInterpretationEnvelope.model_validate(
                {"action": {"operation": "adjust_on_hand", "quantity_delta": 50}}
            ).action

    app.state.action_interpreter = MalformedInterpreter()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "add 20 bags of cement to our inventory"},
            headers={"Idempotency-Key": "conversation:malformed-action:1"},
        )

    assert response.status_code == 200
    assert "couldn't safely interpret" in response.json()["text"]
    assert store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity == 10
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


@pytest.mark.asyncio
async def test_missing_inventory_material_is_created_through_typed_service() -> None:
    app, store = make_app()

    class MissingMaterialInterpreter:
        async def interpret(self, message: str, *, context: object) -> object:
            return MaterialActionInterpretation(
                operation=MaterialOperation.ADJUST_ON_SITE,
                material_reference="tile adhesive",
                quantity_delta=Decimal("20"),
                unit="bags",
                reason="Initial inventory reported by user.",
            )

    app.state.action_interpreter = MissingMaterialInterpreter()
    app.state.intent_classifier._responses["add 20 bags of tile adhesive to inventory"] = (
        IntentDecision(
            intent=IntentType.PROJECT_MUTATION,
            confidence=0.99,
            requires_project_context=True,
            requires_mutation=True,
            reason_code="material_quantity_adjustment",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "add 20 bags of tile adhesive to inventory"},
            headers={"Idempotency-Key": "conversation:create-material:1"},
        )

    assert response.status_code == 200
    created = [
        item
        for item in store.repository(Material).list(PROJECT_ID)
        if item.normalized_name == "tile adhesive"
    ]
    assert len(created) == 1
    assert created[0].available_quantity == Decimal("20")
    events = store.repository(ActivityEvent).list(PROJECT_ID)
    assert any(
        event.action == "material.created" and event.entity_id == created[0].id for event in events
    )


@pytest.mark.asyncio
async def test_missing_inventory_material_without_quantity_clarifies() -> None:
    app, store = make_app()

    class IncompleteMaterialInterpreter:
        async def interpret(self, message: str, *, context: object) -> object:
            return MaterialActionInterpretation(
                operation=MaterialOperation.ADJUST_ON_SITE,
                material_reference="tile adhesive",
            )

    app.state.action_interpreter = IncompleteMaterialInterpreter()
    app.state.intent_classifier._responses["add tile adhesive"] = IntentDecision(
        intent=IntentType.PROJECT_MUTATION,
        confidence=0.99,
        requires_project_context=True,
        requires_mutation=True,
        reason_code="material_quantity_adjustment",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "add tile adhesive"},
            headers={"Idempotency-Key": "conversation:create-material:incomplete"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "clarification"
    assert not any(
        item.normalized_name == "tile adhesive"
        for item in store.repository(Material).list(PROJECT_ID)
    )


@pytest.mark.asyncio
async def test_project_setup_question_guides_a_minimal_project_without_fake_counts() -> None:
    app, store = make_app()
    for model in (Task, Issue, Material):
        for item in store.repository(model).list(PROJECT_ID):
            version = store.repository(model).version_of(PROJECT_ID, item.id)
            store.repository(model).delete(PROJECT_ID, item.id, expected_version=version)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "do we have our project set?"},
            headers={"Idempotency-Key": "conversation:setup:minimal"},
        )

    assert response.status_code == 200
    text = response.json()["text"]
    assert "Ridge House is created, but it's still mostly empty" in text
    assert "tell me what's happening on site today" in text
    assert "task" not in text.casefold()


@pytest.mark.asyncio
async def test_project_setup_ignores_cancelled_tasks_for_readiness_and_counts() -> None:
    app, store = make_app()
    task_repository = store.repository(Task)
    task = task_repository.require(PROJECT_ID, "tsk_plaster123")
    task_repository.save(
        task.model_copy(
            update={
                "status": TaskStatus.CANCELLED,
                "planned_start": datetime(2026, 8, 16, 8, tzinfo=UTC),
            }
        ),
        expected_version=task_repository.version_of(PROJECT_ID, task.id),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "do we have our project set?"},
        )

    assert response.status_code == 200
    assert "One task" not in response.json()["text"]


@pytest.mark.asyncio
async def test_ambiguous_material_quantity_is_clarification_without_idempotency_key() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={
                "message": "Add 50 bags of cement",
                "attachment_ids": [],
                "input_type": "text",
            },
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "clarification"
    assert response.json()["text"] == (
        "Do you mean 50 bags arrived on site, or you want me to prepare a request for 50 bags?"
    )
    memory = store.repository(ConversationMemory).get(
        PROJECT_ID,
        f"mem_{sha256((PROJECT_ID + chr(0) + 'usr_ace123').encode()).hexdigest()[:24]}",
    )
    assert memory is not None
    assert memory.pending_clarification == response.json()["text"]


@pytest.mark.asyncio
async def test_advice_is_grounded_and_does_not_emit_mutation_activity() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "wdyt about plastering tomorrow?"},
            headers={"Idempotency-Key": "conversation:advice:1"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "advice"
    assert response.json()["mutation_performed"] is False
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


@pytest.mark.asyncio
async def test_multimodal_conversation_entry_routes_photo_to_golden_intake() -> None:
    app, store = make_app()
    publisher = Publisher()
    photo = b"site-photo"
    store.repository(Attachment).create(
        Attachment(
            id="att_sitephoto123",
            project_id=PROJECT_ID,
            object_path=f"projects/{PROJECT_ID}/attachments/att_sitephoto123",
            content_type="image/jpeg",
            byte_size=len(photo),
            sha256=sha256(photo).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={
                "message": "",
                "attachment_ids": ["att_sitephoto123"],
                "input_type": "photo",
            },
            headers={"Idempotency-Key": "conversation:photo:1"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "workflow"
    assert response.json()["workflow_run_id"] is not None
    updates = store.repository(SiteUpdate).list(PROJECT_ID)
    assert len(updates) == 1
    assert updates[0].attachment_ids == ["att_sitephoto123"]


@pytest.mark.asyncio
async def test_relative_material_stock_message_adjusts_existing_quantity() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "add additional 60 bags of cement"},
            headers={"Idempotency-Key": "conversation:cement:add:60"},
        )

    assert response.status_code == 200
    assert response.json()["mutation_performed"] is True
    assert response.json()["text"] == "Done. Cement is now recorded at 70 bags."
    material = store.repository(Material).require(PROJECT_ID, "mat_cement123")
    assert material.available_quantity == 70
    assert len(store.repository(ActivityEvent).list(PROJECT_ID)) == 1


@pytest.mark.asyncio
async def test_inventory_modifier_is_not_over_clarified_and_increments_stock() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "add 20 bags of cement to our inventory"},
            headers={"Idempotency-Key": "conversation:cement:inventory:20"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "done"
    assert response.json()["text"] == "Done. Cement is now recorded at 30 bags."
    assert store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity == 30
    assert len(store.repository(ActivityEvent).list(PROJECT_ID)) == 1


@pytest.mark.asyncio
async def test_unauthorized_conversation_action_is_rejected_without_mutation() -> None:
    app, store = make_app()

    def deny_access(*_args: object, **_kwargs: object) -> ProjectAccessContext:
        raise ProjectForbiddenError("project access denied")

    app.state.project_access_provider = deny_access
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "we've got 100 bags of cement now"},
            headers={"Idempotency-Key": "conversation:unauthorized:1"},
        )

    assert response.status_code == 403
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


@pytest.mark.asyncio
async def test_ambiguous_entity_requests_clarification_without_mutation() -> None:
    app, store = make_app()
    store.repository(Task).create(
        Task(
            id="tsk_plaster_duplicate123",
            project_id=PROJECT_ID,
            title="Plastering",
            status=TaskStatus.PLANNED,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:ambiguous:1"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "clarification"
    assert response.json()["mutation_performed"] is False
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


@pytest.mark.asyncio
async def test_expired_unreserved_proposal_is_rejected_without_mutation() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:expired:1"},
        )
        memory = store.repository(ConversationMemory).list(PROJECT_ID)[0]
        assert memory.pending_command is not None
        now = datetime.now(UTC)
        expired = memory.pending_command.model_copy(
            update={
                "created_at": now - timedelta(minutes=20),
                "expires_at": now - timedelta(minutes=5),
            }
        )
        sealed = ConversationMemoryService(
            store,
            ConversationEntityResolver(store),
            proposal_signing_key=PROPOSAL_SIGNING_KEY,
        ).seal_command(expired)
        store.repository(ConversationMemory).save(
            memory.model_copy(update={"pending_command": sealed}),
            expected_version=memory.version,
        )
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/"
            f"{proposed.json()['proposal_id']}/confirm",
            json={"observed_memory_version": proposed.json()["memory_version"] + 1},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_PROPOSAL"
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start is None


@pytest.mark.asyncio
async def test_project_change_is_proposed_audited_and_replay_safe() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:1"},
        )
        pending = await client.get(f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/pending")
        task = store.repository(Task).require(PROJECT_ID, "tsk_plaster123")
        store.repository(Task).save(
            task.model_copy(update={"description": "Changed after proposal."}),
            expected_version=task.version,
        )
        stale = await client.get(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{first.json()['proposal_id']}",
            params={"memory_version": first.json()["memory_version"]},
        )
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:1"},
        )

    assert response.status_code == 200
    assert pending.status_code == 200
    assert pending.json()["proposal"]["proposal_id"] == first.json()["proposal_id"]
    assert pending.json()["memory_version"] == first.json()["memory_version"]
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "PROPOSAL_CONFLICT"
    assert response.json() == first.json()
    assert response.json()["kind"] == "proposed_change"
    assert response.json()["mutation_performed"] is False
    assert [item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)] == [
        "conversation.proposal_created"
    ]
    assert len(store.repository(ConversationMemory).list(PROJECT_ID)) == 1
    memory = store.repository(ConversationMemory).list(PROJECT_ID)[0]
    assert memory.pending_command is not None
    assert memory.pending_command.kind == "schedule"
    assert memory.pending_command.observed_memory_version == 0
    assert memory.pending_command.expires_at > memory.pending_command.created_at
    assert (
        memory.pending_command.expires_at - memory.pending_command.created_at
    ).total_seconds() == 900
    assert memory.pending_command.observed_entity_versions == {
        "tsk_plaster123": 0,
    }
    assert memory.pending_command.command.proposal is not None
    assert response.json()["proposal_id"] == memory.pending_command.proposal_id
    assert response.json()["memory_version"] == memory.version
    assert response.json()["proposal"] == memory.pending_command.model_dump(mode="json")


@pytest.mark.asyncio
async def test_pending_proposal_can_be_reloaded_and_cancelled_without_domain_mutation() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:cancel"},
        )
        proposal_id = proposed.json()["proposal_id"]
        memory_version = proposed.json()["memory_version"]
        loaded = await client.get(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}",
            params={"memory_version": memory_version},
        )
        cancelled = await client.delete(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}",
            params={"memory_version": memory_version},
        )
        retry = await client.delete(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}",
            params={"memory_version": memory_version},
        )

    assert loaded.status_code == 200
    assert loaded.json()["proposal"] == proposed.json()["proposal"]
    assert cancelled.status_code == 200
    assert retry.json() == cancelled.json()
    assert cancelled.json()["kind"] == "proposal_cancelled"
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start is None
    assert store.repository(ConversationMemory).list(PROJECT_ID)[0].pending_command is None
    assert [item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)] == [
        "conversation.proposal_created",
        "conversation.proposal_cleared",
    ]


@pytest.mark.asyncio
async def test_server_proposal_confirmation_executes_once_and_consumes_command() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:confirm"},
        )
        path = (
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/"
            f"{proposed.json()['proposal_id']}/confirm"
        )
        confirmed = await client.post(
            path,
            json={"observed_memory_version": proposed.json()["memory_version"]},
        )
        retry = await client.post(
            path,
            json={"observed_memory_version": proposed.json()["memory_version"]},
        )

    assert confirmed.status_code == 200
    assert confirmed.json()["mutation_performed"] is True
    assert retry.status_code == 200
    assert retry.json()["mutation_performed"] is False
    assert retry.json()["activity_id"] == confirmed.json()["activity_id"]
    task = store.repository(Task).require(PROJECT_ID, "tsk_plaster123")
    assert task.planned_start == datetime(2026, 8, 21, 8, tzinfo=UTC)
    assert store.repository(ConversationMemory).list(PROJECT_ID)[0].pending_command is None
    assert sorted(
        item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)
    ) == sorted(
        [
            "conversation.proposal_created",
            "conversation.proposal_confirmation_started",
            "schedule.updated",
            "conversation.proposal_confirmed",
        ]
    )


@pytest.mark.asyncio
async def test_major_schedule_change_routes_to_existing_approval_without_mutation() -> None:
    app, store = make_app()
    dependency = "tsk_plaster123"
    for index in range(3):
        task_id = f"tsk_schedule_major{index}"
        store.repository(Task).create(
            Task(
                id=task_id,
                project_id=PROJECT_ID,
                title=f"Major downstream {index}",
                status=TaskStatus.PLANNED,
                planned_start=datetime(2026, 8, 22 + index, 8, tzinfo=UTC),
                planned_end=datetime(2026, 8, 22 + index, 17, tzinfo=UTC),
                dependency_ids=[dependency],
            )
        )
        dependency = task_id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:schedule:major"},
        )
        replay = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:schedule:major"},
        )

    assert first.status_code == replay.status_code == 200
    assert first.json()["kind"] == "needs_approval"
    assert [first.json()["mutation_performed"], replay.json()["mutation_performed"]] == [
        True,
        False,
    ]
    assert first.json()["approval_id"] == replay.json()["approval_id"]
    approval = store.repository(Approval).require(PROJECT_ID, first.json()["approval_id"])
    assert approval.action_type.value == "schedule_change"
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start is None
    assert store.repository(ConversationMemory).list(PROJECT_ID) == ()


@pytest.mark.asyncio
async def test_confirmation_rejects_stale_state_and_browser_command_payload() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:stale"},
        )
        task = store.repository(Task).require(PROJECT_ID, "tsk_plaster123")
        store.repository(Task).save(
            task.model_copy(update={"description": "Changed after proposal."}),
            expected_version=task.version,
        )
        path = (
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/"
            f"{proposed.json()['proposal_id']}/confirm"
        )
        stale = await client.post(
            path,
            json={"observed_memory_version": proposed.json()["memory_version"]},
        )
        forged = await client.post(
            path,
            json={
                "observed_memory_version": proposed.json()["memory_version"],
                "command": {"planned_start": "2099-01-01T00:00:00Z"},
            },
        )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_PROPOSAL"
    assert stale.json()["error"]["message"] == (
        "The project changed since I proposed that. I've refreshed the plan."
    )
    assert forged.status_code == 400
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start is None
    assert [item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)] == [
        "conversation.proposal_created"
    ]


def _access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_ace123", subject="ace"),
        project_id=PROJECT_ID,
        role=MemberRole.MANAGER,
    )


def _memory_service(store: InMemoryRepositoryStore) -> ConversationMemoryService:
    return ConversationMemoryService(
        store,
        ConversationEntityResolver(store),
        proposal_signing_key=PROPOSAL_SIGNING_KEY,
    )


@pytest.mark.asyncio
async def test_reserved_confirmation_cannot_be_cancelled() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:reserved"},
        )
        proposal_id = proposed.json()["proposal_id"]
        memory_version = proposed.json()["memory_version"]
        memory = _memory_service(store)
        pending = memory.require_command(_access(), proposal_id, memory_version)
        memory.begin_confirmation(_access(), pending, memory_version)

        cancelled = await client.delete(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}",
            params={"memory_version": memory_version},
        )
        confirmed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}/confirm",
            json={"observed_memory_version": memory_version},
        )

    assert cancelled.status_code == 409
    assert confirmed.status_code == 200
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start == datetime(
        2026, 8, 21, 8, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_stale_state_after_reservation_aborts_and_releases_pending_slot() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:reservation-stale"},
        )
        proposal_id = proposed.json()["proposal_id"]
        memory_version = proposed.json()["memory_version"]
        memory = _memory_service(store)
        pending = memory.require_command(_access(), proposal_id, memory_version)
        memory.begin_confirmation(_access(), pending, memory_version)
        task = store.repository(Task).require(PROJECT_ID, "tsk_plaster123")
        store.repository(Task).save(
            task.model_copy(update={"description": "Changed during confirmation."}),
            expected_version=task.version,
        )

        stale = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}/confirm",
            json={"observed_memory_version": memory_version},
        )
        replacement = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:replacement"},
        )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_PROPOSAL"
    assert replacement.status_code == 200
    assert replacement.json()["proposal_id"] != proposal_id
    claim = store.repository(ConversationProposalClaim).require(PROJECT_ID, proposal_id)
    assert claim.outcome == "stale"
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start is None
    assert "conversation.proposal_confirmation_aborted" in {
        item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)
    }


@pytest.mark.asyncio
async def test_confirmation_recovers_after_domain_commit_before_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store = make_app()
    original_complete = ConversationMemoryService.complete_confirmation
    attempts = 0

    def fail_first_receipt(
        service: ConversationMemoryService,
        access: ProjectAccessContext,
        command: PendingConversationCommand,
        *,
        activity_id: str,
        reply: str,
        confirmation_attempt_id: str,
    ) -> ConversationProposalClaim:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated crash before confirmation receipt")
        return original_complete(
            service,
            access,
            command,
            activity_id=activity_id,
            reply=reply,
            confirmation_attempt_id=confirmation_attempt_id,
        )

    monkeypatch.setattr(
        ConversationMemoryService,
        "complete_confirmation",
        fail_first_receipt,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:crash-recovery"},
        )
        proposal_id = proposed.json()["proposal_id"]
        path = f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}/confirm"
        failed_receipt = await client.post(
            path,
            json={"observed_memory_version": proposed.json()["memory_version"]},
        )
        recovered = await client.post(
            path,
            json={"observed_memory_version": proposed.json()["memory_version"]},
        )

    assert failed_receipt.status_code == 503
    assert recovered.status_code == 200
    assert recovered.json()["mutation_performed"] is False
    assert attempts == 2
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start == datetime(
        2026, 8, 21, 8, tzinfo=UTC
    )
    claim = store.repository(ConversationProposalClaim).require(PROJECT_ID, proposal_id)
    assert claim.outcome == "confirmed"
    assert store.repository(ConversationMemory).list(PROJECT_ID)[0].pending_command is None
    assert (
        len(
            [
                item
                for item in store.repository(ActivityEvent).list(PROJECT_ID)
                if item.action == "schedule.updated"
            ]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_reserved_confirmation_remains_version_bound_and_recovers_after_expiry() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:expired-recovery"},
        )
        proposal_id = proposed.json()["proposal_id"]
        memory_version = proposed.json()["memory_version"]
        memory_service = _memory_service(store)
        pending = memory_service.require_command(_access(), proposal_id, memory_version)
        memory_service.begin_confirmation(_access(), pending, memory_version)
        expired = memory_service.seal_command(
            pending.model_copy(
                update={
                    "created_at": datetime(2026, 8, 13, 8, tzinfo=UTC),
                    "expires_at": datetime(2026, 8, 13, 8, 15, tzinfo=UTC),
                }
            )
        )
        durable_memory = store.repository(ConversationMemory).list(PROJECT_ID)[0]
        store.repository(ConversationMemory).save(
            durable_memory.model_copy(update={"pending_command": expired}),
            expected_version=durable_memory.version,
        )
        path = f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}/confirm"
        wrong_version = await client.post(
            path,
            json={"observed_memory_version": memory_version + 99},
        )
        recovered = await client.post(
            path,
            json={"observed_memory_version": memory_version},
        )

    assert wrong_version.status_code == 409
    assert recovered.status_code == 200
    assert (
        store.repository(ConversationProposalClaim).require(PROJECT_ID, proposal_id).outcome
        == "confirmed"
    )
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start == datetime(
        2026, 8, 21, 8, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_prior_domain_activity_collision_aborts_confirmation_without_wedging() -> None:
    app, store = make_app()
    collision_key = "conversation:collision:shared"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        routine = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "we've got 100 bags of cement now"},
            headers={"Idempotency-Key": collision_key},
        )
        proposed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": collision_key},
        )
        proposal_id = proposed.json()["proposal_id"]
        conflict = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/proposals/{proposal_id}/confirm",
            json={"observed_memory_version": proposed.json()["memory_version"]},
        )
        replacement = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:collision:replacement"},
        )

    assert routine.status_code == 200
    assert proposed.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "STALE_PROPOSAL"
    assert replacement.status_code == 200
    assert (
        store.repository(ConversationProposalClaim).require(PROJECT_ID, proposal_id).outcome
        == "stale"
    )
    assert store.repository(Task).require(PROJECT_ID, "tsk_plaster123").planned_start is None


@pytest.mark.asyncio
async def test_routine_material_action_dispatches_through_typed_service_and_replays() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = [
            await client.post(
                f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
                json={"message": "we've got 100 bags of cement now"},
                headers={"Idempotency-Key": "conversation:cement:100"},
            )
            for _ in range(2)
        ]

    response = responses[-1]
    assert response.status_code == 200
    assert response.json()["kind"] == "done"
    assert [item.json()["mutation_performed"] for item in responses] == [True, False]
    assert responses[0].json()["text"] == "Done. Cement is now recorded at 100 bags."
    assert response.json()["text"] == (
        "That exact request was already processed; no new mutation was applied."
    )
    assert store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity == 100
    activities = store.repository(ActivityEvent).list(PROJECT_ID)
    assert len(activities) == 1
    assert activities[0].action == "material.quantity_set"
    assert response.json()["activity_id"] == activities[0].id


@pytest.mark.asyncio
async def test_purchase_routes_to_existing_durable_approval_workflow_exactly_once() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = [
            await client.post(
                f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
                json={"message": "buy 100 bags of cement"},
                headers={"Idempotency-Key": "conversation:purchase:cement100"},
            )
            for _ in range(2)
        ]

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["kind"] for response in responses] == [
        "needs_approval",
        "needs_approval",
    ]
    assert [response.json()["mutation_performed"] for response in responses] == [True, False]
    assert store.repository(Material).require(
        PROJECT_ID, "mat_cement123"
    ).available_quantity == Decimal("10")
    requests = store.repository(MaterialRequest).list(PROJECT_ID)
    approvals = store.repository(Approval).list(PROJECT_ID)
    runs = store.repository(AgentRun).list(PROJECT_ID)
    assert len(requests) == len(approvals) == len(runs) == 1
    assert requests[0].quantity == Decimal("100")
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert approvals[0].status is ApprovalStatus.PENDING
    assert runs[0].status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert requests[0].approval_id == approvals[0].id
    assert runs[0].trigger_event_id == requests[0].source_event_id
    assert responses[0].json()["approval_id"] == approvals[0].id
    assert responses[0].json()["workflow_run_id"] == runs[0].id

    decision_context = MutationContext(
        project_id=PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id="usr_ace123",
        idempotency_key="conversation:purchase:cement100:approve",
    )
    ApprovalService(store).approve(
        _access(),
        ResolutionCommand(
            project_id=PROJECT_ID,
            approval_id=approvals[0].id,
            expected_version=approvals[0].version,
        ),
        decision_context,
    )
    continuation = ResumeWorkflow(store).handle_approval_granted(
        PROJECT_ID,
        approvals[0].id,
        "usr_ace123",
    )
    assert continuation.run_id == runs[0].id
    assert (
        store.repository(MaterialRequest).require(PROJECT_ID, requests[0].id).status
        is MaterialRequestStatus.APPROVED
    )
    assert (
        store.repository(AgentRun).require(PROJECT_ID, runs[0].id).status is AgentRunStatus.RUNNING
    )
    assert store.repository(AgentRun).require(PROJECT_ID, runs[0].id).pending_actions == []
    outbox = store.repository(OutboxMessage).list(PROJECT_ID)
    assert len(outbox) == 1
    ResumeWorkflow(store).complete_approved_material_workflow(
        PROJECT_ID,
        approvals[0].id,
        "usr_ace123",
    )
    completed = store.repository(AgentRun).require(PROJECT_ID, runs[0].id)
    assert completed.status is AgentRunStatus.COMPLETED
    assert completed.pending_actions == []


@pytest.mark.asyncio
async def test_reused_mutation_key_cannot_apply_a_different_typed_payload() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "we've got 100 bags of cement now"},
            headers={"Idempotency-Key": "conversation:cement:conflict"},
        )
        conflict = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "we've got 90 bags of cement now"},
            headers={"Idempotency-Key": "conversation:cement:conflict"},
        )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert store.repository(Material).require(PROJECT_ID, "mat_cement123").available_quantity == 100
    assert len(store.repository(ActivityEvent).list(PROJECT_ID)) == 1


@pytest.mark.asyncio
async def test_reused_mutation_key_cannot_bind_a_different_raw_request() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "we've got 100 bags of cement now"},
            headers={"Idempotency-Key": "conversation:cement:raw-conflict"},
        )
        conflict = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "cement count confirms one hundred bags"},
            headers={"Idempotency-Key": "conversation:cement:raw-conflict"},
        )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert len(store.repository(ActivityEvent).list(PROJECT_ID)) == 1


@pytest.mark.asyncio
async def test_approval_required_action_never_enters_confirmation_state() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "cancel plastering"},
            headers={"Idempotency-Key": "conversation:cancel:1"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "needs_approval"
    assert response.json()["proposal_id"] is None
    assert (
        store.repository(Task).require(PROJECT_ID, "tsk_plaster123").status
        is TaskStatus.IN_PROGRESS
    )
    assert store.repository(ConversationMemory).list(PROJECT_ID) == ()
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "entity_type", "entity_id", "expected_status", "activity_action"),
    [
        (
            "plastering is complete",
            Task,
            "tsk_plaster123",
            TaskStatus.COMPLETED,
            "task.completed",
        ),
        (
            "electrical is sorted",
            Issue,
            "iss_electrical123",
            IssueStatus.RESOLVED,
            "issue.status_changed",
        ),
    ],
)
async def test_routine_task_and_issue_actions_use_typed_services(
    message: str,
    entity_type: type[Task] | type[Issue],
    entity_id: str,
    expected_status: TaskStatus | IssueStatus,
    activity_action: str,
) -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = [
            await client.post(
                f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
                json={"message": message},
                headers={"Idempotency-Key": f"conversation:{entity_id}:mutation"},
            )
            for _ in range(2)
        ]

    response = responses[-1]
    assert response.status_code == 200
    assert response.json()["kind"] == "done"
    assert [item.json()["mutation_performed"] for item in responses] == [True, False]
    assert store.repository(entity_type).require(PROJECT_ID, entity_id).status == expected_status
    assert [item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)] == [
        activity_action
    ]


@pytest.mark.asyncio
async def test_client_cannot_claim_that_a_confirmation_is_pending() -> None:
    app, _store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "confirm", "has_pending_confirmation": True},
            headers={"Idempotency-Key": "conversation:forged-pending:1"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_follow_up_pronoun_uses_revalidated_recent_task_reference() -> None:
    app, _store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "what's blocking plastering?"},
            headers={"Idempotency-Key": "conversation:blocker:1"},
        )
        response = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "who owns it?"},
            headers={"Idempotency-Key": "conversation:owner:1"},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "Kofi Mensah owns Plastering."
