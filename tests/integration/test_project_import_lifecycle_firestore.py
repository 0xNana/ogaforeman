from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import os
from uuid import uuid4

from google.cloud import firestore
import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import MemberRole
from app.domain.import_records import ProjectImportRecord
from app.domain.models import Task
from app.domain.project_import import ProjectImportDraft, ProjectImportStatus, SourceType
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.project_import import ProjectImportService
from app.services.project_import_review import ProjectImportReviewService
from app.services.project_sources import ProjectSourceService


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for project import restart verification",
    ),
]


PROJECT_ID = "prj_importrestart123"
IMPORT_ID = "imp_importrestart123"
SOURCE_ID = "src_importrestart123"


class UnexpectedExtractor:
    async def extract(self, **kwargs: object) -> ProjectImportDraft:
        raise AssertionError("restart must resume the persisted draft without model extraction")


def _access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="restart-test"),
        project_id=PROJECT_ID,
        role=MemberRole.ADMIN,
    )


def _draft(status: ProjectImportStatus) -> ProjectImportDraft:
    return ProjectImportDraft(
        id=IMPORT_ID,
        project_id=PROJECT_ID,
        source_id=SOURCE_ID,
        status=status,
        confirmed_at=(
            datetime.now(UTC)
            if status
            in {
                ProjectImportStatus.CONFIRMED,
                ProjectImportStatus.IMPORTING,
                ProjectImportStatus.IMPORT_FAILED,
                ProjectImportStatus.IMPORTED,
            }
            else None
        ),
        project={"name": "Restart residence"},
        tasks=[{"temp_id": "tmp_task_foundation", "name": "Foundation"}],
    )


@pytest.mark.asyncio
async def test_validation_resumes_from_firestore_draft_after_fresh_client_restart() -> None:
    cloud_project = f"oga-project-import-validation-{uuid4().hex}"
    key = "project-import-firestore-validation"
    initial = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    now = datetime.now(UTC)
    initial.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=IMPORT_ID,
            project_id=PROJECT_ID,
            source_id=SOURCE_ID,
            status=ProjectImportStatus.DRAFT,
            draft=_draft(ProjectImportStatus.DRAFT),
            extraction_idempotency_key=key,
            extraction_request_fingerprint=sha256(
                f"{PROJECT_ID}\x00{key}\x00{SOURCE_ID}".encode()
            ).hexdigest(),
            extraction_session_id=IMPORT_ID,
            extraction_invocation_id=f"extract:{IMPORT_ID}",
            extraction_attempt=1,
            created_at=now,
            updated_at=now,
        )
    )

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    restarted = ProjectImportReviewService(restarted_store, UnexpectedExtractor())
    result = await restarted.extract_text(
        _access(),
        import_id=IMPORT_ID,
        source_id=SOURCE_ID,
        source_name="restart-plan.md",
        source_text="Task: Foundation",
        source_type=SourceType.MARKDOWN,
        extraction_idempotency_key=key,
    )

    final_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    final = final_store.repository(ProjectImportRecord).require(PROJECT_ID, IMPORT_ID)
    assert result.record.status is ProjectImportStatus.NEEDS_REVIEW
    assert final.status is ProjectImportStatus.NEEDS_REVIEW
    assert final.draft is not None
    assert final.draft.tasks[0].name == "Foundation"


def test_canonical_commit_resumes_from_firestore_importing_after_fresh_client_restart() -> None:
    cloud_project = f"oga-project-import-commit-{uuid4().hex}"
    key = "project-import-firestore-confirm"
    expected_version = 0
    initial = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    ProjectSourceService(initial).persist_text(
        _access(),
        source_id=SOURCE_ID,
        name="restart-plan.md",
        text="Task: Foundation",
        source_type=SourceType.MARKDOWN,
    )
    draft = _draft(ProjectImportStatus.IMPORTING)
    initial.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=IMPORT_ID,
            project_id=PROJECT_ID,
            source_id=SOURCE_ID,
            status=ProjectImportStatus.IMPORTING,
            draft=draft,
            confirmed_at=draft.confirmed_at,
            import_attempt=1,
            decision_action="confirm",
            decision_idempotency_key=key,
            decision_request_fingerprint=sha256(
                f"confirm\x00{key}\x00{expected_version}".encode()
            ).hexdigest(),
            decision_expected_version=expected_version,
        )
    )

    restarted_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    result = ProjectImportService(restarted_store).import_confirmed(
        draft.model_copy(update={"status": ProjectImportStatus.CONFIRMED}),
        _access(),
        expected_review_version=expected_version,
        decision_idempotency_key=key,
    )

    final_store = FirestoreRepositoryStore(firestore.Client(project=cloud_project))
    final = final_store.repository(ProjectImportRecord).require(PROJECT_ID, IMPORT_ID)
    tasks = final_store.repository(Task).list(PROJECT_ID)
    assert not result.replayed
    assert final.status is ProjectImportStatus.IMPORTED
    assert [task.title for task in tasks] == ["Foundation"]
