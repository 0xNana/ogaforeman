"""Durable review lifecycle for extracted project-import drafts."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.enums import ActorType
from app.domain.import_records import ProjectImportRecord
from app.domain.project_import import (
    ProjectImportDraft,
    ProjectImportStatus,
    SourceType,
    ensure_project_import_transition,
)
from app.domain.models import ActivityEvent
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import (
    ProjectRepository,
    RepositorySession,
    RepositoryStore,
    VersionConflictError,
)
from app.repositories.membership import AuthorizedProjectRepository
from app.services.project_import import ProjectImportService
from app.services.project_import_diff import ProjectImportDiffService
from app.services.project_import_validation import (
    ProjectImportValidationResult,
    ProjectImportValidator,
)
from app.services.project_source_adapter import StructuredTextProjectAdapter
from app.services.project_sources import ProjectSourceService


class ProjectImportReviewNotFoundError(RuntimeError):
    code = "PROJECT_IMPORT_NOT_FOUND"


class ProjectImportReviewStateError(RuntimeError):
    code = "PROJECT_IMPORT_INVALID_STATE"


class ProjectImportExtractionError(ValueError):
    code = "PROJECT_IMPORT_EXTRACTION_INVALID"


class ProjectImportDependencyUnavailableError(RuntimeError):
    code = "DEPENDENCY_UNAVAILABLE"


EntityT = TypeVar("EntityT", bound=BaseModel)


class ProjectImportDraftExtractor(Protocol):
    def extract(
        self,
        *,
        project_id: str,
        import_id: str,
        source_id: str,
        source_text: str,
    ) -> Awaitable[ProjectImportDraft]: ...


@dataclass(frozen=True, slots=True)
class ProjectImportReviewResult:
    record: ProjectImportRecord
    replayed: bool = False
    should_extract: bool = False
    should_validate: bool = False


class ProjectImportReviewService:
    """Persist review-only import drafts until an explicit confirmation commits them."""

    def __init__(
        self,
        store: RepositoryStore,
        extractor: ProjectImportDraftExtractor | None = None,
    ) -> None:
        self._store = store
        self._extractor = extractor
        self._validator = ProjectImportValidator()
        self._diff = ProjectImportDiffService()
        self._importer = ProjectImportService(store)
        self._sources = ProjectSourceService(store)

    async def extract_text(
        self,
        access: ProjectAccessContext,
        *,
        import_id: str,
        source_id: str,
        source_name: str,
        source_text: str,
        source_type: SourceType | None,
        extraction_idempotency_key: str | None = None,
    ) -> ProjectImportReviewResult:
        ensure_permission(access, ProjectPermission.MANAGE)
        source = StructuredTextProjectAdapter(
            name=source_name,
            source_type=source_type,
        ).load(source_text)
        self._sources.persist_text(
            access,
            source_id=source_id,
            name=source.name,
            text=source.text,
            source_type=source.source_type,
        )
        self._ensure_uploaded(
            access,
            import_id=import_id,
            source_id=source_id,
            extraction_idempotency_key=extraction_idempotency_key,
        )
        claimed = self._claim_extraction_or_replay(access, import_id=import_id)
        if claimed.should_validate:
            return self._validate_stored_draft(access, claimed.record)
        if not claimed.should_extract:
            return claimed
        extraction_attempt = claimed.record.extraction_attempt
        try:
            if self._extractor is None:
                raise ProjectImportDependencyUnavailableError(
                    "project import extractor is unavailable"
                )
            draft = await self._extractor.extract(
                project_id=access.project_id,
                import_id=import_id,
                source_id=source_id,
                source_text=source.text,
            )
            try:
                self._ensure_draft_scope(draft, access, import_id, source_id)
            except ValueError as exc:
                raise ProjectImportExtractionError(str(exc)) from exc
        except Exception as exc:
            self._mark_extraction_failed(
                access,
                import_id,
                exc,
                expected_extraction_attempt=extraction_attempt,
            )
            raise
        drafted = self._store_draft(
            access,
            draft,
            expected_extraction_attempt=extraction_attempt,
        )
        return self._validate_stored_draft(access, drafted.record)

    def get(self, access: ProjectAccessContext, import_id: str) -> ProjectImportRecord:
        ensure_permission(access, ProjectPermission.MANAGE)
        record = _authorized_repository(self._store, ProjectImportRecord, access).get(
            access.project_id, import_id
        )
        if record is None:
            raise ProjectImportReviewNotFoundError(f"project import {import_id} was not found")
        return record

    def cancel(
        self,
        access: ProjectAccessContext,
        *,
        import_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> ProjectImportReviewResult:
        ensure_permission(access, ProjectPermission.MANAGE)
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> ProjectImportReviewResult:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.get(access.project_id, import_id)
            if record is None:
                raise ProjectImportReviewNotFoundError(f"project import {import_id} was not found")
            if record.status is ProjectImportStatus.CANCELLED:
                _assert_decision_replay(record, "cancel", idempotency_key, expected_version)
                return ProjectImportReviewResult(record=record, replayed=True)
            if record.status not in {
                ProjectImportStatus.UPLOADED,
                ProjectImportStatus.EXTRACTING,
                ProjectImportStatus.DRAFT,
                ProjectImportStatus.VALIDATING,
                ProjectImportStatus.EXTRACTION_FAILED,
                ProjectImportStatus.NEEDS_REVIEW,
                ProjectImportStatus.VALIDATION_FAILED,
                ProjectImportStatus.IMPORT_FAILED,
            }:
                raise ProjectImportReviewStateError(
                    f"project import cannot be cancelled from {record.status.value}"
                )
            ensure_project_import_transition(record.status, ProjectImportStatus.CANCELLED)
            cancelled = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.CANCELLED,
                        "draft": None,
                        "cancelled_at": now,
                        "extraction_lease_until": None,
                        "decision_action": "cancel",
                        "decision_idempotency_key": idempotency_key,
                        "decision_request_fingerprint": _decision_fingerprint(
                            "cancel", idempotency_key, expected_version
                        ),
                        "decision_expected_version": expected_version,
                        "updated_at": now,
                    }
                ),
                expected_version=expected_version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:cancelled",
                action="project.import.cancelled",
                entity_id=import_id,
                summary="Cancelled and discarded the project import draft.",
                metadata={"source_id": record.source_id},
                occurred_at=now,
            )
            return ProjectImportReviewResult(record=cancelled)

        return self._store.run_transaction(operation)

    def confirm(
        self,
        access: ProjectAccessContext,
        *,
        import_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> ProjectImportReviewResult:
        record = self.get(access, import_id)
        if record.status is ProjectImportStatus.IMPORTED:
            _assert_decision_replay(record, "confirm", idempotency_key, expected_version)
            return ProjectImportReviewResult(record=record, replayed=True)
        if record.status is ProjectImportStatus.VALIDATION_FAILED and record.draft is not None:
            self._validator.validate_or_raise(record.draft)
        if (
            record.status
            not in {
                ProjectImportStatus.NEEDS_REVIEW,
                ProjectImportStatus.CONFIRMED,
                ProjectImportStatus.IMPORTING,
                ProjectImportStatus.IMPORT_FAILED,
            }
            or record.draft is None
        ):
            raise ProjectImportReviewStateError(
                f"project import cannot be confirmed from {record.status.value}"
            )
        now = datetime.now(UTC)
        confirmed_draft = record.draft.model_copy(
            update={
                "status": ProjectImportStatus.CONFIRMED,
                "confirmed_at": record.confirmed_at or now,
            }
        )
        result = self._importer.import_confirmed(
            confirmed_draft,
            access,
            expected_review_version=expected_version,
            decision_idempotency_key=idempotency_key,
        )
        return ProjectImportReviewResult(
            record=self.get(access, import_id),
            replayed=result.replayed,
        )

    def _ensure_uploaded(
        self,
        access: ProjectAccessContext,
        *,
        import_id: str,
        source_id: str,
        extraction_idempotency_key: str | None = None,
    ) -> ProjectImportRecord:
        now = datetime.now(UTC)
        key = extraction_idempotency_key or import_id
        request_fingerprint = sha256(
            f"{access.project_id}\x00{key}\x00{source_id}".encode()
        ).hexdigest()

        def operation(session: RepositorySession) -> ProjectImportRecord:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            existing = imports.get(access.project_id, import_id)
            if existing is not None:
                if existing.source_id != source_id:
                    raise ProjectImportReviewStateError(
                        "project import id already identifies a different source"
                    )
                if (
                    existing.extraction_idempotency_key is not None
                    and existing.extraction_idempotency_key != key
                ) or (
                    existing.extraction_request_fingerprint is not None
                    and existing.extraction_request_fingerprint != request_fingerprint
                ):
                    raise ProjectImportReviewStateError(
                        "project import id already identifies a different extraction request"
                    )
                return existing
            record = imports.create(
                ProjectImportRecord(
                    id=import_id,
                    project_id=access.project_id,
                    source_id=source_id,
                    status=ProjectImportStatus.UPLOADED,
                    extraction_idempotency_key=key,
                    extraction_request_fingerprint=request_fingerprint,
                    extraction_session_id=import_id,
                    extraction_invocation_id=f"extract:{import_id}",
                    created_at=now,
                    updated_at=now,
                )
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:uploaded",
                action="project.import.uploaded",
                entity_id=import_id,
                summary="Accepted a project source for extraction.",
                metadata={"source_id": source_id},
                occurred_at=now,
            )
            return record

        return self._store.run_transaction(operation)

    def _claim_extraction_or_replay(
        self,
        access: ProjectAccessContext,
        *,
        import_id: str,
    ) -> ProjectImportReviewResult:
        now = datetime.now(UTC)
        lease_until = now + timedelta(minutes=5)

        def operation(session: RepositorySession) -> ProjectImportReviewResult:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.require(access.project_id, import_id)
            if record.status in {ProjectImportStatus.DRAFT, ProjectImportStatus.VALIDATING}:
                if record.draft is None:
                    raise ProjectImportReviewStateError(
                        f"project import {record.status.value} state has no persisted draft"
                    )
                return ProjectImportReviewResult(
                    record=record,
                    replayed=True,
                    should_validate=True,
                )
            if record.status is ProjectImportStatus.EXTRACTING:
                if (
                    record.extraction_lease_until is not None
                    and record.extraction_lease_until > now
                ):
                    return ProjectImportReviewResult(record=record, replayed=True)
                resumed = imports.save(
                    record.model_copy(
                        update={
                            "extraction_lease_until": lease_until,
                            "extraction_attempt": record.extraction_attempt + 1,
                            "failure_code": None,
                            "failure_message": None,
                            "updated_at": now,
                        }
                    ),
                    expected_version=record.version,
                )
                _activity(
                    session,
                    access,
                    idempotency_key=(
                        f"project-import:{import_id}:extraction-resumed:{resumed.extraction_attempt}"
                    ),
                    action="project.import.extraction_resumed",
                    entity_id=import_id,
                    summary="Resumed an expired project import extraction claim.",
                    metadata={
                        "source_id": record.source_id,
                        "attempt": resumed.extraction_attempt,
                    },
                    occurred_at=now,
                )
                return ProjectImportReviewResult(
                    record=resumed,
                    replayed=True,
                    should_extract=True,
                )
            if record.status not in {
                ProjectImportStatus.UPLOADED,
                ProjectImportStatus.EXTRACTION_FAILED,
            }:
                return ProjectImportReviewResult(record=record, replayed=True)
            ensure_project_import_transition(record.status, ProjectImportStatus.EXTRACTING)
            attempt = record.extraction_attempt + 1
            extracting = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.EXTRACTING,
                        "extraction_lease_until": lease_until,
                        "extraction_attempt": attempt,
                        "failure_code": None,
                        "failure_message": None,
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:extraction-started:{attempt}",
                action=(
                    "project.import.extraction_resumed"
                    if record.status is ProjectImportStatus.EXTRACTION_FAILED
                    else "project.import.extraction_started"
                ),
                entity_id=import_id,
                summary=(
                    "Retried a failed project import extraction."
                    if record.status is ProjectImportStatus.EXTRACTION_FAILED
                    else "Started extracting a project import draft for review."
                ),
                metadata={"source_id": record.source_id, "attempt": attempt},
                occurred_at=now,
            )
            return ProjectImportReviewResult(
                record=extracting,
                replayed=record.status is ProjectImportStatus.EXTRACTION_FAILED,
                should_extract=True,
            )

        return self._store.run_transaction(operation)

    def _store_draft(
        self,
        access: ProjectAccessContext,
        draft: ProjectImportDraft,
        *,
        expected_extraction_attempt: int,
    ) -> ProjectImportReviewResult:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> ProjectImportReviewResult:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.require(access.project_id, draft.id)
            if (
                record.status is not ProjectImportStatus.EXTRACTING
                or record.extraction_attempt != expected_extraction_attempt
            ):
                raise ProjectImportReviewStateError(
                    "project import extraction claim was superseded before draft persistence"
                )
            ensure_project_import_transition(record.status, ProjectImportStatus.DRAFT)
            persisted_draft = draft.model_copy(update={"status": ProjectImportStatus.DRAFT})
            drafted = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.DRAFT,
                        "draft": persisted_draft,
                        "extraction_lease_until": None,
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{draft.id}:draft-created",
                action="project.import.draft_created",
                entity_id=draft.id,
                summary="Persisted the extracted project import draft.",
                metadata={"source_id": draft.source_id},
                occurred_at=now,
            )
            return ProjectImportReviewResult(record=drafted)

        return self._store.run_transaction(operation)

    def _validate_stored_draft(
        self,
        access: ProjectAccessContext,
        record: ProjectImportRecord,
    ) -> ProjectImportReviewResult:
        validating = (
            self._start_validation(access, record.id)
            if record.status is ProjectImportStatus.DRAFT
            else record
        )
        if validating.status is not ProjectImportStatus.VALIDATING or validating.draft is None:
            raise ProjectImportReviewStateError(
                f"project import cannot validate from {validating.status.value}"
            )
        try:
            validation = self._validator.validate(validating.draft)
        except Exception:
            self._mark_validation_failed(access, validating.id)
            raise
        return self._finish_validation(access, validating.id, validation)

    def _start_validation(
        self,
        access: ProjectAccessContext,
        import_id: str,
    ) -> ProjectImportRecord:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> ProjectImportRecord:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.require(access.project_id, import_id)
            if record.status is ProjectImportStatus.VALIDATING and record.draft is not None:
                return record
            if record.status is not ProjectImportStatus.DRAFT or record.draft is None:
                raise ProjectImportReviewStateError(
                    f"project import cannot start validation from {record.status.value}"
                )
            ensure_project_import_transition(record.status, ProjectImportStatus.VALIDATING)
            validating_draft = record.draft.model_copy(
                update={"status": ProjectImportStatus.VALIDATING}
            )
            validating = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.VALIDATING,
                        "draft": validating_draft,
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:validation-started",
                action="project.import.validation_started",
                entity_id=import_id,
                summary="Started deterministic project import validation.",
                metadata={"source_id": record.source_id},
                occurred_at=now,
            )
            return validating

        return self._store.run_transaction(operation)

    def _finish_validation(
        self,
        access: ProjectAccessContext,
        import_id: str,
        validation: ProjectImportValidationResult,
    ) -> ProjectImportReviewResult:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> ProjectImportReviewResult:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.require(access.project_id, import_id)
            if record.status is not ProjectImportStatus.VALIDATING or record.draft is None:
                if record.status in {
                    ProjectImportStatus.NEEDS_REVIEW,
                    ProjectImportStatus.VALIDATION_FAILED,
                }:
                    return ProjectImportReviewResult(record=record, replayed=True)
                raise ProjectImportReviewStateError(
                    f"project import cannot finish validation from {record.status.value}"
                )
            preflight_conflicts = (
                self._diff.blocking_conflicts(
                    self._diff.compare_session(validation.draft, session, access)
                )
                if validation.is_valid
                else ()
            )
            conflicts = [*validation.draft.conflicts, *preflight_conflicts]
            review_status = (
                ProjectImportStatus.NEEDS_REVIEW
                if not conflicts
                else ProjectImportStatus.VALIDATION_FAILED
            )
            ensure_project_import_transition(record.status, review_status)
            reviewed_draft = validation.draft.model_copy(
                update={
                    "status": review_status,
                    "reviewed_at": now,
                    "conflicts": conflicts,
                }
            )
            reviewed = imports.save(
                record.model_copy(
                    update={
                        "status": review_status,
                        "draft": reviewed_draft,
                        "reviewed_at": now,
                        "failure_code": None,
                        "failure_message": None,
                        "phase_count": len(reviewed_draft.phases),
                        "task_count": len(reviewed_draft.tasks) + len(reviewed_draft.milestones),
                        "material_count": len(reviewed_draft.materials),
                        "requirement_count": len(reviewed_draft.material_requirements),
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:validated",
                action=(
                    "project.import.validation_failed"
                    if review_status is ProjectImportStatus.VALIDATION_FAILED
                    else "project.import.extracted"
                ),
                entity_id=import_id,
                summary=(
                    "Project import validation found blocking conflicts."
                    if review_status is ProjectImportStatus.VALIDATION_FAILED
                    else "Extracted a project import draft for review."
                ),
                metadata={
                    "task_count": len(reviewed_draft.tasks) + len(reviewed_draft.milestones),
                    "material_count": len(reviewed_draft.materials),
                    "warning_count": len(reviewed_draft.warnings),
                    "conflict_count": len(reviewed_draft.conflicts),
                },
                occurred_at=now,
            )
            return ProjectImportReviewResult(record=reviewed)

        return self._store.run_transaction(operation)

    def _mark_extraction_failed(
        self,
        access: ProjectAccessContext,
        import_id: str,
        error: Exception,
        *,
        expected_extraction_attempt: int,
    ) -> None:
        now = datetime.now(UTC)
        if isinstance(error, ProjectImportDependencyUnavailableError):
            failure_code = "dependency_unavailable"
            failure_message = "Project import extraction dependency is unavailable."
        elif isinstance(error, ProjectImportExtractionError):
            failure_code = "extraction_invalid"
            failure_message = "Project import extraction returned an invalid draft."
        else:
            failure_code = "extraction_failed"
            failure_message = "Project import extraction failed and can be retried."

        def operation(session: RepositorySession) -> None:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.get(access.project_id, import_id)
            if (
                record is None
                or record.status is not ProjectImportStatus.EXTRACTING
                or record.extraction_attempt != expected_extraction_attempt
            ):
                return
            ensure_project_import_transition(record.status, ProjectImportStatus.EXTRACTION_FAILED)
            failed = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.EXTRACTION_FAILED,
                        "extraction_lease_until": None,
                        "failure_code": failure_code,
                        "failure_message": failure_message,
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=(
                    f"project-import:{import_id}:extraction-failed:{record.extraction_attempt}"
                ),
                action="project.import.extraction_failed",
                entity_id=failed.id,
                summary="Project import extraction failed before review was available.",
                metadata={"status": failed.status.value},
                occurred_at=now,
            )

        self._store.run_transaction(operation)

    def _mark_validation_failed(self, access: ProjectAccessContext, import_id: str) -> None:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> None:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.get(access.project_id, import_id)
            if (
                record is None
                or record.status is not ProjectImportStatus.VALIDATING
                or record.draft is None
            ):
                return
            ensure_project_import_transition(record.status, ProjectImportStatus.VALIDATION_FAILED)
            failed_draft = record.draft.model_copy(
                update={"status": ProjectImportStatus.VALIDATION_FAILED}
            )
            failed = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.VALIDATION_FAILED,
                        "draft": failed_draft,
                        "failure_code": "validation_failed",
                        "failure_message": (
                            "Project import validation failed and requires review."
                        ),
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:validation-error",
                action="project.import.validation_failed",
                entity_id=import_id,
                summary="Project import validation failed before review was available.",
                metadata={"status": failed.status.value},
                occurred_at=now,
            )

        self._store.run_transaction(operation)

    @staticmethod
    def _ensure_draft_scope(
        draft: ProjectImportDraft,
        access: ProjectAccessContext,
        import_id: str,
        source_id: str,
    ) -> None:
        if (
            draft.id != import_id
            or draft.project_id != access.project_id
            or draft.source_id != source_id
        ):
            raise ValueError("extracted project import draft does not match its authorized source")
        references = (
            [task.source_reference for task in draft.tasks]
            + [item.source_reference for item in draft.dependencies]
            + [item.source_reference for item in draft.materials]
            + [item.source_reference for item in draft.material_requirements]
            + [item.source_reference for item in draft.milestones]
            + [item.source_reference for item in draft.warnings]
            + [item.source_reference for item in draft.conflicts]
        )
        if any(
            reference is not None and reference.source_id != source_id for reference in references
        ):
            raise ValueError("extracted provenance must use the authorized source")


def _activity(
    session: RepositorySession,
    access: ProjectAccessContext,
    *,
    idempotency_key: str,
    action: str,
    entity_id: str,
    summary: str,
    metadata: dict[str, str | int],
    occurred_at: datetime,
) -> None:
    _authorized_repository(session, ActivityEvent, access).create(
        ActivityRepository.build_event(
            MutationContext(
                project_id=access.project_id,
                actor_type=ActorType.USER,
                actor_id=access.actor.user_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
            ),
            ActivitySpec(
                action=action,
                entity_type="project_import",
                entity_id=entity_id,
                summary=summary,
                metadata=metadata,
            ),
        )
    )


def _authorized_repository(
    session: RepositorySession,
    entity_type: type[EntityT],
    access: ProjectAccessContext,
) -> AuthorizedProjectRepository[EntityT]:
    repository: ProjectRepository[EntityT] = session.repository(entity_type)
    return AuthorizedProjectRepository(
        repository,
        access,
        mutation_permission=ProjectPermission.MANAGE,
    )


def _decision_fingerprint(action: str, idempotency_key: str, expected_version: int) -> str:
    return sha256(f"{action}\x00{idempotency_key}\x00{expected_version}".encode()).hexdigest()


def _assert_decision_replay(
    record: ProjectImportRecord,
    action: str,
    idempotency_key: str,
    expected_version: int,
) -> None:
    if (
        record.decision_action != action
        or record.decision_idempotency_key != idempotency_key
        or record.decision_request_fingerprint
        != _decision_fingerprint(action, idempotency_key, expected_version)
        or record.decision_expected_version != expected_version
    ):
        raise VersionConflictError(
            "terminal project import replay does not match its original claim"
        )


__all__ = [
    "ProjectImportDraftExtractor",
    "ProjectImportDependencyUnavailableError",
    "ProjectImportExtractionError",
    "ProjectImportReviewNotFoundError",
    "ProjectImportReviewResult",
    "ProjectImportReviewService",
    "ProjectImportReviewStateError",
]
