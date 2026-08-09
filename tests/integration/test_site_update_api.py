from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.agents.interpreter import FakeSiteInterpreter, MediaEvidence
from app.api.errors import install_error_handlers
from app.api.v1.router import api_router
from app.config.settings import Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import (
    AgentRunStatus,
    ApprovalStatus,
    AttachmentUploadStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    ProcessingStatus,
    Severity,
    TaskSource,
    TaskStatus,
)
from app.domain.facts import (
    ExtractedFactSet,
    IssueFact,
    MaterialQuantityFact,
    NextFocusFact,
    TaskCompletionFact,
)
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
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.site_update_intake import SiteUpdateAttachmentError, SiteUpdateIntakeService
from app.worker import process_event


class WorkerPublisher:
    def __init__(
        self,
        store: InMemoryRepositoryStore,
        interpreter: FakeSiteInterpreter | None = None,
        storage: object | None = None,
    ) -> None:
        self._store = store
        self._interpreter = interpreter or FakeSiteInterpreter()
        self._storage = storage
        self.published_event_ids: list[str] = []

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: dict[str, str] | None = None,
    ) -> str:
        del topic, attributes
        result = process_event(
            data,
            store=self._store,
            settings=Settings(_env_file=None),
            site_interpreter=self._interpreter,
            storage_adapter=self._storage,
        )
        self.published_event_ids.append(result.event_id)
        return f"msg_{result.event_id}"


class MemoryMediaStorage:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.reads: list[str] = []

    def read_bytes(
        self,
        *,
        object_path: str,
        expected_sha256: str,
        max_bytes: int,
    ) -> bytes:
        value = self.objects[object_path]
        assert len(value) <= max_bytes
        assert sha256(value).hexdigest() == expected_sha256
        self.reads.append(object_path)
        return value


class RecordingMultimodalInterpreter:
    def __init__(
        self,
        *,
        transcript: str = "",
        facts: ExtractedFactSet | None = None,
        transcription_failures: int = 0,
        fact_failures: int = 0,
    ) -> None:
        self.transcript = transcript
        self.facts = facts or ExtractedFactSet()
        self.transcription_failures = transcription_failures
        self.fact_failures = fact_failures
        self.transcription_calls: list[MediaEvidence] = []
        self.fact_calls: list[tuple[str, tuple[MediaEvidence, ...], str]] = []

    async def transcribe_audio(self, media: MediaEvidence) -> str:
        self.transcription_calls.append(media)
        if len(self.transcription_calls) <= self.transcription_failures:
            raise TimeoutError("transcription temporarily unavailable")
        return self.transcript

    async def extract_facts(
        self,
        text: str,
        *,
        images: Sequence[MediaEvidence] = (),
        project_context: str = "",
    ) -> ExtractedFactSet:
        self.fact_calls.append((text, tuple(images), project_context))
        if len(self.fact_calls) <= self.fact_failures:
            raise TimeoutError("fact extraction temporarily unavailable")
        return self.facts


def access_provider(
    request: object,
    project_id: str,
    permission: ProjectPermission = ProjectPermission.READ,
) -> ProjectAccessContext:
    del request
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman123", subject="sub_foreman123"),
        project_id="prj_readiness123",
        role=MemberRole.FOREMAN,
    )
    if project_id != access.project_id:
        raise ValueError("cross-project access")
    assert permission in {ProjectPermission.READ, ProjectPermission.OPERATE}
    return access


@pytest.mark.asyncio
async def test_site_update_is_persisted_audited_published_and_started_once() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_readiness123",
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    publisher = WorkerPublisher(store)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.auth_runtime = SimpleNamespace(store=store)
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/projects/prj_readiness123/site-updates",
            json={"raw_text": "Blockwork is complete."},
            headers={"Idempotency-Key": "readiness:site-update:123"},
        )
        replay = await client.post(
            "/api/v1/projects/prj_readiness123/site-updates",
            json={"raw_text": "Blockwork is complete."},
            headers={"Idempotency-Key": "readiness:site-update:123"},
        )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == first.json()
    response = first.json()
    assert response["status"] == "queued"
    assert response["status_url"].endswith(response["agent_run_id"])
    assert len(store.repository(SiteUpdate).list("prj_readiness123")) == 1
    activities = store.repository(ActivityEvent).list("prj_readiness123")
    assert {activity.action for activity in activities} == {
        "report.projected",
        "site_update.received",
        "site_update.processing_started",
        "site_update.processing_completed",
    }
    assert len(store.repository(OutboxMessage).list("prj_readiness123")) == 1
    run = store.repository(AgentRun).require(
        "prj_readiness123",
        response["agent_run_id"],
    )
    assert run.status is AgentRunStatus.COMPLETED
    assert publisher.published_event_ids == [response["event_id"]]


@pytest.mark.asyncio
async def test_mixed_api_update_persists_complete_daily_site_update_projection() -> None:
    project_id = "prj_readiness123"
    update_text = "First-floor blockwork is done. We have ten bags of cement left."
    transcript = "Electrician did not come. Plastering is tomorrow."
    interpreter = FakeSiteInterpreter(
        responses={
            f"{update_text} {transcript}": ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="First-floor blockwork",
                        is_completed=True,
                        evidence="First-floor blockwork is done",
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
                materials=[
                    MaterialQuantityFact(
                        material_name="cement bags",
                        quantity=10,
                        unit="bags",
                        evidence="We have ten bags of cement left",
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
        }
    )
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    for task in (
        Task(
            id="tsk_blockwork123",
            project_id=project_id,
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        ),
        Task(
            id="tsk_electrical123",
            project_id=project_id,
            title="Electrical rough-in",
            status=TaskStatus.PLANNED,
            assigned_to="usr_electrician123",
            dependency_ids=["tsk_blockwork123"],
        ),
        Task(
            id="tsk_plastering123",
            project_id=project_id,
            title="First-floor plastering",
            status=TaskStatus.PLANNED,
            dependency_ids=["tsk_blockwork123", "tsk_electrical123"],
        ),
    ):
        store.repository(Task).create(task)
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=project_id,
            name="Cement Bags",
            normalized_name="cement bags",
            aliases=["cement"],
            unit="bags",
            available_quantity=Decimal("25"),
            minimum_required_quantity=Decimal("20"),
            upcoming_requirement_quantity=Decimal("40"),
            estimated_unit_cost=Decimal("12.50"),
        )
    )
    progress_photo = b"\xff\xd8\xffsite progress photo"
    progress_photo_path = f"projects/{project_id}/attachments/att_progress123"
    store.repository(Attachment).create(
        Attachment(
            id="att_progress123",
            project_id=project_id,
            object_path=progress_photo_path,
            content_type="image/jpeg",
            byte_size=len(progress_photo),
            sha256=sha256(progress_photo).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    publisher = WorkerPublisher(
        store,
        interpreter,
        MemoryMediaStorage({progress_photo_path: progress_photo}),
    )
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.auth_runtime = SimpleNamespace(store=store)
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")

    request = {
        "input_type": "mixed",
        "raw_text": update_text,
        "transcript": transcript,
        "attachment_ids": ["att_progress123"],
        "occurred_at": datetime(2026, 8, 8, 9, 30, tzinfo=UTC).isoformat(),
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json=request,
            headers={"Idempotency-Key": "canonical:mixed:update:123"},
        )
        replay = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json=request,
            headers={"Idempotency-Key": "canonical:mixed:update:123"},
        )
        run_response = await client.get(
            f"/api/v1/projects/{project_id}/agent-runs/{first.json()['agent_run_id']}"
        )

    assert first.status_code == 202
    assert replay.json() == first.json()
    accepted = first.json()
    update = store.repository(SiteUpdate).require(project_id, accepted["site_update_id"])
    run = store.repository(AgentRun).require(project_id, accepted["agent_run_id"])
    attachment = store.repository(Attachment).require(project_id, "att_progress123")
    task = store.repository(Task).require(project_id, "tsk_blockwork123")
    tasks = store.repository(Task).list(project_id)
    material = store.repository(Material).require(project_id, "mat_cement123")
    issues = store.repository(Issue).list(project_id)
    requests = store.repository(MaterialRequest).list(project_id)
    approvals = store.repository(Approval).list(project_id)
    reports = store.repository(DailyReport).list(project_id)
    activities = store.repository(ActivityEvent).list(project_id)

    assert interpreter.calls == [f"{update_text} {transcript}"]
    assert publisher.published_event_ids == [accepted["event_id"]]
    assert update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
    assert run.status is AgentRunStatus.WAITING_FOR_APPROVAL
    assert run.step == "approval_required"
    assert run_response.status_code == 200
    assert "First-floor plastering" in run_response.json()["result_summary"]
    assert any(
        "schedule impact" in action.casefold() for action in run_response.json()["pending_actions"]
    )
    assert attachment.site_update_id == update.id
    assert task.status is TaskStatus.COMPLETED
    assert material.available_quantity == Decimal("10")
    assert {(issue.type, tuple(issue.task_ids)) for issue in issues} == {
        (IssueType.BLOCKER, ("tsk_electrical123",)),
        (IssueType.DELAY_RISK, ("tsk_plastering123",)),
    }
    assert len(issues) == 3
    blocker = next(issue for issue in issues if issue.type is IssueType.BLOCKER)
    follow_ups = [task for task in tasks if task.source is TaskSource.SITE_UPDATE]
    assert len(follow_ups) == 1
    assert follow_ups[0].assigned_to == "usr_electrician123"
    assert follow_ups[0].source_refs == [
        update.id,
        blocker.id,
        "tsk_electrical123",
    ]
    assert len(requests) == 1
    assert requests[0].quantity == Decimal("30")
    assert requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
    assert requests[0].approval_id == approvals[0].id
    assert len(approvals) == 1
    assert approvals[0].status is ApprovalStatus.PENDING
    assert len(reports) == 1
    assert reports[0].source_update_ids == [update.id]
    assert len(reports[0].completed_work) == 1
    assert len(reports[0].active_blockers) == 3
    assert len(reports[0].material_risks) == 1
    assert len(reports[0].next_focus) == 1
    assert {activity.action for activity in activities} >= {
        "attachment.linked",
        "task.completed",
        "task.follow_up_created",
        "issue.created",
        "material.quantity_updated",
        "material.requested",
        "approval.requested",
        "report.projected",
        "site_update.approval_requested",
    }


@pytest.mark.asyncio
async def test_voice_attachment_is_transcribed_persisted_and_replayed_once() -> None:
    project_id = "prj_readiness123"
    audio = b"\x1aE\xdf\xa3voice update bytes"
    object_path = f"projects/{project_id}/attachments/att_voice123"
    transcript = "Ground-floor blockwork is complete."
    interpreter = RecordingMultimodalInterpreter(
        transcript=transcript,
        facts=ExtractedFactSet(
            tasks=[
                TaskCompletionFact(
                    task_name="Ground-floor blockwork",
                    is_completed=True,
                    evidence=transcript,
                    confidence="high",
                )
            ]
        ),
    )
    storage = MemoryMediaStorage({object_path: audio})
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_groundblockwork123",
            project_id=project_id,
            title="Ground-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        )
    )
    store.repository(Attachment).create(
        Attachment(
            id="att_voice123",
            project_id=project_id,
            object_path=object_path,
            content_type="audio/webm",
            byte_size=len(audio),
            sha256=sha256(audio).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    publisher = WorkerPublisher(store, interpreter, storage)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "voice", "attachment_ids": ["att_voice123"]},
            headers={"Idempotency-Key": "voice:site-update:123"},
        )
        replay = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "voice", "attachment_ids": ["att_voice123"]},
            headers={"Idempotency-Key": "voice:site-update:123"},
        )

    assert first.status_code == 202
    assert replay.json() == first.json()
    accepted = first.json()
    update = store.repository(SiteUpdate).require(project_id, accepted["site_update_id"])
    attachment = store.repository(Attachment).require(project_id, "att_voice123")
    assert update.transcript == transcript
    assert update.transcribed_attachment_ids == ["att_voice123"]
    assert attachment.site_update_id == update.id
    assert len(store.repository(SiteUpdate).list(project_id)) == 1
    assert len(interpreter.transcription_calls) == 1
    assert interpreter.transcription_calls[0].attachment_id == "att_voice123"
    assert interpreter.transcription_calls[0].content_type == "audio/webm"
    assert interpreter.transcription_calls[0].data == audio
    assert interpreter.fact_calls[0][0] == transcript
    assert storage.reads == [object_path]
    assert (
        store.repository(Task).require(project_id, "tsk_groundblockwork123").status
        is TaskStatus.COMPLETED
    )
    assert [
        activity.action
        for activity in store.repository(ActivityEvent).list(project_id)
        if activity.action == "site_update.transcribed"
    ] == ["site_update.transcribed"]


@pytest.mark.asyncio
async def test_photo_attachment_reaches_interpreter_with_context_and_ambiguous_work_waits() -> None:
    project_id = "prj_readiness123"
    photo = b"\x89PNG\r\n\x1a\nsite photo bytes"
    object_path = f"projects/{project_id}/attachments/att_photo123"
    interpreter = RecordingMultimodalInterpreter(
        facts=ExtractedFactSet(
            tasks=[
                TaskCompletionFact(
                    task_name="Ground-floor blockwork",
                    is_completed=True,
                    evidence="The visible wall appears substantially built.",
                    confidence="high",
                )
            ]
        )
    )
    storage = MemoryMediaStorage({object_path: photo})
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_groundblockwork123",
            project_id=project_id,
            title="Ground-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("80"),
        )
    )
    store.repository(Attachment).create(
        Attachment(
            id="att_photo123",
            project_id=project_id,
            object_path=object_path,
            content_type="image/png",
            byte_size=len(photo),
            sha256=sha256(photo).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    publisher = WorkerPublisher(store, interpreter, storage)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    app.include_router(api_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "photo", "attachment_ids": ["att_photo123"]},
            headers={"Idempotency-Key": "photo:site-update:123"},
        )

    assert response.status_code == 202
    accepted = response.json()
    update = store.repository(SiteUpdate).require(project_id, accepted["site_update_id"])
    run = store.repository(AgentRun).require(project_id, accepted["agent_run_id"])
    attachment = store.repository(Attachment).require(project_id, "att_photo123")
    text, images, context = interpreter.fact_calls[0]
    assert text == ""
    assert len(images) == 1
    assert images[0].attachment_id == "att_photo123"
    assert images[0].content_type == "image/png"
    assert images[0].data == photo
    assert "Ground-floor blockwork" in context
    assert update.processing_status is ProcessingStatus.WAITING_FOR_CLARIFICATION
    assert run.status is AgentRunStatus.WAITING_FOR_CLARIFICATION
    assert attachment.site_update_id == update.id
    assert (
        store.repository(Task).require(project_id, "tsk_groundblockwork123").status
        is TaskStatus.IN_PROGRESS
    )


@pytest.mark.asyncio
async def test_failed_voice_transcription_recovers_on_same_persisted_site_update() -> None:
    project_id = "prj_readiness123"
    audio = b"\x1aE\xdf\xa3retry voice bytes"
    object_path = f"projects/{project_id}/attachments/att_retryvoice123"
    transcript = "The electrician did not come today."
    interpreter = RecordingMultimodalInterpreter(
        transcript=transcript,
        transcription_failures=1,
    )
    storage = MemoryMediaStorage({object_path: audio})
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Attachment).create(
        Attachment(
            id="att_retryvoice123",
            project_id=project_id,
            object_path=object_path,
            content_type="audio/webm",
            byte_size=len(audio),
            sha256=sha256(audio).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    publisher = WorkerPublisher(store, interpreter, storage)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "voice", "attachment_ids": ["att_retryvoice123"]},
            headers={"Idempotency-Key": "voice:retry:123"},
        )
        update_after_failure = store.repository(SiteUpdate).list(project_id)[0]
        recovered = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "voice", "attachment_ids": ["att_retryvoice123"]},
            headers={"Idempotency-Key": "voice:retry:123"},
        )

    assert failed.status_code == 503
    assert update_after_failure.processing_status is ProcessingStatus.FAILED
    assert recovered.status_code == 202
    assert len(store.repository(SiteUpdate).list(project_id)) == 1
    update = store.repository(SiteUpdate).list(project_id)[0]
    run = store.repository(AgentRun).list(project_id)[0]
    assert update.id == update_after_failure.id
    assert update.transcript == transcript
    assert update.processing_status is ProcessingStatus.COMPLETED
    assert run.status is AgentRunStatus.COMPLETED
    assert run.attempt == 2
    assert len(interpreter.transcription_calls) == 2


@pytest.mark.asyncio
async def test_voice_retry_reuses_persisted_transcript_after_later_model_failure() -> None:
    project_id = "prj_readiness123"
    audio = b"\x1aE\xdf\xa3persisted transcript bytes"
    object_path = f"projects/{project_id}/attachments/att_persistedvoice123"
    transcript = "Ground-floor blockwork is complete."
    interpreter = RecordingMultimodalInterpreter(
        transcript=transcript,
        fact_failures=1,
    )
    storage = MemoryMediaStorage({object_path: audio})
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=project_id,
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Attachment).create(
        Attachment(
            id="att_persistedvoice123",
            project_id=project_id,
            object_path=object_path,
            content_type="audio/webm",
            byte_size=len(audio),
            sha256=sha256(audio).hexdigest(),
            upload_status=AttachmentUploadStatus.VERIFIED,
        )
    )
    publisher = WorkerPublisher(store, interpreter, storage)
    app = FastAPI()
    app.state.project_access_provider = access_provider
    app.state.site_update_intake = SiteUpdateIntakeService(store, publisher)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "voice", "attachment_ids": ["att_persistedvoice123"]},
            headers={"Idempotency-Key": "voice:persisted-retry:123"},
        )
        persisted_after_failure = store.repository(SiteUpdate).list(project_id)[0]
        recovered = await client.post(
            f"/api/v1/projects/{project_id}/site-updates",
            json={"input_type": "voice", "attachment_ids": ["att_persistedvoice123"]},
            headers={"Idempotency-Key": "voice:persisted-retry:123"},
        )

    assert failed.status_code == 503
    assert persisted_after_failure.transcript == transcript
    assert persisted_after_failure.processing_status is ProcessingStatus.FAILED
    assert recovered.status_code == 202
    assert len(store.repository(SiteUpdate).list(project_id)) == 1
    assert (
        store.repository(SiteUpdate).list(project_id)[0].processing_status
        is ProcessingStatus.COMPLETED
    )
    assert len(interpreter.transcription_calls) == 1
    assert len(interpreter.fact_calls) == 2
    assert storage.reads == [object_path]
    assert (
        len(
            [
                activity
                for activity in store.repository(ActivityEvent).list(project_id)
                if activity.action == "site_update.transcribed"
            ]
        )
        == 1
    )


def test_site_update_rejects_unverified_photo_before_persisting_intake() -> None:
    project_id = "prj_readiness123"
    store = InMemoryRepositoryStore()
    attachment = Attachment(
        id="att_unverified123",
        project_id=project_id,
        object_path=f"projects/{project_id}/attachments/att_unverified123",
        content_type="image/jpeg",
        byte_size=512,
        sha256="b" * 64,
        upload_status=AttachmentUploadStatus.INITIATED,
    )
    store.repository(Attachment).create(attachment)
    publisher = WorkerPublisher(store)

    with pytest.raises(SiteUpdateAttachmentError, match="must be verified"):
        SiteUpdateIntakeService(store, publisher).submit(
            access_provider(object(), project_id, ProjectPermission.OPERATE),
            idempotency_key="unverified:photo:123",
            raw_text="Progress photo attached.",
            attachment_ids=[attachment.id],
        )

    assert publisher.published_event_ids == []
    assert store.repository(SiteUpdate).list(project_id) == ()
    assert store.repository(Attachment).require(project_id, attachment.id).site_update_id is None
    assert store.repository(ActivityEvent).list(project_id) == ()
