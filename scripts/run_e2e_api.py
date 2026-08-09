from __future__ import annotations

import hashlib
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import ApiError, install_error_handlers, install_request_id_middleware
from app.api.uploads import router as upload_router
from app.api.v1.router import api_router
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import (
    ActorType,
    ApprovalActionType,
    MemberRole,
    ProjectStatus,
    ReportStatus,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    Approval,
    DailyReport,
    Material,
    Project,
    ReportFact,
    Task,
)
from app.domain.events import ProjectEvent
from app.infrastructure.storage import SignedUpload, StoredObject
from app.repositories.memory import InMemoryRepositoryStore
from app.services.attachments import AttachmentService
from app.services.site_update_intake import SiteUpdateIntakeService
from app.services.site_update_lifecycle import SiteUpdateExecutionStateService


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


class LocalE2EPublisher:
    def __init__(self, store: InMemoryRepositoryStore) -> None:
        self._store = store

    def publish(self, topic, data: bytes, *, attributes=None) -> str:
        del topic, attributes
        event = ProjectEvent.model_validate_json(data)
        access = ProjectAccessContext(
            actor=AuthenticatedUser(user_id=ACTOR_ID, subject="firebase-auth-emulator-user"),
            project_id=event.project_id,
            role=MemberRole.MANAGER,
        )
        state = SiteUpdateExecutionStateService(self._store)
        update_id = str(event.payload["site_update_id"])
        run_id = f"run_{hashlib.sha256(event.event_id.encode('utf-8')).hexdigest()[:32]}"
        state.start_attempt(
            access,
            update_id,
            source_event_id=event.event_id,
            run_id=run_id,
            trace_id=event.event_id,
            attempt=1,
        )
        time.sleep(0.2)
        text = str(event.payload.get("text") or "").lower()
        if "nearly done" in text:
            state.wait_for_clarification(
                access,
                update_id,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=event.event_id,
                attempt=1,
                step="clarification_needed",
            )
        elif "processing error" in text:
            state.fail(
                access,
                update_id,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=event.event_id,
                attempt=1,
                error_code="E2E_PROCESSING_FAILURE",
                error_summary="The site update could not be processed.",
            )
        else:
            state.complete(
                access,
                update_id,
                source_event_id=event.event_id,
                run_id=run_id,
                trace_id=event.event_id,
                attempt=1,
            )
        return f"msg_{event.event_id}"


class SeededProjectService:
    def __init__(self, project: Project) -> None:
        self._project = project

    def require(self, access: ProjectAccessContext) -> Project:
        if access.project_id != self._project.id:
            raise LookupError("project was not found")
        return self._project


class LocalE2ERuntime:
    def __init__(self) -> None:
        self.store = InMemoryRepositoryStore()
        self.storage = LocalE2EStorage()
        self.projects = SeededProjectService(
            Project(
                id=PROJECT_ID,
                name="Ridge House",
                location="East Legon, Accra",
                timezone="Africa/Accra",
                status=ProjectStatus.ACTIVE,
                created_by=ACTOR_ID,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        self._seed()

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
        role = MemberRole.MANAGER
        return ProjectAccessContext(actor=actor, project_id=project_id, role=role)

    def _seed(self) -> None:
        for task in (
            Task(
                id="tsk_blockwork123",
                project_id=PROJECT_ID,
                title="First-floor blockwork",
                status=TaskStatus.COMPLETED,
                completion_percent=Decimal("100"),
                assigned_to="usr_kwame123",
                actual_completion=NOW,
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
                available_quantity=Decimal("10"),
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
    settings = Settings(
        oga_env=RuntimeEnvironment.TEST,
        max_upload_bytes=10 * 1024 * 1024,
    )
    app.state.attachment_service = AttachmentService(runtime.store, runtime.storage, settings)
    app.state.site_update_intake = SiteUpdateIntakeService(
        runtime.store,
        LocalE2EPublisher(runtime.store),
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

    @app.put("/e2e-storage/{token}", status_code=204)
    async def upload(token: str, request: Request) -> Response:
        runtime.storage.put(
            token,
            await request.body(),
            request.headers.get("content-type", ""),
        )
        return Response(status_code=204)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8001, log_level="warning")
