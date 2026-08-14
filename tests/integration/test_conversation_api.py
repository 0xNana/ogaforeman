from decimal import Decimal
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.agents.conversation import FakeIntentClassifier
from app.api.errors import install_error_handlers
from app.api.v1.router import api_router
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import IntentDecision, IntentType, PendingConversationCommand
from app.domain.conversation import IssueOperation, MaterialOperation, TaskOperation
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
    ConversationProposalClaim,
    Issue,
    Material,
    Project,
    ProjectMember,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_action_composer import (
    IssueActionInterpretation,
    MaterialActionInterpretation,
    TaskActionInterpretation,
    ScheduleActionInterpretation,
)
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_schedule_operations import ConversationScheduleService
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService


PROJECT_ID = "prj_conversation123"
PROPOSAL_SIGNING_KEY = b"conversation-api-envelope-signing-key-32-bytes"


class FakeActionInterpreter:
    async def interpret(
        self, message: str, *, context: object
    ) -> (
        MaterialActionInterpretation
        | TaskActionInterpretation
        | IssueActionInterpretation
        | ScheduleActionInterpretation
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
        raise AssertionError(f"unexpected action message: {message}")


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
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/conversations/messages",
            json={"message": "move plastering to Friday"},
            headers={"Idempotency-Key": "conversation:move:1"},
        )
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
