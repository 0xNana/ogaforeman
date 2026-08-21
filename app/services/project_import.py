"""Idempotent deterministic commit of a confirmed project import draft."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from hashlib import sha256
from typing import TypeVar

from pydantic import BaseModel

from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType, TaskSource, TaskStatus
from app.domain.import_records import (
    ImportProvenance,
    ImportProvenanceTargetType,
    MaterialRequirement,
    ProjectImportRecord,
    ProjectPhase,
    ProjectSource,
    ProjectSourceStatus,
    import_provenance_id,
)
from app.domain.materials import MaterialLedgerEntry, normalize_material_name
from app.domain.models import ActivityEvent, Material, Project, Task
from app.domain.project_import import (
    ProjectImportDraft,
    ProjectImportStatus,
    SourceReference,
    ensure_project_import_transition,
)
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import (
    ProjectRepository,
    RepositorySession,
    RepositoryStore,
    VersionConflictError,
)
from app.repositories.membership import AuthorizedProjectRepository
from app.services.project_import_validation import (
    ProjectImportValidationResult,
    ProjectImportValidator,
)
from app.services.project_import_diff import (
    ProjectImportDiffConflictError,
    ProjectImportDiffService,
)
from app.services.project_import_plan import (
    PreparedProjectImportPlan,
    canonical_import_id,
)


class ProjectImportConfirmationError(ValueError):
    code = "PROJECT_IMPORT_CONFIRMATION_REQUIRED"


class ProjectImportAlreadyCommittedError(RuntimeError):
    code = "PROJECT_IMPORT_ALREADY_COMMITTED"


EntityT = TypeVar("EntityT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ProjectImportResult:
    import_id: str
    project_id: str
    phase_count: int
    task_count: int
    material_count: int
    requirement_count: int
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class _PreparedImportEntities:
    plan: PreparedProjectImportPlan
    provenance: tuple[ImportProvenance, ...]
    phases: tuple[ProjectPhase, ...]
    tasks: tuple[Task, ...]
    materials: tuple[Material, ...]
    ledger: tuple[MaterialLedgerEntry, ...]
    requirements: tuple[MaterialRequirement, ...]


class ProjectImportService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._validator = ProjectImportValidator()
        self._diff = ProjectImportDiffService()

    def import_confirmed(
        self,
        draft: ProjectImportDraft,
        access: ProjectAccessContext,
        *,
        expected_review_version: int | None,
        decision_idempotency_key: str,
    ) -> ProjectImportResult:
        ensure_permission(access, ProjectPermission.MANAGE)
        ensure_project_scope(access, draft.project_id)
        if expected_review_version is None:
            raise VersionConflictError("expected review version is required for confirmation")
        if draft.status is not ProjectImportStatus.CONFIRMED or draft.confirmed_at is None:
            raise ProjectImportConfirmationError(
                "project import must be explicitly confirmed before commit"
            )

        # The service boundary owns the confirmation timestamp; callers cannot
        # backdate or predate an approval by crafting the draft payload.
        draft = draft.model_copy(update={"confirmed_at": datetime.now(UTC)})

        _ensure_source_references(draft)
        validated = self._validator.validate_or_raise(draft)
        request_fingerprint = _decision_fingerprint(
            "confirm", decision_idempotency_key, expected_review_version
        )
        self._preflight_confirmation(draft, access)
        claimed, source = self._claim_confirmation(
            draft,
            access,
            expected_review_version=expected_review_version,
            decision_idempotency_key=decision_idempotency_key,
            decision_request_fingerprint=request_fingerprint,
        )
        if claimed.status is ProjectImportStatus.IMPORTED:
            return _result(claimed, replayed=True)
        if claimed.confirmed_at is None:
            raise ProjectImportConfirmationError(
                "confirmed project import is missing its server confirmation timestamp"
            )
        importing = self._claim_import(
            access,
            import_id=draft.id,
            decision_idempotency_key=decision_idempotency_key,
            decision_request_fingerprint=request_fingerprint,
            expected_review_version=expected_review_version,
        )
        if importing.status is ProjectImportStatus.IMPORTED:
            return _result(importing, replayed=True)
        try:
            entities = self._prepare_entities(
                validated,
                source=source,
                imported_by=access.actor.user_id,
                imported_at=claimed.confirmed_at,
            )
        except Exception:
            self._mark_import_failed(access, draft.id)
            raise
        return self._commit(
            draft,
            access,
            entities,
            expected_review_version=expected_review_version,
            decision_idempotency_key=decision_idempotency_key,
            decision_request_fingerprint=request_fingerprint,
        )

    def import_draft(
        self,
        draft: ProjectImportDraft,
        access: ProjectAccessContext,
    ) -> ProjectImportResult:
        raise ProjectImportConfirmationError(
            "draft imports are review-only; confirm through ProjectImportReviewService"
        )

    def _claim_confirmation(
        self,
        draft: ProjectImportDraft,
        access: ProjectAccessContext,
        *,
        expected_review_version: int,
        decision_idempotency_key: str,
        decision_request_fingerprint: str,
    ) -> tuple[ProjectImportRecord, ProjectSource]:
        now = datetime.now(UTC)

        def operation(
            session: RepositorySession,
        ) -> tuple[ProjectImportRecord, ProjectSource]:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            source = _authorized_repository(session, ProjectSource, access).get(
                draft.project_id, draft.source_id
            )
            if source is None:
                raise ValueError("project import source must be persisted before import")
            if source.status != ProjectSourceStatus.ACTIVE:
                raise ProjectImportConfirmationError("project import source is not active")
            existing = imports.get(draft.project_id, draft.id)
            if existing is None:
                raise ProjectImportConfirmationError(
                    "a persisted needs_review record is required before confirmation"
                )
            if existing.status in {
                ProjectImportStatus.CONFIRMED,
                ProjectImportStatus.IMPORTING,
                ProjectImportStatus.IMPORT_FAILED,
                ProjectImportStatus.IMPORTED,
            }:
                _assert_decision_replay(
                    existing,
                    action="confirm",
                    idempotency_key=decision_idempotency_key,
                    request_fingerprint=decision_request_fingerprint,
                    expected_version=expected_review_version,
                )
                if (
                    existing.draft is None
                    or existing.source_id != draft.source_id
                    or _draft_fingerprint(existing.draft) != _draft_fingerprint(draft)
                ):
                    raise ProjectImportConfirmationError(
                        "confirmed import no longer matches its persisted draft"
                    )
                return existing, source
            if existing.status is not ProjectImportStatus.NEEDS_REVIEW:
                raise ProjectImportAlreadyCommittedError(
                    f"import {draft.id} already exists in state {existing.status.value}"
                )
            if (
                existing.draft is None
                or existing.source_id != draft.source_id
                or _draft_fingerprint(existing.draft) != _draft_fingerprint(draft)
            ):
                raise ProjectImportConfirmationError("reviewed import no longer matches its source")
            ensure_project_import_transition(existing.status, ProjectImportStatus.CONFIRMED)
            confirmed = imports.save(
                existing.model_copy(
                    update={
                        "status": ProjectImportStatus.CONFIRMED,
                        "draft": draft,
                        "confirmed_at": draft.confirmed_at,
                        "decision_action": "confirm",
                        "decision_idempotency_key": decision_idempotency_key,
                        "decision_request_fingerprint": decision_request_fingerprint,
                        "decision_expected_version": expected_review_version,
                        "failure_code": None,
                        "failure_message": None,
                        "diagnostic_stage": "commit",
                        "commit_outcome": "running",
                        "updated_at": now,
                    }
                ),
                expected_version=expected_review_version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{draft.id}:reviewed",
                action="project.import.reviewed",
                entity_type="project_import",
                entity_id=draft.id,
                summary="Reviewed and confirmed the project plan.",
                metadata={"source_id": draft.source_id, "import_id": draft.id},
                occurred_at=now,
            )
            return confirmed, source

        return self._store.run_transaction(operation)

    def _preflight_confirmation(
        self,
        draft: ProjectImportDraft,
        access: ProjectAccessContext,
    ) -> None:
        def operation(session: RepositorySession) -> None:
            record = _authorized_repository(session, ProjectImportRecord, access).get(
                draft.project_id, draft.id
            )
            if record is None:
                raise ProjectImportConfirmationError(
                    "a persisted needs_review record is required before confirmation"
                )
            # Imported records must reach the existing exact-claim replay check.
            # Recovery claims are checked again by the canonical commit transaction.
            if record.status is not ProjectImportStatus.NEEDS_REVIEW:
                return
            self._diff.ensure_additive(self._diff.compare_session(draft, session, access))

        try:
            self._store.run_transaction(operation)
        except ProjectImportDiffConflictError as exc:
            raise ProjectImportConfirmationError(
                "project import conflicts with current canonical project state"
            ) from exc

    def _claim_import(
        self,
        access: ProjectAccessContext,
        *,
        import_id: str,
        decision_idempotency_key: str,
        decision_request_fingerprint: str,
        expected_review_version: int,
    ) -> ProjectImportRecord:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> ProjectImportRecord:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            existing = imports.require(access.project_id, import_id)
            _assert_decision_replay(
                existing,
                action="confirm",
                idempotency_key=decision_idempotency_key,
                request_fingerprint=decision_request_fingerprint,
                expected_version=expected_review_version,
            )
            if existing.status in {
                ProjectImportStatus.IMPORTING,
                ProjectImportStatus.IMPORTED,
            }:
                return existing
            if existing.status not in {
                ProjectImportStatus.CONFIRMED,
                ProjectImportStatus.IMPORT_FAILED,
            }:
                raise ProjectImportAlreadyCommittedError(
                    f"import {import_id} cannot start from {existing.status.value}"
                )
            ensure_project_import_transition(existing.status, ProjectImportStatus.IMPORTING)
            attempt = existing.import_attempt + 1
            importing = imports.save(
                existing.model_copy(
                    update={
                        "status": ProjectImportStatus.IMPORTING,
                        "import_attempt": attempt,
                        "failure_code": None,
                        "failure_message": None,
                        "diagnostic_stage": "commit",
                        "diagnostic_attempt": attempt,
                        "commit_outcome": "running",
                        "updated_at": now,
                    }
                ),
                expected_version=existing.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:started:{attempt}",
                action="project.import.started",
                entity_type="project_import",
                entity_id=import_id,
                summary="Started importing the confirmed project plan.",
                metadata={
                    "source_id": existing.source_id,
                    "import_id": import_id,
                    "attempt": attempt,
                },
                occurred_at=now,
            )
            return importing

        return self._store.run_transaction(operation)

    def _commit(
        self,
        draft: ProjectImportDraft,
        access: ProjectAccessContext,
        entities: _PreparedImportEntities,
        *,
        expected_review_version: int,
        decision_idempotency_key: str,
        decision_request_fingerprint: str,
    ) -> ProjectImportResult:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> ProjectImportResult:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            existing = imports.get(draft.project_id, draft.id)
            if existing is None:
                raise ProjectImportConfirmationError(
                    "a persisted importing record is required before canonical commit"
                )
            if existing.status is ProjectImportStatus.IMPORTED:
                _assert_decision_replay(
                    existing,
                    action="confirm",
                    idempotency_key=decision_idempotency_key,
                    request_fingerprint=decision_request_fingerprint,
                    expected_version=expected_review_version,
                )
                return _result(existing, replayed=True)
            if existing.status is not ProjectImportStatus.IMPORTING:
                raise ProjectImportAlreadyCommittedError(
                    f"import {draft.id} already exists in state {existing.status.value}"
                )
            _assert_decision_replay(
                existing,
                action="confirm",
                idempotency_key=decision_idempotency_key,
                request_fingerprint=decision_request_fingerprint,
                expected_version=expected_review_version,
            )
            if (
                existing.draft is None
                or existing.source_id != draft.source_id
                or _draft_fingerprint(existing.draft) != _draft_fingerprint(draft)
            ):
                raise ProjectImportConfirmationError("reviewed import no longer matches its source")
            self._diff.ensure_additive(self._diff.compare_session(draft, session, access))
            projects = _authorized_repository(session, Project, access)
            project = projects.get(draft.project_id, draft.project_id)
            if project is not None and _is_initial_project_import(session, access):
                projects.save(
                    project.model_copy(
                        update={
                            "name": draft.project.name,
                            "location": draft.project.location or project.location,
                            "description": draft.project.description or project.description,
                            "start_date": draft.project.start_date or project.start_date,
                            "target_end_date": (
                                draft.project.target_end_date or project.target_end_date
                            ),
                            "status": draft.project.status,
                            "updated_at": now,
                        }
                    ),
                    expected_version=projects.version_of(draft.project_id, draft.project_id),
                )
            for provenance in entities.provenance:
                _authorized_repository(session, ImportProvenance, access).create(provenance)
            for phase in entities.phases:
                _authorized_repository(session, ProjectPhase, access).create(phase)
            for task in entities.tasks:
                _authorized_repository(session, Task, access).create(task)
                _activity(
                    session,
                    access,
                    idempotency_key=f"task:{task.id}:created:import:{draft.id}",
                    action="task.created",
                    entity_type="task",
                    entity_id=task.id,
                    summary=f"Created task {task.title}.",
                    metadata={"import_id": draft.id, "source_id": draft.source_id},
                    occurred_at=now,
                )
            for dependency in entities.plan.dependencies:
                _activity(
                    session,
                    access,
                    idempotency_key=(
                        f"dependency:{dependency.target_id}:created:import:{draft.id}"
                    ),
                    action="dependency.created",
                    entity_type="dependency",
                    entity_id=dependency.target_id,
                    summary=(
                        "Created task dependency from "
                        f"{dependency.predecessor_task_id} to {dependency.successor_task_id}."
                    ),
                    metadata={
                        "predecessor_task_id": dependency.predecessor_task_id,
                        "successor_task_id": dependency.successor_task_id,
                        "import_id": draft.id,
                        "source_id": draft.source_id,
                    },
                    occurred_at=now,
                )
            for material in entities.materials:
                _authorized_repository(session, Material, access).create(material)
                _activity(
                    session,
                    access,
                    idempotency_key=f"material:{material.id}:created:import:{draft.id}",
                    action="material.created",
                    entity_type="material",
                    entity_id=material.id,
                    summary=f"Created material {material.name}.",
                    metadata={
                        "unit": material.unit,
                        "import_id": draft.id,
                        "source_id": draft.source_id,
                    },
                    occurred_at=now,
                )
            for ledger_entry in entities.ledger:
                _authorized_repository(session, MaterialLedgerEntry, access).create(ledger_entry)
            for requirement in entities.requirements:
                _authorized_repository(session, MaterialRequirement, access).create(requirement)
                _activity(
                    session,
                    access,
                    idempotency_key=f"requirement:{requirement.id}:created:import:{draft.id}",
                    action="material.requirement.created",
                    entity_type="material_requirement",
                    entity_id=requirement.id,
                    summary="Created material requirement.",
                    metadata={
                        "task_id": requirement.task_id,
                        "material_id": requirement.material_id,
                        "import_id": draft.id,
                        "source_id": draft.source_id,
                    },
                    occurred_at=now,
                )

            _activity(
                session,
                access,
                idempotency_key=f"project-import:{draft.id}:completed",
                action="project.initialized",
                entity_type="project_import",
                entity_id=draft.id,
                summary="Imported the confirmed project plan into the canonical model.",
                metadata={
                    "phase_count": len(entities.phases),
                    "task_count": len(entities.tasks),
                    "material_count": len(entities.materials),
                    "requirement_count": len(entities.requirements),
                    "source_id": draft.source_id,
                    "import_id": draft.id,
                },
                occurred_at=now,
            )
            ensure_project_import_transition(existing.status, ProjectImportStatus.IMPORTED)
            completed = imports.save(
                existing.model_copy(
                    update={
                        "status": ProjectImportStatus.IMPORTED,
                        "phase_count": len(entities.phases),
                        "task_count": len(entities.tasks),
                        "material_count": len(entities.materials),
                        "requirement_count": len(entities.requirements),
                        "completed_at": now,
                        "diagnostic_stage": "commit",
                        "diagnostic_attempt": existing.import_attempt,
                        "commit_outcome": "succeeded",
                        "updated_at": now,
                    }
                ),
                expected_version=existing.version,
            )
            return _result(completed)

        try:
            return self._store.run_transaction(operation)
        except ProjectImportDiffConflictError as exc:
            self._mark_import_failed(
                access,
                draft.id,
                failure_code="canonical_preflight_conflict",
                failure_message=(
                    "Canonical project state changed after review; this import cannot be applied."
                ),
            )
            raise ProjectImportConfirmationError(
                "project import conflicts with current canonical project state"
            ) from exc
        except (
            VersionConflictError,
            ProjectImportConfirmationError,
            ProjectImportAlreadyCommittedError,
        ):
            raise
        except Exception:
            self._mark_import_failed(access, draft.id)
            raise

    def _mark_import_failed(
        self,
        access: ProjectAccessContext,
        import_id: str,
        *,
        failure_code: str = "import_commit_failed",
        failure_message: str = "Project import commit failed and can be retried.",
    ) -> None:
        now = datetime.now(UTC)

        def operation(session: RepositorySession) -> None:
            imports = _authorized_repository(session, ProjectImportRecord, access)
            record = imports.get(access.project_id, import_id)
            if record is None or record.status is not ProjectImportStatus.IMPORTING:
                return
            ensure_project_import_transition(record.status, ProjectImportStatus.IMPORT_FAILED)
            failed = imports.save(
                record.model_copy(
                    update={
                        "status": ProjectImportStatus.IMPORT_FAILED,
                        "failure_code": failure_code,
                        "failure_message": failure_message,
                        "diagnostic_stage": "commit",
                        "diagnostic_attempt": record.import_attempt,
                        "commit_outcome": "failed",
                        "updated_at": now,
                    }
                ),
                expected_version=record.version,
            )
            _activity(
                session,
                access,
                idempotency_key=f"project-import:{import_id}:failed:{failed.version}",
                action="project.import.failed",
                entity_type="project_import",
                entity_id=import_id,
                summary="Project import could not be committed; review can be retried or cancelled.",
                metadata={"status": failed.status.value},
                occurred_at=now,
            )

        self._store.run_transaction(operation)

    def _prepare_entities(
        self,
        result: ProjectImportValidationResult,
        *,
        source: ProjectSource,
        imported_by: str,
        imported_at: datetime,
    ) -> _PreparedImportEntities:
        draft = result.draft
        plan = result.plan
        phase_ids = dict(plan.phase_ids)
        task_ids = dict(plan.task_ids)
        material_ids = dict(plan.material_ids)
        ledger_ids = dict(plan.ledger_ids)
        provenance: list[ImportProvenance] = []

        def provenance_for(
            target_entity_type: ImportProvenanceTargetType,
            target_entity_id: str,
            reference: SourceReference | None,
        ) -> str:
            provenance_id = import_provenance_id(target_entity_type, target_entity_id)
            provenance.append(
                ImportProvenance(
                    id=provenance_id,
                    project_id=draft.project_id,
                    import_id=draft.id,
                    source_id=source.id,
                    source_checksum=source.checksum,
                    source_type=source.type,
                    source_name=source.name,
                    target_entity_type=target_entity_type,
                    target_entity_id=target_entity_id,
                    section=reference.section if reference is not None else None,
                    external_reference=(
                        reference.external_reference if reference is not None else None
                    ),
                    imported_by=imported_by,
                    imported_at=imported_at,
                    idempotency_key=(
                        f"project-import:{draft.id}:provenance:"
                        f"{target_entity_type.value}:{target_entity_id}"
                    ),
                )
            )
            return provenance_id

        phases: list[ProjectPhase] = []
        for phase in draft.phases:
            phase_id = phase_ids[phase.temp_id]
            phases.append(
                ProjectPhase(
                    id=phase_id,
                    project_id=draft.project_id,
                    import_id=draft.id,
                    name=phase.name,
                    sequence=phase.sequence,
                    description=phase.description,
                )
            )
            provenance_for(ImportProvenanceTargetType.PROJECT_PHASE, phase_id, None)
        tasks: list[Task] = []
        for task_draft in draft.tasks:
            status = TaskStatus(task_draft.initial_status.value)
            planned_finish = _at_utc(task_draft.planned_finish)
            task_provenance = provenance_for(
                ImportProvenanceTargetType.TASK,
                task_ids[task_draft.temp_id],
                task_draft.source_reference,
            )
            tasks.append(
                Task(
                    id=task_ids[task_draft.temp_id],
                    project_id=draft.project_id,
                    title=task_draft.name,
                    description=task_draft.description,
                    status=status,
                    phase_id=(
                        phase_ids[task_draft.phase_temp_id]
                        if task_draft.phase_temp_id is not None
                        else None
                    ),
                    trade=task_draft.trade,
                    location=task_draft.location,
                    planned_start=_at_utc(task_draft.planned_start),
                    planned_end=planned_finish,
                    actual_completion=(
                        _at_utc(task_draft.actual_completion)
                        if status is TaskStatus.COMPLETED
                        else None
                    ),
                    completion_percent=(
                        Decimal("100") if status is TaskStatus.COMPLETED else Decimal("0")
                    ),
                    source=TaskSource.IMPORT,
                    source_refs=[task_provenance] if task_provenance else [],
                )
            )
        for milestone in draft.milestones:
            planned = _at_utc(milestone.planned_date)
            if planned is None:
                continue
            milestone_provenance = provenance_for(
                ImportProvenanceTargetType.TASK,
                task_ids[milestone.temp_id],
                milestone.source_reference,
            )
            tasks.append(
                Task(
                    id=task_ids[milestone.temp_id],
                    project_id=draft.project_id,
                    title=milestone.name,
                    status=TaskStatus.PROPOSED,
                    planned_start=planned,
                    planned_end=planned,
                    is_milestone=True,
                    source=TaskSource.IMPORT,
                    source_refs=[milestone_provenance] if milestone_provenance else [],
                )
            )
        tasks_by_id = {task.id: task for task in tasks}
        for dependency, planned_dependency in zip(
            draft.dependencies, plan.dependencies, strict=True
        ):
            provenance_for(
                ImportProvenanceTargetType.DEPENDENCY,
                planned_dependency.target_id,
                dependency.source_reference,
            )
            successor = tasks_by_id[planned_dependency.successor_task_id]
            successor.dependency_ids.append(planned_dependency.predecessor_task_id)
        materials = tuple(
            Material(
                id=material_ids[material.temp_id],
                project_id=draft.project_id,
                name=material.name,
                normalized_name=normalize_material_name(material.name),
                unit=material.canonical_unit,
                location=material.location,
                available_quantity=material.initial_on_hand_quantity,
            )
            for material in draft.materials
        )
        for material in draft.materials:
            provenance_for(
                ImportProvenanceTargetType.MATERIAL,
                material_ids[material.temp_id],
                material.source_reference,
            )
        ledger = tuple(
            MaterialLedgerEntry(
                id=ledger_ids[material.temp_id],
                project_id=draft.project_id,
                material_id=material_ids[material.temp_id],
                quantity_delta=material.initial_on_hand_quantity,
                unit=material.canonical_unit,
                balance_after=material.initial_on_hand_quantity,
                reason="Initial inventory from confirmed project import.",
                actor_id="system",
                idempotency_key=f"project-import:{draft.id}:inventory:{material.temp_id}",
            )
            for material in draft.materials
            if material.initial_on_hand_quantity > 0
        )
        material_drafts_by_id = {
            material_ids[material.temp_id]: material for material in draft.materials
        }
        for ledger_entry in ledger:
            material = material_drafts_by_id[ledger_entry.material_id]
            provenance_for(
                ImportProvenanceTargetType.MATERIAL_LEDGER_ENTRY,
                ledger_entry.id,
                material.source_reference,
            )
        requirements: list[MaterialRequirement] = []
        for requirement, planned_requirement in zip(
            draft.material_requirements, plan.requirements, strict=True
        ):
            provenance_id = provenance_for(
                ImportProvenanceTargetType.MATERIAL_REQUIREMENT,
                planned_requirement.target_id,
                requirement.source_reference,
            )
            requirements.append(
                MaterialRequirement(
                    id=planned_requirement.target_id,
                    project_id=draft.project_id,
                    import_id=draft.id,
                    task_id=planned_requirement.task_id,
                    material_id=planned_requirement.material_id,
                    required_quantity=requirement.required_quantity,
                    unit=requirement.unit,
                    required_by=requirement.required_by,
                    confidence=requirement.confidence,
                    source_provenance_id=provenance_id,
                )
            )
        entities = _PreparedImportEntities(
            plan=plan,
            provenance=tuple(provenance),
            phases=tuple(phases),
            tasks=tuple(tasks),
            materials=materials,
            ledger=ledger,
            requirements=tuple(requirements),
        )
        _ensure_entities_match_plan(entities)
        return entities


def _activity(
    session: RepositorySession,
    access: ProjectAccessContext,
    *,
    idempotency_key: str,
    action: str,
    entity_type: str,
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
                entity_type=entity_type,
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


def _draft_fingerprint(draft: ProjectImportDraft) -> str:
    payload = draft.model_dump(
        mode="json",
        exclude={"status", "reviewed_at", "confirmed_at"},
    )
    import json

    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decision_fingerprint(action: str, idempotency_key: str, expected_version: int) -> str:
    return sha256(f"{action}\x00{idempotency_key}\x00{expected_version}".encode()).hexdigest()


def _assert_decision_replay(
    record: ProjectImportRecord,
    *,
    action: str,
    idempotency_key: str,
    request_fingerprint: str,
    expected_version: int,
) -> None:
    if (
        record.decision_action != action
        or record.decision_idempotency_key != idempotency_key
        or record.decision_request_fingerprint != request_fingerprint
        or record.decision_expected_version != expected_version
    ):
        raise VersionConflictError(
            "terminal project import replay does not match its original claim"
        )


def _ensure_source_references(draft: ProjectImportDraft) -> None:
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
        reference is not None and reference.source_id != draft.source_id for reference in references
    ):
        raise ProjectImportConfirmationError(
            "all import provenance references must point to the persisted import source"
        )


def _result(record: ProjectImportRecord, *, replayed: bool = False) -> ProjectImportResult:
    return ProjectImportResult(
        import_id=record.id,
        project_id=record.project_id,
        phase_count=record.phase_count,
        task_count=record.task_count,
        material_count=record.material_count,
        requirement_count=record.requirement_count,
        replayed=replayed,
    )


def _canonical_id(prefix: str, *parts: str) -> str:
    return canonical_import_id(prefix, *parts)


def _ensure_entities_match_plan(entities: _PreparedImportEntities) -> None:
    plan = entities.plan
    expected_ids = {
        "phase": {canonical_id for _, canonical_id in plan.phase_ids},
        "task": {canonical_id for _, canonical_id in plan.task_ids},
        "material": {canonical_id for _, canonical_id in plan.material_ids},
        "ledger": {canonical_id for _, canonical_id in plan.ledger_ids},
        "requirement": {requirement.target_id for requirement in plan.requirements},
    }
    actual_ids = {
        "phase": {entity.id for entity in entities.phases},
        "task": {entity.id for entity in entities.tasks},
        "material": {entity.id for entity in entities.materials},
        "ledger": {entity.id for entity in entities.ledger},
        "requirement": {entity.id for entity in entities.requirements},
    }
    expected_provenance_targets = set(plan.provenance_targets)
    actual_provenance_targets = {
        (provenance.target_entity_type, provenance.target_entity_id)
        for provenance in entities.provenance
    }
    actual_commit_writes = (
        len(entities.provenance)
        + len(entities.phases)
        + len(entities.tasks)
        + len(entities.materials)
        + len(entities.ledger)
        + len(entities.requirements)
        + 1  # reviewed project metadata
        + len(entities.tasks)
        + len(plan.dependencies)
        + len(entities.materials)
        + len(entities.requirements)
        + 1  # project.initialized activity
        + 1  # imported ProjectImportRecord save
    )
    if (
        actual_ids != expected_ids
        or actual_provenance_targets != expected_provenance_targets
        or actual_commit_writes != plan.commit_write_count
    ):
        raise RuntimeError("prepared project import entities diverged from the validated plan")


def _is_initial_project_import(
    session: RepositorySession,
    access: ProjectAccessContext,
) -> bool:
    return not (
        _authorized_repository(session, ProjectPhase, access).list(access.project_id)
        or _authorized_repository(session, Task, access).list(access.project_id)
        or _authorized_repository(session, Material, access).list(access.project_id)
    )


def _at_utc(value: date | None) -> datetime | None:
    return None if value is None else datetime.combine(value, time.min, tzinfo=UTC)


__all__ = [
    "ProjectImportAlreadyCommittedError",
    "ProjectImportConfirmationError",
    "ProjectImportResult",
    "ProjectImportService",
]
