from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.agents.interpreter import MediaEvidence
from app.api.errors import ApiError, install_error_handlers, install_request_id_middleware
from app.api.uploads import router as upload_router
from app.api.v1.router import api_router
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import (
    ActorType,
    ApprovalActionType,
    IssueType,
    MemberRole,
    MemberStatus,
    OutboxStatus,
    ProjectStatus,
    ReportStatus,
    Severity,
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
    Approval,
    DailyReport,
    Material,
    OutboxMessage,
    Project,
    ProjectMember,
    ReportFact,
    Task,
)
from app.domain.events import EventType, ProjectEvent
from app.infrastructure.firestore import create_firestore_client, encode_firestore_value
from app.infrastructure.storage import SignedUpload, StoredObject
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.interfaces import RepositoryStore
from app.repositories.memory import InMemoryRepositoryStore
from app.services.attachments import AttachmentService
from app.services.outbox import OutboxService
from app.services.projects import FirestoreProjectService
from app.services.site_update_intake import SiteUpdateIntakeService
from app.worker import WorkerResult, process_event


PROJECT_ID = "prj_playwright123"
ACTOR_ID = "usr_playwright123"
NOW = datetime(2026, 8, 8, 9, 45, tzinfo=UTC)


class LocalE2EStorage:
    def __init__(self) -> None:
        self._contracts: dict[str, tuple[str, str, int]] = {}
        self._objects: dict[str, tuple[bytes, str]] = {}

    def sign_upload(
        self,
        *,
        object_path: str,
        content_type: str,
        byte_size: int,
        expires_in_seconds: int,
    ) -> SignedUpload:
        token = hashlib.sha256(object_path.encode("utf-8")).hexdigest()[:24]
        self._contracts[token] = (object_path, content_type, byte_size)
        return SignedUpload(
            url=f"http://127.0.0.1:8001/e2e-storage/{token}",
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            required_headers={"Content-Type": content_type},
        )

    def put(self, token: str, body: bytes, content_type: str) -> None:
        object_path, expected_type, expected_size = self._contracts[token]
        if content_type != expected_type or len(body) != expected_size:
            raise ValueError("uploaded object does not match its signed contract")
        self._objects[object_path] = (body, content_type)

    def inspect(self, *, object_path: str, expected_sha256: str, max_bytes: int) -> StoredObject:
        body, content_type = self._objects[object_path]
        if len(body) > max_bytes:
            raise ValueError("uploaded object exceeds the configured size limit")
        digest = hashlib.sha256(body).hexdigest()
        if digest != expected_sha256:
            raise ValueError("uploaded object checksum does not match")
        return StoredObject(
            name=object_path,
            content_type=content_type,
            byte_size=len(body),
            sha256=digest,
            generation="1",
        )

    def sign_read(self, *, object_path: str, expires_in_seconds: int) -> SignedUpload:
        token = hashlib.sha256(object_path.encode("utf-8")).hexdigest()[:24]
        return SignedUpload(
            url=f"http://127.0.0.1:8001/e2e-storage/{token}",
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            required_headers={},
        )

    def read_bytes(
        self,
        *,
        object_path: str,
        expected_sha256: str,
        max_bytes: int,
    ) -> bytes:
        body, _content_type = self._objects[object_path]
        if len(body) > max_bytes:
            raise ValueError("stored object exceeds the model input limit")
        if hashlib.sha256(body).hexdigest() != expected_sha256:
            raise ValueError("stored object checksum changed after verification")
        return body


class DeterministicE2ESiteInterpreter:
    """Deterministic substitute for Gemini at the external model boundary only."""

    voice_transcript = (
        "First-floor blockwork is complete. The electrician did not come today. "
        "We have 10 bags of cement left. Plastering starts tomorrow."
    )

    def __init__(self) -> None:
        self.transcription_calls: list[MediaEvidence] = []
        self.fact_calls: list[tuple[str, tuple[MediaEvidence, ...], str]] = []
        self._audio_input: ContextVar[bool] = ContextVar("e2e_audio_input", default=False)

    async def transcribe_audio(self, media: MediaEvidence) -> str:
        if not media.data:
            raise RuntimeError("the deterministic model received empty audio")
        self.transcription_calls.append(media)
        self._audio_input.set(True)
        return self.voice_transcript

    async def extract_facts(
        self,
        text: str,
        *,
        images: Sequence[MediaEvidence] = (),
        project_context: str = "",
    ) -> ExtractedFactSet:
        self.fact_calls.append((text, tuple(images), project_context))
        if images:
            return ExtractedFactSet(
                tasks=[
                    TaskCompletionFact(
                        task_name="First-floor blockwork",
                        is_completed=True,
                        evidence="The blockwork appears complete in the photo.",
                        confidence="high",
                    )
                ]
            )
        if self._audio_input.get():
            self._audio_input.set(False)
            return ExtractedFactSet(
                next_focus=[
                    NextFocusFact(
                        task_name="First-floor plastering",
                        description="First-floor plastering starts tomorrow.",
                        evidence="Plastering starts tomorrow",
                        confidence="high",
                    )
                ]
            )
        if not text.strip():
            raise RuntimeError("the deterministic model received no interpretable evidence")
        return ExtractedFactSet(
            tasks=[
                TaskCompletionFact(
                    task_name="First-floor blockwork",
                    is_completed=True,
                    evidence="First-floor blockwork is complete",
                    confidence="high",
                )
            ],
            issues=[
                IssueFact(
                    issue_type=IssueType.BLOCKER,
                    task_name="Electrical rough-in",
                    description="The electrician did not come today.",
                    severity=Severity.HIGH,
                    evidence="The electrician did not come today",
                    confidence="high",
                )
            ],
            materials=[
                MaterialQuantityFact(
                    material_name="Cement",
                    quantity=10,
                    unit="bags",
                    evidence="We have 10 bags of cement left",
                    confidence="high",
                )
            ],
            next_focus=[
                NextFocusFact(
                    task_name="First-floor plastering",
                    description="First-floor plastering starts tomorrow.",
                    evidence="Plastering starts tomorrow",
                    confidence="high",
                )
            ],
        )


class LocalE2EEventTransport:
    """In-process delivery adapter around the production event worker."""

    def __init__(
        self,
        store: RepositoryStore,
        storage: LocalE2EStorage,
        interpreter: DeterministicE2ESiteInterpreter,
        settings: Settings,
    ) -> None:
        self._store = store
        self._storage = storage
        self._interpreter = interpreter
        self._settings = settings
        self.worker_results: list[WorkerResult] = []

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        del topic, attributes
        result = process_event(
            data,
            store=self._store,
            settings=self._settings,
            site_interpreter=self._interpreter,
            storage_adapter=self._storage,
        )
        self.worker_results.append(result)
        return f"msg_{result.event_id}"


class SeededProjectService:
    def __init__(self, project: Project) -> None:
        self._project = project

    def require(self, access: ProjectAccessContext) -> Project:
        if access.project_id != self._project.id:
            raise LookupError("project was not found")
        return self._project


class LocalE2ERuntime:
    def __init__(self) -> None:
        self.storage = LocalE2EStorage()
        self.settings = Settings(
            _env_file=None,
            oga_env=RuntimeEnvironment.TEST,
            demo_mode=True,
            max_upload_bytes=10 * 1024 * 1024,
            firestore_emulator_host=os.getenv("FIRESTORE_EMULATOR_HOST"),
            google_cloud_project="oga-foreman-playwright",
        )
        project = Project(
            id=PROJECT_ID,
            name="Ridge House",
            location="East Legon, Accra",
            timezone="Africa/Accra",
            status=ProjectStatus.ACTIVE,
            created_by=ACTOR_ID,
            created_at=NOW,
            updated_at=NOW,
        )
        if self.settings.firestore_emulator_host:
            client = create_firestore_client(self.settings)
            project_reference = client.document("projects", project.id)
            client.recursive_delete(project_reference)
            project_reference.set(encode_firestore_value(project))
            self.store: RepositoryStore = FirestoreRepositoryStore(client)
            self.projects = FirestoreProjectService(client)
        else:
            self.store = InMemoryRepositoryStore()
            self.projects = SeededProjectService(project)
        self.interpreter = DeterministicE2ESiteInterpreter()
        self.event_transport = LocalE2EEventTransport(
            self.store,
            self.storage,
            self.interpreter,
            self.settings,
        )
        self._seed()

    def deliver_pending_continuations(self) -> None:
        outbox = OutboxService(self.store)
        for message in self.store.repository(OutboxMessage).list(PROJECT_ID):
            if message.status not in {OutboxStatus.PENDING, OutboxStatus.FAILED}:
                continue
            if message.message_type not in {
                EventType.APPROVAL_GRANTED.value,
                EventType.APPROVAL_REJECTED.value,
            }:
                continue
            event = ProjectEvent.model_validate(message.payload)
            approval = self.store.repository(Approval).require(
                PROJECT_ID,
                str(event.payload["approval_id"]),
            )
            if approval.action_type is not ApprovalActionType.PURCHASE:
                continue
            outbox.process(
                PROJECT_ID,
                message.id,
                lambda claimed: self.event_transport.publish(
                    None,
                    ProjectEvent.model_validate(claimed.payload).model_dump_json().encode(),
                    attributes={"event_type": claimed.message_type},
                ),
            )

    def authenticate(
        self,
        request: Request,
        *,
        provision: bool = False,
        display_name: str | None = None,
    ) -> AuthenticatedUser:
        del provision, display_name
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) <= len("Bearer "):
            raise ApiError("AUTH_REQUIRED", "Authentication is required.", status_code=401)
        return AuthenticatedUser(
            user_id=ACTOR_ID,
            subject="firebase-auth-emulator-user",
            email="manager@example.test",
        )

    def project_access(
        self,
        request: Request,
        project_id: str,
        permission: ProjectPermission = ProjectPermission.READ,
    ) -> ProjectAccessContext:
        if project_id != PROJECT_ID:
            raise ApiError(
                "AUTH_PROJECT_FORBIDDEN",
                "You do not have access to this project.",
                status_code=403,
            )
        actor = self.authenticate(request)
        role = MemberRole.ADMIN
        return ProjectAccessContext(actor=actor, project_id=project_id, role=role)

    def _seed(self) -> None:
        self.store.repository(ProjectMember).create(
            ProjectMember(
                project_id=PROJECT_ID,
                user_id=ACTOR_ID,
                role=MemberRole.ADMIN,
                status=MemberStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        for task in (
            Task(
                id="tsk_blockwork123",
                project_id=PROJECT_ID,
                title="First-floor blockwork",
                status=TaskStatus.IN_PROGRESS,
                completion_percent=Decimal("80"),
                assigned_to="usr_kwame123",
                created_at=NOW,
                updated_at=NOW,
            ),
            Task(
                id="tsk_electrical123",
                project_id=PROJECT_ID,
                title="Electrical rough-in",
                status=TaskStatus.BLOCKED,
                completion_percent=Decimal("20"),
                assigned_to="usr_kofi123",
                planned_end=NOW,
                description="Electrician was absent in today's update.",
                dependency_ids=["tsk_blockwork123"],
                created_at=NOW,
                updated_at=NOW,
            ),
            Task(
                id="tsk_plastering123",
                project_id=PROJECT_ID,
                title="First-floor plastering",
                status=TaskStatus.PLANNED,
                assigned_to="usr_ama123",
                planned_start=NOW + timedelta(days=1),
                planned_end=NOW + timedelta(days=3),
                dependency_ids=["tsk_blockwork123", "tsk_electrical123"],
                created_at=NOW,
                updated_at=NOW,
            ),
        ):
            self.store.repository(Task).create(task)
        self.store.repository(Material).create(
            Material(
                id="mat_cement123",
                project_id=PROJECT_ID,
                name="Cement",
                normalized_name="cement",
                unit="bags",
                available_quantity=Decimal("50"),
                minimum_required_quantity=Decimal("20"),
                upcoming_requirement_quantity=Decimal("40"),
                updated_at=NOW,
            )
        )
        for device in ("desktop", "mobile"):
            for action in ("approve", "reject", "stale"):
                self.store.repository(Approval).create(
                    Approval(
                        id=f"apr_{action}_{device}123",
                        project_id=PROJECT_ID,
                        action_type=ApprovalActionType.HIGH_IMPACT_CHANGE,
                        proposed_action={
                            "title": f"{action.title()} {device} access sequence",
                            "quantity": "1",
                            "unit": "decision",
                            "needed_by": "Today",
                        },
                        reason="The access sequence affects tomorrow's work.",
                        requested_by="system",
                        requested_at=NOW,
                    )
                )
        for activity in (
            ActivityEvent(
                id="act_progress123",
                project_id=PROJECT_ID,
                actor_type=ActorType.AGENT,
                actor_id="agt_sitecoordinator123",
                action="task.completed",
                entity_type="task",
                entity_id="tsk_blockwork123",
                summary="First-floor blockwork completed.",
                created_at=NOW,
            ),
            ActivityEvent(
                id="act_blocker123",
                project_id=PROJECT_ID,
                actor_type=ActorType.AGENT,
                actor_id="agt_sitecoordinator123",
                action="issue.created",
                entity_type="issue",
                entity_id="iss_electrical123",
                summary="Electrical work is blocked by the absent electrician.",
                created_at=NOW.replace(minute=44),
            ),
            ActivityEvent(
                id="act_material123",
                project_id=PROJECT_ID,
                actor_type=ActorType.AGENT,
                actor_id="agt_sitecoordinator123",
                action="material.requested",
                entity_type="material_request",
                entity_id="mrq_cement123",
                summary="Cement shortage detected and sent for approval.",
                created_at=NOW.replace(minute=43),
            ),
        ):
            self.store.repository(ActivityEvent).create(activity)
        self.store.repository(DailyReport).create(
            DailyReport(
                id="rpt_playwright123",
                project_id=PROJECT_ID,
                report_date=date(2026, 8, 8),
                summary="Blockwork completed; electrical work and cement need attention.",
                completed_work=[
                    ReportFact(summary="First-floor blockwork", source_refs=["su_playwright123"])
                ],
                active_blockers=[
                    ReportFact(summary="Electrician absent", source_refs=["su_playwright123"])
                ],
                material_risks=[
                    ReportFact(summary="Cement stock is low", source_refs=["su_playwright123"])
                ],
                next_focus=[
                    ReportFact(summary="Prepare plastering", source_refs=["su_playwright123"])
                ],
                status=ReportStatus.PUBLISHED,
                created_at=NOW,
                updated_at=NOW,
            )
        )


def create_app() -> FastAPI:
    runtime = LocalE2ERuntime()
    app = FastAPI(title="Oga Foreman local E2E API")
    app.state.auth_runtime = runtime
    app.state.project_access_provider = runtime.project_access
    app.state.attachment_service = AttachmentService(
        runtime.store,
        runtime.storage,
        runtime.settings,
    )
    app.state.site_update_intake = SiteUpdateIntakeService(
        runtime.store,
        runtime.event_transport,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3100"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )
    install_request_id_middleware(app)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(upload_router)

    @app.middleware("http")
    async def deliver_continuations(request: Request, call_next):
        response = await call_next(request)
        if response.status_code < 400:
            runtime.deliver_pending_continuations()
        return response

    @app.put("/e2e-storage/{token}", status_code=204)
    async def upload(token: str, request: Request) -> Response:
        runtime.storage.put(
            token,
            await request.body(),
            request.headers.get("content-type", ""),
        )
        return Response(status_code=204)

    @app.get("/health/live")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8001, log_level="warning")
