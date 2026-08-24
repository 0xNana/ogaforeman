from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from decimal import Decimal
from hashlib import sha256

import httpx
import pytest
from fastapi import FastAPI
from google.cloud import storage as cloud_storage

from app.agents.interpreter import FakeSiteInterpreter, MediaEvidence
from app.api.v1.router import api_router
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.activity import MutationContext
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectPermission,
)
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    ApprovalStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    ProcessingStatus,
    Severity,
    TaskSource,
    TaskStatus,
)
from app.domain.events import EventType, ProjectEvent
from app.domain.facts import (
    ExtractedFactSet,
    IssueFact,
    MaterialQuantityFact,
    NextFocusFact,
    TaskCompletionFact,
)
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    Attachment,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    OutboxMessage,
    ProcessedEvent,
    SiteUpdate,
    Task,
)
from app.infrastructure.firestore import create_firestore_client
from app.infrastructure.storage import GoogleCloudStorageAdapter
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.services.site_update_intake import SiteUpdateIntakeService
from app.worker import process_event, process_event_async
from scripts.reset_demo import reset_demo
from scripts.seed_demo import DEMO_FOREMAN_ID, DEMO_MANAGER_ID, DEMO_PROJECT_ID


UPDATE_TEXT = "First-floor blockwork is done. We have ten bags of cement left."
TRANSCRIPT = "Electrician did not come. Plastering is tomorrow."
VOICE_TRANSCRIPT = (
    "First-floor blockwork is done. Electrician did not come. "
    "We have ten bags of cement left. Plastering is tomorrow."
)
PHOTO_BYTES = b"\xff\xd8\xfffirestore-site-photo"
AUDIO_BYTES = b"OggS-firestore-site-audio"


class CapturingPublisher:
    def __init__(self) -> None:
        self.data: bytes | None = None
        self.calls = 0

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        del topic, attributes
        self.calls += 1
        self.data = data
        return "msg_firestore_worker123"


class StateCapturingInterpreter(FakeSiteInterpreter):
    def __init__(
        self,
        store: FirestoreRepositoryStore,
        responses: dict[str, ExtractedFactSet],
        *,
        transcriptions: dict[str, str],
    ) -> None:
        super().__init__(responses, transcriptions=transcriptions)
        self._store = store
        self.processing_states: list[tuple[ProcessingStatus, AgentRunStatus]] = []

    async def extract_facts(
        self,
        text: str,
        *,
        images: Sequence[MediaEvidence] = (),
        project_context: str = "",
    ) -> ExtractedFactSet:
        update = self._store.repository(SiteUpdate).list(DEMO_PROJECT_ID)[0]
        run = self._store.repository(AgentRun).list(DEMO_PROJECT_ID)[0]
        self.processing_states.append((update.processing_status, run.status))
        return await super().extract_facts(
            text,
            images=images,
            project_context=project_context,
        )


def _access_provider(
    request: object,
    project_id: str,
    permission: ProjectPermission = ProjectPermission.READ,
) -> ProjectAccessContext:
    del request
    assert project_id == DEMO_PROJECT_ID
    assert permission is ProjectPermission.OPERATE
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id=DEMO_FOREMAN_ID, subject="demo-foreman"),
        project_id=DEMO_PROJECT_ID,
        role=MemberRole.FOREMAN,
    )


@pytest.mark.asyncio
@pytest.mark.backing_services
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST") or not os.getenv("STORAGE_EMULATOR_HOST"),
    reason="Firestore and Storage emulators are required for durable worker integration",
)
async def test_site_update_and_approval_resume_survive_backing_service_restarts() -> None:
    emulator_host = os.environ["FIRESTORE_EMULATOR_HOST"]
    settings = Settings(
        _env_file=None,
        oga_env=RuntimeEnvironment.TEST,
        demo_mode=True,
        firestore_emulator_host=emulator_host,
        google_cloud_project="oga-foreman-worker-test",
        firestore_database="(default)",
    )
    client = create_firestore_client(settings)
    reset_demo(client, settings=settings)
    store = FirestoreRepositoryStore(client)
    attachment_repo = store.repository(Attachment)
    photo = attachment_repo.require(DEMO_PROJECT_ID, "att_demo001")
    audio = attachment_repo.require(DEMO_PROJECT_ID, "att_demo002")
    photo = attachment_repo.save(
        photo.model_copy(
            update={
                "byte_size": len(PHOTO_BYTES),
                "sha256": sha256(PHOTO_BYTES).hexdigest(),
                "metadata": {},
            }
        ),
        expected_version=attachment_repo.version_of(DEMO_PROJECT_ID, photo.id),
    )
    audio = attachment_repo.save(
        audio.model_copy(
            update={
                "content_type": "audio/ogg",
                "byte_size": len(AUDIO_BYTES),
                "sha256": sha256(AUDIO_BYTES).hexdigest(),
                "metadata": {},
            }
        ),
        expected_version=attachment_repo.version_of(DEMO_PROJECT_ID, audio.id),
    )
    bucket_name = "oga-foreman-worker-test.appspot.com"
    storage_client = cloud_storage.Client(project=settings.google_cloud_project)
    storage_bucket = storage_client.bucket(bucket_name)
    storage_bucket.blob(photo.object_path).upload_from_string(
        PHOTO_BYTES,
        content_type=photo.content_type,
    )
    storage_bucket.blob(audio.object_path).upload_from_string(
        AUDIO_BYTES,
        content_type=audio.content_type,
    )
    storage = GoogleCloudStorageAdapter(
        bucket_name,
        client=cloud_storage.Client(project=settings.google_cloud_project),
    )
    publisher = CapturingPublisher()
    app = FastAPI()
    app.state.project_access_provider = _access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    payload = {
        "input_type": "mixed",
        "raw_text": UPDATE_TEXT,
        "attachment_ids": ["att_demo001", "att_demo002"],
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_http:
        accepted_response = await client_http.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/site-updates",
            json=payload,
            headers={"Idempotency-Key": "firestore-worker-site-update-123"},
        )
        replay_response = await client_http.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/site-updates",
            json=payload,
            headers={"Idempotency-Key": "firestore-worker-site-update-123"},
        )
    assert accepted_response.status_code == 202
    assert replay_response.json() == accepted_response.json()
    accepted = accepted_response.json()
    assert publisher.data is not None
    assert publisher.calls == 1
    interpreter = FakeSiteInterpreter(
        responses={
            f"{UPDATE_TEXT} {TRANSCRIPT}": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="First-floor blockwork",
                        is_completed=True,
                        evidence="First-floor blockwork is done",
                        confidence="high",
                    )
                ],
                materials=[
                    MaterialQuantityFact(
                        material_name="cement bags",
                        quantity=10,
                        unit="bags",
                        evidence="We have ten bags of cement left",
                        confidence="high",
                    )
                ],
                issues=[
                    IssueFact(
                        issue_type=IssueType.BLOCKER,
                        task_name="Electrical rough-in",
                        description="Electrician did not come",
                        severity=Severity.HIGH,
                        evidence="Electrician did not come",
                        confidence="high",
                    )
                ],
                next_focus=[
                    NextFocusFact(
                        task_name="First-floor plastering",
                        description="Plastering is planned for tomorrow",
                        evidence="Plastering is tomorrow",
                        confidence="high",
                    )
                ],
            )
        },
        transcriptions={"att_demo002": TRANSCRIPT},
    )

    first = await process_event_async(
        publisher.data,
        store=store,
        settings=settings,
        site_interpreter=interpreter,
        storage_adapter=storage,
    )
    replay = await process_event_async(
        publisher.data,
        store=store,
        settings=settings,
        site_interpreter=interpreter,
        storage_adapter=storage,
    )

    restarted = FirestoreRepositoryStore(create_firestore_client(settings))
    task = restarted.repository(Task).require(DEMO_PROJECT_ID, "tsk_blockwork")
    electrical = restarted.repository(Task).require(DEMO_PROJECT_ID, "tsk_electrical")
    follow_ups = [
        persisted_task
        for persisted_task in restarted.repository(Task).list(DEMO_PROJECT_ID)
        if persisted_task.source is TaskSource.SITE_UPDATE
    ]
    material = restarted.repository(Material).require(DEMO_PROJECT_ID, "mat_cement")
    update = restarted.repository(SiteUpdate).require(DEMO_PROJECT_ID, accepted["site_update_id"])
    run = restarted.repository(AgentRun).require(DEMO_PROJECT_ID, accepted["agent_run_id"])
    attachment = restarted.repository(Attachment).require(DEMO_PROJECT_ID, "att_demo001")
    second_attachment = restarted.repository(Attachment).require(DEMO_PROJECT_ID, "att_demo002")
    issues = restarted.repository(Issue).list(DEMO_PROJECT_ID)
    requests = restarted.repository(MaterialRequest).list(DEMO_PROJECT_ID)
    approvals = restarted.repository(Approval).list(DEMO_PROJECT_ID)
    reports = restarted.repository(DailyReport).list(DEMO_PROJECT_ID)
    activities = restarted.repository(ActivityEvent).list(DEMO_PROJECT_ID)

    assert first.result_ref == f"run:{accepted['agent_run_id']}"
    assert replay.status == "duplicate"
    assert interpreter.calls == [f"{UPDATE_TEXT} {TRANSCRIPT}"]
    assert [call.data for call in interpreter.transcription_calls] == [AUDIO_BYTES]
    assert interpreter.image_calls[0][0].data == PHOTO_BYTES
    assert task.status is TaskStatus.COMPLETED
    assert electrical.status is TaskStatus.BLOCKED
    blocker = next(issue for issue in issues if issue.type is IssueType.BLOCKER)
    assert len(follow_ups) == 1
    assert follow_ups[0].source_refs == [update.id, blocker.id, electrical.id]
    assert material.available_quantity == Decimal("10")
    assert update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
    assert update.transcript == TRANSCRIPT
    assert update.transcribed_attachment_ids == [audio.id]
    assert run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert run.step == "approval_required"
    assert run.result_summary is not None
    assert "Electrical rough-in is blocked" in run.result_summary
    assert any(
        "schedule impact on First-floor plastering" in action for action in run.pending_actions
    )
    assert attachment.site_update_id == update.id
    assert second_attachment.site_update_id == update.id
    assert {(issue.type, tuple(issue.task_ids)) for issue in issues} == {
        (IssueType.BLOCKER, ("tsk_electrical",)),
        (IssueType.DELAY_RISK, ("tsk_plastering",)),
    }
    assert len(issues) == 3
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("30")
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert len(approvals) == 1
    assert approvals[0].id == requests[0].approval_id
    assert approvals[0].status is ApprovalStatus.PENDING
    assert len(reports) == 1
    assert reports[0].source_update_ids == [update.id]
    assert len(reports[0].completed_work) == 1
    assert len(reports[0].active_blockers) == 3
    assert len(reports[0].material_risks) == 1
    assert len(reports[0].next_focus) == 1
    assert len(restarted.repository(MaterialLedgerEntry).list(DEMO_PROJECT_ID)) == 1
    assert len(restarted.repository(ProcessedEvent).list(DEMO_PROJECT_ID)) == 1
    assert sum(activity.action == "issue.created" for activity in activities) == 3
    assert {activity.action for activity in activities} >= {
        "attachment.linked",
        "site_update.transcribed",
        "task.completed",
        "task.follow_up_created",
        "issue.created",
        "material.quantity_updated",
        "material.requested",
        "approval.requested",
        "report.projected",
        "site_update.approval_requested",
    }

    approval = approvals[0]
    ApprovalService(restarted).approve(
        ProjectAccessContext(
            actor=AuthenticatedUser(user_id=DEMO_MANAGER_ID, subject="demo-manager"),
            project_id=DEMO_PROJECT_ID,
            role=MemberRole.MANAGER,
        ),
        ResolutionCommand(
            project_id=DEMO_PROJECT_ID,
            approval_id=approval.id,
            expected_version=approval.version,
        ),
        MutationContext(
            project_id=DEMO_PROJECT_ID,
            actor_type=ActorType.USER,
            actor_id=DEMO_MANAGER_ID,
            source_event_id="evt_restart_approval123",
            agent_run_id=run.id,
            idempotency_key="approval:durable-restart:123",
        ),
    )
    continuation_message = next(
        message
        for message in restarted.repository(OutboxMessage).list(DEMO_PROJECT_ID)
        if message.message_type == EventType.APPROVAL_GRANTED.value
    )
    continuation_event = ProjectEvent.model_validate(continuation_message.payload)

    resumed_store = FirestoreRepositoryStore(create_firestore_client(settings))
    resumed = process_event(continuation_event.model_dump_json().encode(), store=resumed_store)
    duplicate_resume = process_event(
        continuation_event.model_dump_json().encode(),
        store=resumed_store,
    )

    final_store = FirestoreRepositoryStore(create_firestore_client(settings))
    final_run = final_store.repository(AgentRun).require(DEMO_PROJECT_ID, run.id)
    final_request = final_store.repository(MaterialRequest).require(
        DEMO_PROJECT_ID,
        requests[0].id,
    )
    final_approval = final_store.repository(Approval).require(DEMO_PROJECT_ID, approval.id)
    final_follow_up = final_store.repository(Task).require(DEMO_PROJECT_ID, follow_ups[0].id)
    final_activities = final_store.repository(ActivityEvent).list(DEMO_PROJECT_ID)
    restarted_storage = GoogleCloudStorageAdapter(
        bucket_name,
        client=cloud_storage.Client(project=settings.google_cloud_project),
    )

    assert resumed.status == "completed"
    assert duplicate_resume.status == "duplicate"
    assert final_run.id == accepted["agent_run_id"]
    assert final_run.status is AgentRunStatus.COMPLETED
    assert final_request.status is MaterialRequestStatus.APPROVED
    assert final_approval.status is ApprovalStatus.APPROVED
    assert final_follow_up == follow_ups[0]
    assert (
        restarted_storage.read_bytes(
            object_path=photo.object_path,
            expected_sha256=photo.sha256,
            max_bytes=settings.max_model_media_bytes,
        )
        == PHOTO_BYTES
    )
    assert (
        restarted_storage.read_bytes(
            object_path=audio.object_path,
            expected_sha256=audio.sha256,
            max_bytes=settings.max_model_media_bytes,
        )
        == AUDIO_BYTES
    )
    assert "approval.approved" in {activity.action for activity in final_activities}
    assert not any(
        activity.action == "material_request.submitted" and activity.entity_id == final_request.id
        for activity in final_activities
    )


@pytest.mark.asyncio
@pytest.mark.backing_services
@pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST") or not os.getenv("STORAGE_EMULATOR_HOST"),
    reason="Firestore and Storage emulators are required for durable worker integration",
)
@pytest.mark.parametrize("decision", ["approved", "rejected"])
async def test_voice_approval_continuation_survives_restart_and_executes_once(
    decision: str,
) -> None:
    emulator_host = os.environ["FIRESTORE_EMULATOR_HOST"]
    settings = Settings(
        _env_file=None,
        oga_env=RuntimeEnvironment.TEST,
        demo_mode=True,
        firestore_emulator_host=emulator_host,
        google_cloud_project="oga-foreman-worker-test",
        firestore_database="(default)",
    )
    initial_client = create_firestore_client(settings)
    reset_demo(initial_client, settings=settings)
    initial_store = FirestoreRepositoryStore(initial_client)
    attachment_repo = initial_store.repository(Attachment)
    audio = attachment_repo.require(DEMO_PROJECT_ID, "att_demo002")
    audio = attachment_repo.save(
        audio.model_copy(
            update={
                "content_type": "audio/ogg",
                "byte_size": len(AUDIO_BYTES),
                "sha256": sha256(AUDIO_BYTES).hexdigest(),
                "metadata": {},
            }
        ),
        expected_version=attachment_repo.version_of(DEMO_PROJECT_ID, audio.id),
    )
    bucket_name = "oga-foreman-worker-test.appspot.com"
    cloud_storage.Client(project=settings.google_cloud_project).bucket(bucket_name).blob(
        audio.object_path
    ).upload_from_string(AUDIO_BYTES, content_type=audio.content_type)
    storage = GoogleCloudStorageAdapter(
        bucket_name,
        client=cloud_storage.Client(project=settings.google_cloud_project),
    )
    publisher = CapturingPublisher()
    app = FastAPI()
    app.state.project_access_provider = _access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(initial_store, publisher)
    app.include_router(api_router, prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    payload = {"input_type": "voice", "attachment_ids": [audio.id]}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_http:
        accepted_response = await client_http.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/site-updates",
            json=payload,
            headers={"Idempotency-Key": f"voice-approval-{decision}-123"},
        )
        replay_response = await client_http.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/site-updates",
            json=payload,
            headers={"Idempotency-Key": f"voice-approval-{decision}-123"},
        )
    assert accepted_response.status_code == 202
    assert replay_response.json() == accepted_response.json()
    assert publisher.calls == 1
    assert publisher.data is not None
    accepted = accepted_response.json()
    facts = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                task_name="First-floor blockwork",
                is_completed=True,
                evidence="First-floor blockwork is done",
                confidence="high",
            )
        ],
        materials=[
            MaterialQuantityFact(
                material_name="cement bags",
                quantity=10,
                unit="bags",
                evidence="We have ten bags of cement left",
                confidence="high",
            )
        ],
        issues=[
            IssueFact(
                issue_type=IssueType.BLOCKER,
                task_name="Electrical rough-in",
                description="Electrician did not come",
                severity=Severity.HIGH,
                evidence="Electrician did not come",
                confidence="high",
            )
        ],
        next_focus=[
            NextFocusFact(
                task_name="First-floor plastering",
                description="Plastering is planned for tomorrow",
                evidence="Plastering is tomorrow",
                confidence="high",
            )
        ],
    )
    interpreter = StateCapturingInterpreter(
        initial_store,
        {VOICE_TRANSCRIPT: facts},
        transcriptions={audio.id: VOICE_TRANSCRIPT},
    )

    first = await process_event_async(
        publisher.data,
        store=initial_store,
        settings=settings,
        site_interpreter=interpreter,
        storage_adapter=storage,
    )
    duplicate_intake = await process_event_async(
        publisher.data,
        store=initial_store,
        settings=settings,
        site_interpreter=interpreter,
        storage_adapter=storage,
    )

    waiting_store = FirestoreRepositoryStore(create_firestore_client(settings))
    update = waiting_store.repository(SiteUpdate).require(
        DEMO_PROJECT_ID, accepted["site_update_id"]
    )
    run = waiting_store.repository(AgentRun).require(DEMO_PROJECT_ID, accepted["agent_run_id"])
    requests = waiting_store.repository(MaterialRequest).list(DEMO_PROJECT_ID)
    approvals = waiting_store.repository(Approval).list(DEMO_PROJECT_ID)
    waiting_activities = waiting_store.repository(ActivityEvent).list(DEMO_PROJECT_ID)
    waiting_outbox = waiting_store.repository(OutboxMessage).list(DEMO_PROJECT_ID)

    assert first.result_ref == f"run:{run.id}"
    assert duplicate_intake.status == "duplicate"
    assert interpreter.processing_states == [(ProcessingStatus.PROCESSING, AgentRunStatus.RUNNING)]
    assert interpreter.calls == [VOICE_TRANSCRIPT]
    assert len(interpreter.transcription_calls) == 1
    assert interpreter.transcription_calls[0].data == AUDIO_BYTES
    assert update.input_type.value == "voice"
    assert update.transcript == VOICE_TRANSCRIPT
    assert update.transcribed_attachment_ids == [audio.id]
    assert update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
    assert run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert run.workflow.value == "daily_site_update"
    assert run.adk_session_id is not None
    assert run.adk_invocation_id == accepted["event_id"]
    assert run.adk_workflow_id == "daily_site_update_workflow"
    paused_adk_identity = (
        run.adk_session_id,
        run.adk_invocation_id,
        run.adk_workflow_id,
    )
    assert run.step == "approval_required"
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("30")
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert len(approvals) == 1
    assert approvals[0].status is ApprovalStatus.PENDING
    assert not any(
        activity.action == "material_request.submitted" for activity in waiting_activities
    )
    assert not any(
        message.message_type == "supplier:submit_material_request" for message in waiting_outbox
    )
    waiting_action_counts = {
        action: sum(
            activity.action == action and activity.agent_run_id == run.id
            for activity in waiting_activities
        )
        for action in {
            "site_update.received",
            "site_update.media_processed",
            "project.context_retrieved",
            "site_update.interpreted",
            "task.completed",
            "blocker.detected",
            "material.quantity_updated",
            "material.risk_detected",
            "material.requested",
            "approval.requested",
            "report.updated",
            "workflow.paused",
        }
    }
    assert set(waiting_action_counts.values()) == {1}
    assert (
        sum(
            activity.action == "schedule.risk_detected" and activity.agent_run_id == run.id
            for activity in waiting_activities
        )
        >= 1
    )
    for activity in waiting_activities:
        if activity.agent_run_id == run.id and (
            activity.action in waiting_action_counts or activity.action == "schedule.risk_detected"
        ):
            assert activity.agent_run_id == run.id
            assert activity.source_event_id is not None
            serialized_metadata = str(activity.metadata).casefold()
            assert VOICE_TRANSCRIPT.casefold() not in serialized_metadata
            assert "chain_of_thought" not in serialized_metadata
            assert "raw_prompt" not in serialized_metadata
    processing_activity = next(
        activity
        for activity in waiting_activities
        if activity.action == "site_update.processing_started"
    )
    waiting_activity = next(
        activity
        for activity in waiting_activities
        if activity.action == "site_update.approval_requested"
    )
    assert processing_activity.agent_run_id == run.id
    assert waiting_activity.agent_run_id == run.id
    assert processing_activity.created_at <= waiting_activity.created_at

    approval = approvals[0]
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=DEMO_MANAGER_ID, subject="demo-manager"),
        project_id=DEMO_PROJECT_ID,
        role=MemberRole.MANAGER,
    )
    notes = (
        "Approved for tomorrow's plastering."
        if decision == "approved"
        else "Use retained stock and defer plastering."
    )
    command = ResolutionCommand(
        project_id=DEMO_PROJECT_ID,
        approval_id=approval.id,
        expected_version=approval.version,
        notes=notes,
    )
    mutation_context = MutationContext(
        project_id=DEMO_PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id=DEMO_MANAGER_ID,
        source_event_id=f"evt_voice_{decision}_decision123",
        agent_run_id=run.id,
        idempotency_key=f"approval:voice:{decision}:restart:123",
    )
    approval_service = ApprovalService(waiting_store)
    if decision == "approved":
        approval_service.approve(access, command, mutation_context)
        continuation_type = EventType.APPROVAL_GRANTED
        expected_approval_status = ApprovalStatus.APPROVED
        expected_decision_request_status = MaterialRequestStatus.APPROVED
    else:
        approval_service.reject(access, command, mutation_context)
        continuation_type = EventType.APPROVAL_REJECTED
        expected_approval_status = ApprovalStatus.REJECTED
        expected_decision_request_status = MaterialRequestStatus.CANCELLED

    decided_store = FirestoreRepositoryStore(create_firestore_client(settings))
    decided_run = decided_store.repository(AgentRun).require(DEMO_PROJECT_ID, run.id)
    decided_request = decided_store.repository(MaterialRequest).require(
        DEMO_PROJECT_ID, requests[0].id
    )
    decided_approval = decided_store.repository(Approval).require(DEMO_PROJECT_ID, approval.id)
    decided_activities = decided_store.repository(ActivityEvent).list(DEMO_PROJECT_ID)
    decided_outbox = decided_store.repository(OutboxMessage).list(DEMO_PROJECT_ID)
    assert decided_run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert decided_request.status is expected_decision_request_status
    assert decided_approval.status is expected_approval_status
    assert decided_approval.resolution_notes == notes
    decision_action = f"approval.{decision}"
    decision_activities = [
        activity
        for activity in decided_activities
        if activity.action == decision_action and activity.entity_id == approval.id
    ]
    assert len(decision_activities) == 1
    assert decision_activities[0].agent_run_id == run.id
    assert decision_activities[0].source_event_id is not None
    assert not any(
        activity.action == "material_request.submitted" for activity in decided_activities
    )
    assert not any(
        message.message_type == "supplier:submit_material_request" for message in decided_outbox
    )
    continuation_message = next(
        message for message in decided_outbox if message.message_type == continuation_type.value
    )
    continuation_event = ProjectEvent.model_validate(continuation_message.payload)

    resumed_store = FirestoreRepositoryStore(create_firestore_client(settings))
    resumed = process_event(continuation_event.model_dump_json().encode(), store=resumed_store)
    duplicate_resume = process_event(
        continuation_event.model_dump_json().encode(), store=resumed_store
    )

    final_store = FirestoreRepositoryStore(create_firestore_client(settings))
    final_run = final_store.repository(AgentRun).require(DEMO_PROJECT_ID, run.id)
    final_request = final_store.repository(MaterialRequest).require(DEMO_PROJECT_ID, requests[0].id)
    final_approval = final_store.repository(Approval).require(DEMO_PROJECT_ID, approval.id)
    final_update = final_store.repository(SiteUpdate).require(DEMO_PROJECT_ID, update.id)
    final_attachment = final_store.repository(Attachment).require(DEMO_PROJECT_ID, audio.id)
    final_activities = final_store.repository(ActivityEvent).list(DEMO_PROJECT_ID)
    final_outbox = final_store.repository(OutboxMessage).list(DEMO_PROJECT_ID)
    logical_runs = [
        candidate
        for candidate in final_store.repository(AgentRun).list(DEMO_PROJECT_ID)
        if candidate.trigger_event_id == accepted["event_id"]
    ]

    assert resumed.status == "completed"
    assert resumed.result_ref == f"run:{run.id}"
    assert duplicate_resume.status == "duplicate"
    assert logical_runs == [final_run]
    assert final_run.id == accepted["agent_run_id"]
    assert final_update.transcript == VOICE_TRANSCRIPT
    assert final_attachment.site_update_id == final_update.id
    restarted_storage = GoogleCloudStorageAdapter(
        bucket_name,
        client=cloud_storage.Client(project=settings.google_cloud_project),
    )
    assert (
        restarted_storage.read_bytes(
            object_path=final_attachment.object_path,
            expected_sha256=final_attachment.sha256,
            max_bytes=settings.max_model_media_bytes,
        )
        == AUDIO_BYTES
    )

    if decision == "approved":
        assert final_run.status is AgentRunStatus.COMPLETED
        assert final_run.step == "completed"
        assert (
            final_run.adk_session_id,
            final_run.adk_invocation_id,
            final_run.adk_workflow_id,
        ) == paused_adk_identity
        assert final_update.processing_status is ProcessingStatus.COMPLETED
        assert final_update.processed_at is not None
        assert final_run.updated_at >= run.updated_at
        assert final_run.completed_at is not None
        assert final_request.status is MaterialRequestStatus.APPROVED
        assert final_approval.status is ApprovalStatus.APPROVED
        assert sum(activity.action == "agent_run.resumed" for activity in final_activities) == 1
        assert (
            next(
                activity for activity in final_activities if activity.action == "agent_run.resumed"
            ).actor_type
            is ActorType.SYSTEM
        )
        assert not any(
            activity.action == "material_request.submitted"
            and activity.entity_id == final_request.id
            for activity in final_activities
        )
        assert sum(activity.action == "agent_run.completed" for activity in final_activities) == 1
        assert sum(activity.action == "workflow.resumed" for activity in final_activities) == 1
        assert (
            sum(
                activity.action == "site_update.processing_resumed" for activity in final_activities
            )
            == 1
        )
        assert (
            sum(
                activity.action == "site_update.processing_completed"
                for activity in final_activities
            )
            == 1
        )
        assert (
            sum(activity.action == "external_action.executed" for activity in final_activities) == 1
        )
        assert sum(activity.action == "workflow.completed" for activity in final_activities) == 1
        assert not any(
            message.message_type == "supplier:submit_material_request" for message in final_outbox
        )
    else:
        assert final_run.status is AgentRunStatus.FAILED
        assert final_run.step == "approval_rejected"
        assert final_run.updated_at >= run.updated_at
        assert final_run.error_code == "APPROVAL_REJECTED"
        assert final_request.status is MaterialRequestStatus.CANCELLED
        assert final_approval.status is ApprovalStatus.REJECTED
        assert final_approval.resolution_notes == notes
        assert sum(activity.action == "agent_run.rejected" for activity in final_activities) == 1
        rejected_terminal = [
            activity
            for activity in final_activities
            if activity.action == "workflow.completed" and activity.agent_run_id == run.id
        ]
        assert len(rejected_terminal) == 1
        assert rejected_terminal[0].metadata["outcome"] == "rejected"
        assert rejected_terminal[0].metadata["error_code"] == "APPROVAL_REJECTED"
        assert (
            next(
                activity for activity in final_activities if activity.action == "agent_run.rejected"
            ).actor_type
            is ActorType.SYSTEM
        )
        assert not any(
            activity.action
            in {
                "agent_run.resumed",
                "workflow.resumed",
                "material_request.submitted",
                "external_action.executed",
            }
            for activity in final_activities
        )
        assert not any(
            message.message_type == "supplier:submit_material_request" for message in final_outbox
        )
