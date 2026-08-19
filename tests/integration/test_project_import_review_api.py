from __future__ import annotations

import asyncio
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_error_handlers, install_request_id_middleware
from app.api.v1.router import api_router
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import MemberRole
from app.domain.import_records import MaterialRequirement, ProjectImportRecord, ProjectPhase
from app.domain.models import Material, Task
from app.domain.project_import import (
    ImportConflict,
    ProjectImportDraft,
    ProjectImportStatus,
    SourceType,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.project_import_review import (
    ProjectImportReviewService,
    ProjectImportReviewStateError,
)


PROJECT_ID = "prj_importapi123"
ACTOR_ID = "usr_admin123"


class FixedDraftExtractor:
    async def extract(
        self,
        *,
        project_id: str,
        import_id: str,
        source_id: str,
        source_text: str,
    ) -> ProjectImportDraft:
        assert project_id == PROJECT_ID
        assert "Foundation" in source_text
        return ProjectImportDraft(
            id=import_id,
            project_id=project_id,
            source_id=source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            project={"name": "Ridge House"},
            phases=[{"temp_id": "tmp_phase_foundation", "name": "Foundation", "sequence": 1}],
            tasks=[
                {
                    "temp_id": "tmp_task_excavation",
                    "name": "Excavation",
                    "phase_temp_id": "tmp_phase_foundation",
                },
                {
                    "temp_id": "tmp_task_foundation",
                    "name": "Foundation",
                    "phase_temp_id": "tmp_phase_foundation",
                },
            ],
            dependencies=[
                {
                    "predecessor_temp_id": "tmp_task_excavation",
                    "successor_temp_id": "tmp_task_foundation",
                }
            ],
            materials=[
                {
                    "temp_id": "tmp_material_cement",
                    "name": "Cement",
                    "canonical_unit": "bags",
                    "initial_on_hand_quantity": Decimal("20"),
                }
            ],
            material_requirements=[
                {
                    "task_temp_id": "tmp_task_foundation",
                    "material_temp_id": "tmp_material_cement",
                    "required_quantity": Decimal("100"),
                    "unit": "bags",
                }
            ],
            warnings=[{"code": "MISSING_DATE", "message": "Foundation has no planned finish."}],
            unresolved_references=["Foundation foreman"],
        )


class ConflictDraftExtractor(FixedDraftExtractor):
    async def extract(self, **kwargs) -> ProjectImportDraft:
        draft = await super().extract(**kwargs)
        return draft.model_copy(
            update={
                "conflicts": [
                    ImportConflict(
                        code="EXISTING_TASK_POSSIBLE_MATCH",
                        message="Review the possible existing task match.",
                    )
                ]
            }
        )


class InvalidReferencesDraftExtractor(FixedDraftExtractor):
    async def extract(self, **kwargs) -> ProjectImportDraft:
        draft = await super().extract(**kwargs)
        return draft.model_copy(
            update={
                "tasks": [
                    draft.tasks[0].model_copy(update={"phase_temp_id": "tmp_phase_missing"}),
                    draft.tasks[0].model_copy(update={"name": "Duplicate excavation"}),
                ],
                "dependencies": [
                    draft.dependencies[0].model_copy(
                        update={"successor_temp_id": "tmp_task_excavation"}
                    )
                ],
                "material_requirements": [
                    draft.material_requirements[0].model_copy(update={"unit": "kg"})
                ],
            }
        )


class FailOnceExtractor:
    def __init__(self) -> None:
        self.calls = 0
        self._delegate = FixedDraftExtractor()

    async def extract(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary extraction outage")
        return await self._delegate.extract(**kwargs)


class SecretFailingExtractor:
    async def extract(self, **kwargs) -> ProjectImportDraft:
        raise RuntimeError("provider secret=do-not-persist source=private-plan")


class UnexpectedCallExtractor:
    async def extract(self, **kwargs) -> ProjectImportDraft:
        raise AssertionError("a persisted draft must resume at validation")


class ControlledDraftExtractor:
    def __init__(self, task_name: str, *, fail: bool = False) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._task_name = task_name
        self._fail = fail

    async def extract(self, **kwargs) -> ProjectImportDraft:
        self.started.set()
        await self.release.wait()
        if self._fail:
            raise RuntimeError("expired extraction failed")
        draft = await FixedDraftExtractor().extract(**kwargs)
        tasks = list(draft.tasks)
        tasks[0] = tasks[0].model_copy(update={"name": self._task_name})
        return draft.model_copy(update={"tasks": tasks})


def make_app(store: InMemoryRepositoryStore) -> FastAPI:
    app = FastAPI()
    app.state.auth_runtime = SimpleNamespace(store=store)
    app.state.project_import_draft_extractor = FixedDraftExtractor()
    app.state.project_access_provider = lambda _request, project_id, permission: _project_access(
        project_id, permission
    )
    install_request_id_middleware(app)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


def make_app_with_extractor(store: InMemoryRepositoryStore, extractor: object) -> FastAPI:
    app = make_app(store)
    app.state.project_import_draft_extractor = extractor
    return app


def _project_access(project_id: str, permission: ProjectPermission) -> ProjectAccessContext:
    assert project_id == PROJECT_ID
    assert permission is ProjectPermission.MANAGE
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id=ACTOR_ID, subject="import-api-test"),
        project_id=project_id,
        role=MemberRole.ADMIN,
    )


def _canonical_counts(store: InMemoryRepositoryStore) -> tuple[int, int, int, int]:
    return (
        len(store.repository(ProjectPhase).list(PROJECT_ID)),
        len(store.repository(Task).list(PROJECT_ID)),
        len(store.repository(Material).list(PROJECT_ID)),
        len(store.repository(MaterialRequirement).list(PROJECT_ID)),
    )


@pytest.mark.asyncio
async def test_import_draft_can_be_reviewed_and_cancelled_without_canonical_mutations() -> None:
    store = InMemoryRepositoryStore()
    transport = httpx.ASGITransport(
        app=make_app_with_extractor(store, ConflictDraftExtractor()),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={
                "source_name": "ridge-house.md",
                "source_type": SourceType.MARKDOWN.value,
                "source_text": "Task: Foundation",
            },
            headers={"Idempotency-Key": "project-import-review:create"},
        )
        review = created.json()
        fetched = await client.get(f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}")
        cancelled = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}/cancel",
            json={"expected_version": review["version"]},
            headers={"Idempotency-Key": "project-import-review:cancel"},
        )
        discarded = await client.get(f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}")
        confirm_cancelled = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}/confirm",
            json={"expected_version": cancelled.json()["version"]},
            headers={"Idempotency-Key": "project-import-review:confirm-cancelled"},
        )

    assert created.status_code == 201
    assert review["status"] == "validation_failed"
    assert [item["name"] for item in review["tasks"]] == ["Excavation", "Foundation"]
    assert len(review["dependencies"]) == 1
    assert review["materials"][0]["name"] == "Cement"
    assert review["requirements"][0]["required_quantity"] == "100"
    assert review["warnings"][0]["code"] == "MISSING_DATE"
    assert review["conflicts"][0]["code"] == "EXISTING_TASK_POSSIBLE_MATCH"
    assert review["unresolved_references"] == ["Foundation foreman"]
    assert fetched.status_code == 200
    assert fetched.json()["tasks"] == review["tasks"]
    assert _canonical_counts(store) == (0, 0, 0, 0)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert discarded.status_code == 200
    assert discarded.json()["tasks"] == []
    assert _canonical_counts(store) == (0, 0, 0, 0)
    assert confirm_cancelled.status_code == 409


@pytest.mark.asyncio
async def test_confirming_a_conflicted_review_is_rejected_without_canonical_mutations() -> None:
    store = InMemoryRepositoryStore()
    app = make_app_with_extractor(store, ConflictDraftExtractor())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={"source_name": "ridge-house.md", "source_text": "Task: Foundation"},
            headers={"Idempotency-Key": "project-import-conflict:create"},
        )
        review = created.json()
        confirmed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}/confirm",
            json={"expected_version": review["version"]},
            headers={"Idempotency-Key": "project-import-conflict:confirm"},
        )

    assert created.status_code == 201
    assert confirmed.status_code == 422
    assert confirmed.json()["error"]["code"] == "PROJECT_IMPORT_VALIDATION_FAILED"
    assert _canonical_counts(store) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_invalid_cross_references_are_persisted_and_cannot_be_confirmed() -> None:
    store = InMemoryRepositoryStore()
    app = make_app_with_extractor(store, InvalidReferencesDraftExtractor())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={"source_name": "ridge-house.md", "source_text": "Task: Foundation"},
            headers={"Idempotency-Key": "project-import-invalid:create"},
        )
        review = created.json()
        fetched = await client.get(f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}")
        confirmed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}/confirm",
            json={"expected_version": review["version"]},
            headers={"Idempotency-Key": "project-import-invalid:confirm"},
        )

    expected_codes = {
        "DUPLICATE_TEMP_ID",
        "UNKNOWN_TASK_PHASE",
        "SELF_DEPENDENCY",
        "MATERIAL_UNIT_MISMATCH",
    }
    assert created.status_code == 201
    assert review["status"] == "validation_failed"
    assert {item["code"] for item in review["conflicts"]} >= expected_codes
    assert fetched.status_code == 200
    assert fetched.json()["tasks"] == review["tasks"]
    assert confirmed.status_code == 422
    assert confirmed.json()["error"]["code"] == "PROJECT_IMPORT_VALIDATION_FAILED"
    assert _canonical_counts(store) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_confirming_a_reviewed_import_commits_once() -> None:
    store = InMemoryRepositoryStore()
    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={"source_name": "ridge-house.md", "source_text": "Task: Foundation"},
            headers={"Idempotency-Key": "project-import-confirm:create"},
        )
        review = created.json()
        confirmed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}/confirm",
            json={"expected_version": review["version"]},
            headers={"Idempotency-Key": "project-import-confirm:confirm"},
        )
        replay = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{review['id']}/confirm",
            json={"expected_version": review["version"]},
            headers={"Idempotency-Key": "project-import-confirm:confirm"},
        )

    assert created.status_code == 201
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "imported"
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert _canonical_counts(store) == (1, 2, 1, 1)


@pytest.mark.asyncio
async def test_persisted_review_can_be_read_and_cancelled_when_extractor_is_unavailable() -> None:
    store = InMemoryRepositoryStore()
    app = make_app(store)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={"source_name": "ridge-house.md", "source_text": "Task: Foundation"},
            headers={"Idempotency-Key": "project-import-outage:create"},
        )
        delattr(app.state, "project_import_draft_extractor")
        fetched = await client.get(f"/api/v1/projects/{PROJECT_ID}/imports/{created.json()['id']}")
        cancelled = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{created.json()['id']}/cancel",
            json={"expected_version": created.json()["version"]},
            headers={"Idempotency-Key": "project-import-outage:cancel"},
        )

    assert fetched.status_code == 200
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_extractor_outage_persists_a_retryable_terminal_failure() -> None:
    store = InMemoryRepositoryStore()
    app = make_app(store)
    delattr(app.state, "project_import_draft_extractor")
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Idempotency-Key": "project-import-inflight:create"}
    payload = {"source_name": "ridge-house.md", "source_text": "Task: Foundation"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports", json=payload, headers=headers
        )

    assert first.status_code == 503
    record = store.repository(ProjectImportRecord).list(PROJECT_ID)[0]
    assert record.status is ProjectImportStatus.EXTRACTION_FAILED
    assert record.failure_code == "dependency_unavailable"
    assert record.failure_message == "Project import extraction dependency is unavailable."
    assert _canonical_counts(store) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_extraction_failure_persists_only_safe_reloadable_diagnostics() -> None:
    store = InMemoryRepositoryStore()
    app = make_app_with_extractor(store, SecretFailingExtractor())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={"source_name": "private-plan.md", "source_text": "Task: Foundation"},
            headers={"Idempotency-Key": "project-import-safe-failure:create"},
        )
        record = store.repository(ProjectImportRecord).list(PROJECT_ID)[0]
        reloaded = await client.get(f"/api/v1/projects/{PROJECT_ID}/imports/{record.id}")

    assert failed.status_code == 500
    assert reloaded.status_code == 200
    assert reloaded.json()["status"] == "extraction_failed"
    assert reloaded.json()["failure_code"] == "extraction_failed"
    assert reloaded.json()["failure_message"] == (
        "Project import extraction failed and can be retried."
    )
    assert "secret" not in record.failure_message.lower()
    assert "private-plan" not in record.failure_message.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resume_status",
    [ProjectImportStatus.DRAFT, ProjectImportStatus.VALIDATING],
)
async def test_restart_resumes_persisted_draft_at_validation_without_reextracting(
    resume_status: ProjectImportStatus,
) -> None:
    store = InMemoryRepositoryStore()
    import_id = "imp_resumevalidation123"
    source_id = "src_resumevalidation123"
    key = "project-import-resume-validation:create"
    draft = await FixedDraftExtractor().extract(
        project_id=PROJECT_ID,
        import_id=import_id,
        source_id=source_id,
        source_text="Task: Foundation",
    )
    now = datetime.now(UTC)
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=import_id,
            project_id=PROJECT_ID,
            source_id=source_id,
            status=resume_status,
            draft=draft.model_copy(update={"status": resume_status}),
            extraction_idempotency_key=key,
            extraction_request_fingerprint=sha256(
                f"{PROJECT_ID}\x00{key}\x00{source_id}".encode()
            ).hexdigest(),
            extraction_session_id=import_id,
            extraction_invocation_id=f"extract:{import_id}",
            extraction_attempt=1,
            created_at=now,
            updated_at=now,
        )
    )

    restarted = ProjectImportReviewService(store, UnexpectedCallExtractor())
    result = await restarted.extract_text(
        _project_access(PROJECT_ID, ProjectPermission.MANAGE),
        import_id=import_id,
        source_id=source_id,
        source_name="ridge-house.md",
        source_text="Task: Foundation",
        source_type=SourceType.MARKDOWN,
        extraction_idempotency_key=key,
    )

    assert result.record.status is ProjectImportStatus.NEEDS_REVIEW
    assert result.record.draft is not None
    assert [task.name for task in result.record.draft.tasks] == ["Excavation", "Foundation"]


@pytest.mark.asyncio
async def test_mismatched_extraction_retry_conflicts_without_changing_the_claim() -> None:
    store = InMemoryRepositoryStore()
    import_id = "imp_retryclaim123"
    source_id = "src_retryclaim123"
    service = ProjectImportReviewService(store, FailOnceExtractor())
    access = _project_access(PROJECT_ID, ProjectPermission.MANAGE)

    with pytest.raises(RuntimeError, match="temporary extraction outage"):
        await service.extract_text(
            access,
            import_id=import_id,
            source_id=source_id,
            source_name="ridge-house.md",
            source_text="Task: Foundation",
            source_type=SourceType.MARKDOWN,
            extraction_idempotency_key="original-claim",
        )

    with pytest.raises(ProjectImportReviewStateError):
        await service.extract_text(
            access,
            import_id=import_id,
            source_id=source_id,
            source_name="ridge-house.md",
            source_text="Task: Foundation",
            source_type=SourceType.MARKDOWN,
            extraction_idempotency_key="different-claim",
        )

    record = store.repository(ProjectImportRecord).require(PROJECT_ID, import_id)
    assert record.status is ProjectImportStatus.EXTRACTION_FAILED
    assert record.extraction_idempotency_key == "original-claim"


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_fails", [False, True])
async def test_expired_extraction_attempt_cannot_mutate_reclaimed_attempt(
    stale_fails: bool,
) -> None:
    store = InMemoryRepositoryStore()
    access = _project_access(PROJECT_ID, ProjectPermission.MANAGE)
    import_id = "imp_attemptfence123"
    source_id = "src_attemptfence123"
    key = "project-import-attempt-fence:create"
    stale_extractor = ControlledDraftExtractor("Stale excavation", fail=stale_fails)
    current_extractor = ControlledDraftExtractor("Current excavation")

    stale_task = asyncio.create_task(
        ProjectImportReviewService(store, stale_extractor).extract_text(
            access,
            import_id=import_id,
            source_id=source_id,
            source_name="ridge-house.md",
            source_text="Task: Foundation",
            source_type=SourceType.MARKDOWN,
            extraction_idempotency_key=key,
        )
    )
    await stale_extractor.started.wait()
    imports = store.repository(ProjectImportRecord)
    first_claim = imports.require(PROJECT_ID, import_id)
    imports.save(
        first_claim.model_copy(
            update={"extraction_lease_until": datetime.now(UTC) - timedelta(seconds=1)}
        ),
        expected_version=first_claim.version,
    )

    current_task = asyncio.create_task(
        ProjectImportReviewService(store, current_extractor).extract_text(
            access,
            import_id=import_id,
            source_id=source_id,
            source_name="ridge-house.md",
            source_text="Task: Foundation",
            source_type=SourceType.MARKDOWN,
            extraction_idempotency_key=key,
        )
    )
    await current_extractor.started.wait()

    stale_extractor.release.set()
    if stale_fails:
        with pytest.raises(RuntimeError, match="expired extraction failed"):
            await stale_task
    else:
        with pytest.raises(ProjectImportReviewStateError):
            await stale_task
    active_claim = imports.require(PROJECT_ID, import_id)
    assert active_claim.status is ProjectImportStatus.EXTRACTING
    assert active_claim.extraction_attempt == 2

    current_extractor.release.set()
    current = await current_task
    assert current.record.status is ProjectImportStatus.NEEDS_REVIEW
    assert current.record.draft is not None
    assert current.record.draft.tasks[0].name == "Current excavation"


@pytest.mark.asyncio
async def test_terminal_replay_requires_the_original_idempotency_claim() -> None:
    store = InMemoryRepositoryStore()
    transport = httpx.ASGITransport(app=make_app(store), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports",
            json={"source_name": "ridge-house.md", "source_text": "Task: Foundation"},
            headers={"Idempotency-Key": "project-import-claim:create"},
        )
        confirmed = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{created.json()['id']}/confirm",
            json={"expected_version": created.json()["version"]},
            headers={"Idempotency-Key": "project-import-claim:confirm"},
        )
        stale = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{created.json()['id']}/confirm",
            json={"expected_version": confirmed.json()["version"]},
            headers={"Idempotency-Key": "project-import-claim:confirm"},
        )
        different_claim = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports/{created.json()['id']}/confirm",
            json={"expected_version": created.json()["version"]},
            headers={"Idempotency-Key": "project-import-claim:other"},
        )

    assert confirmed.status_code == 200
    assert stale.status_code == 409
    assert different_claim.status_code == 409


@pytest.mark.asyncio
async def test_failed_extraction_retries_with_the_same_durable_claim() -> None:
    store = InMemoryRepositoryStore()
    extractor = FailOnceExtractor()
    app = make_app_with_extractor(store, extractor)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Idempotency-Key": "project-import-retry:create"}
    payload = {"source_name": "ridge-house.md", "source_text": "Task: Foundation"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports", json=payload, headers=headers
        )
        second = await client.post(
            f"/api/v1/projects/{PROJECT_ID}/imports", json=payload, headers=headers
        )

    assert first.status_code == 500
    assert second.status_code == 201
    assert second.json()["status"] == "needs_review"
    assert extractor.calls == 2
    record = store.repository(ProjectImportRecord).require(PROJECT_ID, second.json()["id"])
    assert record.extraction_attempt == 2
    assert record.extraction_session_id == record.id
    assert record.extraction_invocation_id == f"extract:{record.id}"


@pytest.mark.asyncio
async def test_api_rejects_an_access_provider_that_returns_the_wrong_project() -> None:
    store = InMemoryRepositoryStore()
    app = make_app(store)
    app.state.project_access_provider = lambda _request, _project_id, permission: _project_access(
        PROJECT_ID, permission
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/projects/prj_other123/imports/imp_missing123")

    assert response.status_code == 403
