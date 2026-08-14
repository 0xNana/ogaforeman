from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.agents.conversation import FakeIntentClassifier
from app.api.errors import install_error_handlers
from app.api.v1.router import api_router
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import IntentDecision, IntentType
from app.domain.enums import (
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MemberRole,
    MemberStatus,
    ProjectStatus,
    Severity,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    ConversationMemory,
    Issue,
    Material,
    Project,
    ProjectMember,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore


PROJECT_ID = "prj_conversation123"


class Projects:
    def __init__(self, project: Project) -> None:
        self.project = project

    def require(self, access: ProjectAccessContext) -> Project:
        assert access.project_id == self.project.id
        return self.project


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
            status=TaskStatus.PLANNED,
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
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app, store


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
async def test_project_change_is_proposed_audited_and_replay_safe() -> None:
    app, store = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(2):
            response = await client.post(
                f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
                json={"message": "move plastering to Friday"},
                headers={"Idempotency-Key": "conversation:move:1"},
            )

    assert response.status_code == 200
    assert response.json()["kind"] == "proposed_change"
    assert response.json()["mutation_performed"] is False
    assert {item.action for item in store.repository(ActivityEvent).list(PROJECT_ID)} == {
        "conversation.mutation_requested",
        "conversation.confirmation_requested",
    }
    assert len(store.repository(ConversationMemory).list(PROJECT_ID)) == 1
    memory = store.repository(ConversationMemory).list(PROJECT_ID)[0]
    assert memory.pending_confirmation is None


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
