from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from collections.abc import Callable
from collections import Counter
from typing import Generic, TypeVar, cast

import pytest
from pydantic import BaseModel

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import MemberRole, ProjectStatus, TaskStatus
from app.domain.import_records import (
    ImportProvenance,
    MaterialRequirement,
    ProjectImportRecord,
    ProjectPhase,
    ProjectSource,
)
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import ActivityEvent, Material, Project, Task
from app.domain.project_import import (
    DraftTaskStatus,
    ImportConflict,
    ProjectImportDraft,
    ProjectImportStatus,
    SourceType,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.repositories.interfaces import (
    EntityAlreadyExistsError,
    ProjectRepository,
    RepositorySession,
)
from app.repositories.interfaces import VersionConflictError
from app.repositories.firestore import (
    FirestoreRepository,
    firestore_collection_name,
    firestore_document_data,
)
from app.services.project_import import ProjectImportService, _canonical_id
from app.services.project_import import ProjectImportConfirmationError
from app.services.project_import_validation import (
    ProjectImportValidationError,
    ProjectImportValidator,
)
from app.services.project_sources import ProjectSourceService


ResultT = TypeVar("ResultT")
EntityT = TypeVar("EntityT", bound=BaseModel)


class MutationCountingRepository(Generic[EntityT]):
    def __init__(self, delegate: ProjectRepository[EntityT], counter: list[int]) -> None:
        self._delegate = delegate
        self._counter = counter

    def get(self, project_id: str, entity_id: str) -> EntityT | None:
        return self._delegate.get(project_id, entity_id)

    def require(self, project_id: str, entity_id: str) -> EntityT:
        return self._delegate.require(project_id, entity_id)

    def list(self, project_id: str):
        return self._delegate.list(project_id)

    def create(self, entity: EntityT) -> EntityT:
        self._counter[0] += 1
        return self._delegate.create(entity)

    def save(self, entity: EntityT, *, expected_version: int | None = None) -> EntityT:
        self._counter[0] += 1
        return self._delegate.save(entity, expected_version=expected_version)

    def delete(
        self,
        project_id: str,
        entity_id: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        self._counter[0] += 1
        self._delegate.delete(project_id, entity_id, expected_version=expected_version)

    def version_of(self, project_id: str, entity_id: str) -> int | None:
        return self._delegate.version_of(project_id, entity_id)


class MutationCountingSession:
    def __init__(self, delegate: RepositorySession, counter: list[int]) -> None:
        self._delegate = delegate
        self._counter = counter

    def repository(self, entity_type: type[EntityT]) -> ProjectRepository[EntityT]:
        return cast(
            ProjectRepository[EntityT],
            MutationCountingRepository(self._delegate.repository(entity_type), self._counter),
        )


class MutationCountingImportStore(InMemoryRepositoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.commit_write_count: int | None = None

    def run_transaction(
        self,
        operation: Callable[[RepositorySession], ResultT],
    ) -> ResultT:
        is_canonical_commit = any(
            record.status is ProjectImportStatus.IMPORTING
            for record in self.repository(ProjectImportRecord).list("prj_commit123")
        )
        if not is_canonical_commit:
            return super().run_transaction(operation)
        counter = [0]
        result = super().run_transaction(
            lambda session: operation(MutationCountingSession(session, counter))
        )
        self.commit_write_count = counter[0]
        return result


class RecordingImportStore(InMemoryRepositoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.import_statuses: list[ProjectImportStatus] = []

    def run_transaction(
        self,
        operation: Callable[[RepositorySession], ResultT],
    ) -> ResultT:
        result = super().run_transaction(operation)
        records = self.repository(ProjectImportRecord).list("prj_commit123")
        if records:
            status = records[0].status
            if not self.import_statuses or self.import_statuses[-1] is not status:
                self.import_statuses.append(status)
        return result


class CanonicalRaceImportStore(InMemoryRepositoryStore):
    """Inject canonical state after the import claim but before commit preflight."""

    def __init__(self) -> None:
        super().__init__()
        self.armed = False
        self.injected = False

    def run_transaction(
        self,
        operation: Callable[[RepositorySession], ResultT],
    ) -> ResultT:
        records = self.repository(ProjectImportRecord).list("prj_commit123")
        if (
            self.armed
            and not self.injected
            and any(record.status is ProjectImportStatus.IMPORTING for record in records)
        ):
            self.repository(Task).create(
                Task(
                    id="tsk_concurrent123",
                    project_id="prj_commit123",
                    title="Foundation",
                )
            )
            self.injected = True
        return super().run_transaction(operation)


def _confirmed_draft() -> ProjectImportDraft:
    return ProjectImportDraft(
        id="imp_commit123",
        project_id="prj_commit123",
        source_id="src_commit123",
        status=ProjectImportStatus.CONFIRMED,
        confirmed_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
        project={"name": "Imported residence"},
        phases=[{"temp_id": "tmp_phase_one", "name": "Substructure", "sequence": 1}],
        tasks=[
            {
                "temp_id": "tmp_task_foundation",
                "name": "Foundation",
                "phase_temp_id": "tmp_phase_one",
                "planned_start": date(2026, 8, 20),
                "planned_finish": date(2026, 8, 30),
                "source_reference": {
                    "source_id": "src_commit123",
                    "source_type": SourceType.MARKDOWN,
                    "source_name": "plan.md",
                },
            }
        ],
        materials=[
            {
                "temp_id": "tmp_material_cement",
                "name": "Cement Bags",
                "canonical_unit": "bags",
                "initial_on_hand_quantity": Decimal("20"),
                "source_reference": {
                    "source_id": "src_commit123",
                    "source_type": SourceType.MARKDOWN,
                    "source_name": "plan.md",
                },
            }
        ],
        material_requirements=[
            {
                "task_temp_id": "tmp_task_foundation",
                "material_temp_id": "tmp_material_cement",
                "required_quantity": Decimal("100"),
                "unit": "bags",
                "source_reference": {
                    "source_id": "src_commit123",
                    "source_type": SourceType.MARKDOWN,
                    "source_name": "plan.md",
                },
            }
        ],
    )


def test_confirmed_import_commits_canonical_records_and_replays_idempotently() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )

    service = ProjectImportService(store)
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    draft = _confirmed_draft()
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    first = service.import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-direct",
    )
    replay = service.import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-direct",
    )

    assert not first.replayed
    assert replay.replayed
    assert len(store.repository(ProjectPhase).list("prj_commit123")) == 1
    assert len(store.repository(Task).list("prj_commit123")) == 1
    assert len(store.repository(Material).list("prj_commit123")) == 1
    assert len(store.repository(MaterialRequirement).list("prj_commit123")) == 1
    assert len(store.repository(ImportProvenance).list("prj_commit123")) == 5
    assert len(store.repository(MaterialLedgerEntry).list("prj_commit123")) == 1
    assert (
        store.repository(ProjectImportRecord).require("prj_commit123", "imp_commit123").status
        == "imported"
    )
    assert {
        activity.action for activity in store.repository(ActivityEvent).list("prj_commit123")
    } == {
        "project.source.created",
        "project.import.started",
        "project.import.reviewed",
        "task.created",
        "material.created",
        "material.requirement.created",
        "project.initialized",
    }
    activities = {
        activity.action: activity
        for activity in store.repository(ActivityEvent).list("prj_commit123")
    }
    assert activities["task.created"].entity_type == "task"
    assert activities["material.created"].entity_type == "material"
    assert activities["material.requirement.created"].entity_type == "material_requirement"
    assert activities["project.initialized"].entity_type == "project_import"
    for action in ("task.created", "material.created", "material.requirement.created"):
        assert activities[action].metadata["import_id"] == draft.id
        assert activities[action].metadata["source_id"] == draft.source_id


def test_first_import_applies_reviewed_project_metadata_atomically() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    store.repository(Project).create(
        Project(
            id="prj_commit123",
            name="Ridge plan",
            location="Not specified",
            timezone="Africa/Accra",
            created_by="usr_admin123",
        )
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="ridge-plan.md",
        text="# Ridge House\nLocation: East Legon",
    )
    draft_data = _confirmed_draft().model_dump()
    draft_data["project"] = {
        "name": "Ridge House",
        "description": "Three-bedroom residential build",
        "location": "East Legon, Accra",
        "start_date": date(2026, 9, 1),
        "target_end_date": date(2027, 4, 30),
        "status": ProjectStatus.ACTIVE,
    }
    draft = ProjectImportDraft.model_validate(draft_data)
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-project-metadata",
    )

    project = store.repository(Project).require(draft.project_id, draft.project_id)
    assert project.name == "Ridge House"
    assert project.location == "East Legon, Accra"
    assert project.description == "Three-bedroom residential build"
    assert project.start_date == date(2026, 9, 1)
    assert project.target_end_date == date(2027, 4, 30)
    assert project.status is ProjectStatus.ACTIVE
    assert project.timezone == "Africa/Accra"


def test_prepared_plan_count_matches_writes_attempted_by_commit_transaction() -> None:
    draft_data = _confirmed_draft().model_dump()
    draft_data["tasks"].append(
        {
            "temp_id": "tmp_task_wall",
            "name": "Walling",
            "source_reference": draft_data["tasks"][0]["source_reference"],
        }
    )
    draft_data["dependencies"] = [
        {
            "predecessor_temp_id": "tmp_task_foundation",
            "successor_temp_id": "tmp_task_wall",
            "source_reference": draft_data["tasks"][0]["source_reference"],
        }
    ]
    draft = ProjectImportDraft.model_validate(draft_data)
    plan = ProjectImportValidator().validate(draft).plan
    store = MutationCountingImportStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id=draft.project_id,
        role=MemberRole.ADMIN,
    )
    store.repository(Project).create(
        Project(
            id=draft.project_id,
            name="Imported residence",
            location="Not specified",
            timezone="Africa/Accra",
            created_by=access.actor.user_id,
        )
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id=draft.source_id,
        name="plan.md",
        text="# Imported residence\nFoundation precedes walling.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-counted-plan",
    )

    assert store.commit_write_count == plan.commit_write_count
    dependency = next(
        activity
        for activity in store.repository(ActivityEvent).list(draft.project_id)
        if activity.action == "dependency.created"
    )
    assert dependency.entity_type == "dependency"
    assert dependency.entity_id.startswith("dep_")
    assert {
        key: dependency.metadata[key]
        for key in (
            "predecessor_task_id",
            "successor_task_id",
            "import_id",
            "source_id",
        )
    } == {
        "predecessor_task_id": _canonical_id("tsk", draft.id, "tmp_task_foundation"),
        "successor_task_id": _canonical_id("tsk", draft.id, "tmp_task_wall"),
        "import_id": draft.id,
        "source_id": draft.source_id,
    }


def test_confirmation_persists_confirmed_and_importing_before_canonical_commit() -> None:
    store = RecordingImportStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    draft = _confirmed_draft()
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-lifecycle",
    )

    assert store.import_statuses[-3:] == [
        ProjectImportStatus.CONFIRMED,
        ProjectImportStatus.IMPORTING,
        ProjectImportStatus.IMPORTED,
    ]


@pytest.mark.parametrize(
    "restart_status",
    [ProjectImportStatus.CONFIRMED, ProjectImportStatus.IMPORTING],
)
def test_exact_confirmation_claim_resumes_after_restart(
    restart_status: ProjectImportStatus,
) -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    draft = _confirmed_draft()
    key = "confirm-restart"
    expected_version = 0
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=restart_status,
            draft=draft,
            confirmed_at=draft.confirmed_at,
            decision_action="confirm",
            decision_idempotency_key=key,
            decision_request_fingerprint=sha256(
                f"confirm\x00{key}\x00{expected_version}".encode()
            ).hexdigest(),
            decision_expected_version=expected_version,
        )
    )

    result = ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=expected_version,
        decision_idempotency_key=key,
    )

    assert not result.replayed
    assert store.repository(ProjectImportRecord).require(draft.project_id, draft.id).status is (
        ProjectImportStatus.IMPORTED
    )
    assert len(store.repository(Task).list(draft.project_id)) == 1


def test_import_failed_retry_requires_the_exact_original_confirmation_claim() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    draft = _confirmed_draft()
    key = "confirm-failed-retry"
    expected_version = 0
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.IMPORT_FAILED,
            draft=draft,
            confirmed_at=draft.confirmed_at,
            decision_action="confirm",
            decision_idempotency_key=key,
            decision_request_fingerprint=sha256(
                f"confirm\x00{key}\x00{expected_version}".encode()
            ).hexdigest(),
            decision_expected_version=expected_version,
            failure_code="import_commit_failed",
            failure_message="Project import commit failed and can be retried.",
        )
    )

    with pytest.raises(VersionConflictError):
        ProjectImportService(store).import_confirmed(
            draft,
            access,
            expected_review_version=expected_version,
            decision_idempotency_key="different-confirmation-claim",
        )

    result = ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=expected_version,
        decision_idempotency_key=key,
    )

    assert not result.replayed
    assert store.repository(ProjectImportRecord).require(draft.project_id, draft.id).status is (
        ProjectImportStatus.IMPORTED
    )


def test_direct_import_service_rejects_persisted_conflicts_before_writes() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    draft = _confirmed_draft().model_copy(
        update={
            "conflicts": [
                ImportConflict(
                    code="EXISTING_TASK_POSSIBLE_MATCH",
                    message="Review the possible existing task match.",
                )
            ]
        }
    )

    with pytest.raises(ProjectImportValidationError) as exc_info:
        ProjectImportService(store).import_confirmed(
            draft,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-conflicted-direct",
        )

    assert [error.code for error in exc_info.value.errors] == ["EXISTING_TASK_POSSIBLE_MATCH"]
    assert store.repository(Task).list(draft.project_id) == ()
    assert store.repository(Material).list(draft.project_id) == ()


def test_active_project_initialization_preserves_actual_state_without_history() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="site-state.md",
        text="Site clearance and excavation are complete; foundation is under way.",
    )
    draft = ProjectImportDraft.model_validate(
        {
            "id": "imp_actual123",
            "project_id": access.project_id,
            "source_id": "src_commit123",
            "status": ProjectImportStatus.CONFIRMED,
            "confirmed_at": datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
            "project": {"name": "Mid-project residence", "status": ProjectStatus.ACTIVE},
            "tasks": [
                {
                    "temp_id": "tmp_task_clearance",
                    "name": "Site Clearance",
                    "initial_status": DraftTaskStatus.COMPLETED,
                    "actual_completion": date(2026, 8, 10),
                },
                {
                    "temp_id": "tmp_task_excavation",
                    "name": "Excavation",
                    "initial_status": DraftTaskStatus.COMPLETED,
                    "actual_completion": date(2026, 8, 12),
                },
                {
                    "temp_id": "tmp_task_foundation",
                    "name": "Foundation",
                    "initial_status": DraftTaskStatus.IN_PROGRESS,
                },
                {
                    "temp_id": "tmp_task_blockwork",
                    "name": "Blockwork",
                    "initial_status": DraftTaskStatus.PLANNED,
                },
                {
                    "temp_id": "tmp_task_electrical",
                    "name": "Electrical rough-in",
                    "initial_status": DraftTaskStatus.BLOCKED,
                },
            ],
            "materials": [
                {
                    "temp_id": "tmp_material_cement",
                    "name": "Cement",
                    "canonical_unit": "bags",
                    "initial_on_hand_quantity": Decimal("10"),
                }
            ],
        }
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-actual-state",
    )

    tasks_by_title = {task.title: task for task in store.repository(Task).list(access.project_id)}
    assert tasks_by_title["Site Clearance"].status is TaskStatus.COMPLETED
    assert tasks_by_title["Site Clearance"].actual_completion == datetime(2026, 8, 10, tzinfo=UTC)
    assert tasks_by_title["Excavation"].status is TaskStatus.COMPLETED
    assert tasks_by_title["Foundation"].status is TaskStatus.IN_PROGRESS
    assert tasks_by_title["Foundation"].actual_completion is None
    assert tasks_by_title["Blockwork"].status is TaskStatus.PLANNED
    assert tasks_by_title["Blockwork"].actual_completion is None
    assert tasks_by_title["Electrical rough-in"].status is TaskStatus.BLOCKED
    assert tasks_by_title["Electrical rough-in"].actual_completion is None

    material = store.repository(Material).list(access.project_id)[0]
    ledger_entry = store.repository(MaterialLedgerEntry).list(access.project_id)[0]
    assert material.available_quantity == Decimal("10")
    assert ledger_entry.quantity_delta == Decimal("10")
    assert ledger_entry.reason == "Initial inventory from confirmed project import."
    assert {
        activity.action for activity in store.repository(ActivityEvent).list(access.project_id)
    } == {
        "project.source.created",
        "project.import.reviewed",
        "project.import.started",
        "task.created",
        "material.created",
        "project.initialized",
    }


def test_distinct_import_of_the_same_logical_plan_is_blocked() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    service = ProjectImportService(store)

    first = _confirmed_draft()
    ProjectSourceService(store).persist_text(
        access,
        source_id=first.source_id,
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=first.id,
            project_id=first.project_id,
            source_id=first.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=first.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    service.import_confirmed(
        first,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-first-plan",
    )

    second_data = first.model_dump()
    second_data.update({"id": "imp_duplicate123", "source_id": "src_duplicate123"})
    for item in (
        *second_data["tasks"],
        *second_data["materials"],
        *second_data["material_requirements"],
    ):
        if item["source_reference"] is not None:
            item["source_reference"]["source_id"] = "src_duplicate123"
    second = ProjectImportDraft.model_validate(second_data)
    ProjectSourceService(store).persist_text(
        access,
        source_id=second.source_id,
        name="plan-copy.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=second.id,
            project_id=second.project_id,
            source_id=second.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=second.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    with pytest.raises(ProjectImportConfirmationError):
        service.import_confirmed(
            second,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-duplicate-plan",
        )

    assert len(store.repository(Task).list(access.project_id)) == 1
    assert len(store.repository(Material).list(access.project_id)) == 1
    assert len(store.repository(MaterialRequirement).list(access.project_id)) == 1


def test_distinct_import_with_only_new_entities_is_committed_additively() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    service = ProjectImportService(store)
    first = _confirmed_draft()
    ProjectSourceService(store).persist_text(
        access,
        source_id=first.source_id,
        name="plan.md",
        text="Foundation requires 100 bags of cement.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=first.id,
            project_id=first.project_id,
            source_id=first.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=first.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    service.import_confirmed(
        first,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-first-additive-plan",
    )
    original_task = store.repository(Task).list(access.project_id)[0]
    original_material = store.repository(Material).list(access.project_id)[0]

    second_data = first.model_dump()
    second_data.update({"id": "imp_additive123", "source_id": "src_additive123"})
    second_data["phases"] = [{"temp_id": "tmp_phase_finishes", "name": "Finishes", "sequence": 2}]
    second_data["tasks"] = [
        {
            "temp_id": "tmp_task_painting",
            "name": "Painting",
            "phase_temp_id": "tmp_phase_finishes",
        }
    ]
    second_data["materials"] = [
        {
            "temp_id": "tmp_material_paint",
            "name": "Emulsion paint",
            "canonical_unit": "litres",
            "initial_on_hand_quantity": Decimal("0"),
        }
    ]
    second_data["material_requirements"] = [
        {
            "task_temp_id": "tmp_task_painting",
            "material_temp_id": "tmp_material_paint",
            "required_quantity": Decimal("40"),
            "unit": "litres",
        }
    ]
    second = ProjectImportDraft.model_validate(second_data)
    ProjectSourceService(store).persist_text(
        access,
        source_id=second.source_id,
        name="finishes.md",
        text="Painting requires 40 litres of emulsion paint.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=second.id,
            project_id=second.project_id,
            source_id=second.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=second.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    result = service.import_confirmed(
        second,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-additive-plan",
    )

    assert not result.replayed
    assert len(store.repository(Task).list(access.project_id)) == 2
    assert len(store.repository(Material).list(access.project_id)) == 2
    assert len(store.repository(MaterialRequirement).list(access.project_id)) == 2
    assert store.repository(Task).require(access.project_id, original_task.id) == original_task
    assert (
        store.repository(Material).require(access.project_id, original_material.id)
        == original_material
    )


def test_commit_transaction_rechecks_preflight_after_concurrent_canonical_write() -> None:
    store = CanonicalRaceImportStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    draft = _confirmed_draft()
    ProjectSourceService(store).persist_text(
        access,
        source_id=draft.source_id,
        name="plan.md",
        text="Foundation requires 100 bags of cement.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    store.armed = True

    with pytest.raises(ProjectImportConfirmationError, match="canonical project state"):
        ProjectImportService(store).import_confirmed(
            draft,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-raced-plan",
        )

    assert store.injected
    assert [task.id for task in store.repository(Task).list(access.project_id)] == [
        "tsk_concurrent123"
    ]
    assert store.repository(Material).list(access.project_id) == ()
    failed = store.repository(ProjectImportRecord).require(access.project_id, draft.id)
    assert failed.status is ProjectImportStatus.IMPORT_FAILED
    assert failed.failure_code == "canonical_preflight_conflict"


def test_import_provenance_uses_trusted_source_and_canonical_target_links() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    persisted_source = (
        ProjectSourceService(store)
        .persist_text(
            access,
            source_id="src_commit123",
            name="plan.md",
            text="# Imported residence\nFoundation requires 100 bags.",
        )
        .source
    )
    draft_data = _confirmed_draft().model_dump()
    for item in (
        *draft_data["tasks"],
        *draft_data["materials"],
        *draft_data["material_requirements"],
    ):
        if item["source_reference"] is not None:
            item["source_reference"].update(
                {
                    "source_type": SourceType.EXTERNAL,
                    "source_name": "forged-source.xlsx",
                    "imported_at": datetime(2000, 1, 1, tzinfo=UTC),
                }
            )
    draft = ProjectImportDraft.model_validate(draft_data)
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-trusted-provenance",
    )

    provenance = store.repository(ImportProvenance).list(access.project_id)
    assert {item.source_name for item in provenance} == {persisted_source.name}
    assert {item.source_type for item in provenance} == {persisted_source.type.value}
    assert {item.source_checksum for item in provenance} == {persisted_source.checksum}
    assert {item.source_id for item in provenance} == {persisted_source.id}
    assert {item.imported_by for item in provenance} == {access.actor.user_id}
    assert {item.target_entity_type for item in provenance} == {
        "project_phase",
        "task",
        "material",
        "material_ledger_entry",
        "material_requirement",
    }
    assert all(item.target_entity_id for item in provenance)
    imported_record = store.repository(ProjectImportRecord).require(access.project_id, draft.id)
    assert imported_record.confirmed_at is not None
    assert {item.imported_at for item in provenance} == {imported_record.confirmed_at}

    task = store.repository(Task).list(access.project_id)[0]
    requirement = store.repository(MaterialRequirement).list(access.project_id)[0]
    task_provenance = next(
        item
        for item in provenance
        if item.target_entity_type == "task" and item.target_entity_id == task.id
    )
    requirement_provenance = next(
        item
        for item in provenance
        if item.target_entity_type == "material_requirement"
        and item.target_entity_id == requirement.id
    )
    assert task.source_refs == [task_provenance.id]
    assert requirement.source_provenance_id == requirement_provenance.id


def test_import_rejects_a_forged_provenance_source_identity() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    draft_data = _confirmed_draft().model_dump()
    draft_data["tasks"][0]["source_reference"]["source_id"] = "src_forged123"
    draft = ProjectImportDraft.model_validate(draft_data)

    with pytest.raises(ProjectImportConfirmationError):
        ProjectImportService(store).import_confirmed(
            draft,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-forged-source-id",
        )

    assert store.repository(ImportProvenance).list(access.project_id) == ()
    assert store.repository(Task).list(access.project_id) == ()


def test_import_provenance_covers_every_created_fact_with_synthesized_links() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="trusted-plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    draft_data = _confirmed_draft().model_dump()
    draft_data["tasks"].append(
        {
            "temp_id": "tmp_task_blockwork",
            "name": "Blockwork",
            "phase_temp_id": "tmp_phase_one",
        }
    )
    draft_data["dependencies"] = [
        {
            "predecessor_temp_id": "tmp_task_foundation",
            "successor_temp_id": "tmp_task_blockwork",
        }
    ]
    draft_data["milestones"] = [
        {
            "temp_id": "tmp_milestone_handover",
            "name": "Handover",
            "planned_date": date(2026, 9, 1),
        }
    ]
    draft = ProjectImportDraft.model_validate(draft_data)
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-complete-provenance",
    )

    provenance = store.repository(ImportProvenance).list(access.project_id)
    assert Counter(item.target_entity_type.value for item in provenance) == Counter(
        {
            "project_phase": 1,
            "task": 3,
            "dependency": 1,
            "material": 1,
            "material_ledger_entry": 1,
            "material_requirement": 1,
        }
    )
    imported = store.repository(ProjectImportRecord).require(access.project_id, draft.id)
    assert imported.confirmed_at is not None
    assert {item.imported_at for item in provenance} == {imported.confirmed_at}
    assert all(item.source_id == draft.source_id for item in provenance)
    assert all(item.import_id == draft.id for item in provenance)

    provenance_by_id = {item.id: item for item in provenance}
    tasks = store.repository(Task).list(access.project_id)
    phases = store.repository(ProjectPhase).list(access.project_id)
    materials = store.repository(Material).list(access.project_id)
    ledger = store.repository(MaterialLedgerEntry).list(access.project_id)
    requirements = store.repository(MaterialRequirement).list(access.project_id)
    targets_by_type = {
        target_type: {
            item.target_entity_id
            for item in provenance
            if item.target_entity_type.value == target_type
        }
        for target_type in {
            "project_phase",
            "task",
            "material",
            "material_ledger_entry",
            "material_requirement",
        }
    }
    assert targets_by_type["project_phase"] == {item.id for item in phases}
    assert targets_by_type["task"] == {item.id for item in tasks}
    assert targets_by_type["material"] == {item.id for item in materials}
    assert targets_by_type["material_ledger_entry"] == {item.id for item in ledger}
    assert targets_by_type["material_requirement"] == {item.id for item in requirements}
    assert all(task.source_refs for task in tasks)
    for task in tasks:
        assert all(reference in provenance_by_id for reference in task.source_refs)
    requirement = requirements[0]
    assert requirement.source_provenance_id in provenance_by_id


def test_confirmed_import_requires_the_persisted_review_record() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )

    with pytest.raises(ProjectImportConfirmationError):
        ProjectImportService(store).import_confirmed(
            _confirmed_draft(),
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-direct",
        )


def test_confirmed_import_rejects_cross_source_provenance() -> None:
    draft_data = _confirmed_draft().model_dump()
    draft_data["tasks"][0]["source_reference"]["source_id"] = "src_other123"
    draft = ProjectImportDraft.model_validate(draft_data)
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )

    with pytest.raises(ProjectImportConfirmationError, match="provenance"):
        ProjectImportService(store).import_confirmed(
            draft,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-provenance",
        )


def test_confirmed_import_preserves_phase_material_and_milestone_fidelity() -> None:
    draft_data = _confirmed_draft().model_dump()
    draft_data["milestones"] = [
        {"temp_id": "tmp_milestone_roof", "name": "Roof complete", "planned_date": date(2026, 9, 1)}
    ]
    draft_data["materials"][0]["location"] = "Store A"
    draft_data["material_requirements"][0]["confidence"] = Decimal("0.8")
    draft = ProjectImportDraft.model_validate(draft_data)
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    from app.domain.import_records import ProjectImportRecord

    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    result = ProjectImportService(store).import_confirmed(
        draft,
        access,
        expected_review_version=0,
        decision_idempotency_key="confirm-fidelity",
    )

    assert result.task_count == 2
    tasks = store.repository(Task).list("prj_commit123")
    assert any(task.phase_id is not None for task in tasks)
    assert any(task.is_milestone for task in tasks)
    assert store.repository(Material).list("prj_commit123")[0].location == "Store A"
    requirement = store.repository(MaterialRequirement).list("prj_commit123")[0]
    assert requirement.confidence == Decimal("0.8")


def test_commit_failure_is_persisted_as_retryable_import_failed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _confirmed_draft()
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_admin123", subject="test"),
        project_id="prj_commit123",
        role=MemberRole.ADMIN,
    )
    ProjectSourceService(store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    store.repository(Task).create(
        Task(
            id=_canonical_id("tsk", draft.id, "tmp_task_foundation"),
            project_id=draft.project_id,
            title="Existing task",
        )
    )

    with pytest.raises(EntityAlreadyExistsError):
        ProjectImportService(store).import_confirmed(
            draft,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-failure",
        )

    failed = store.repository(ProjectImportRecord).require(draft.project_id, draft.id)
    assert failed.status is ProjectImportStatus.IMPORT_FAILED
    assert failed.failure_code == "import_commit_failed"
    assert failed.failure_message == "Project import commit failed and can be retried."
    assert store.repository(ProjectPhase).list(draft.project_id) == ()
    assert store.repository(Material).list(draft.project_id) == ()
    assert store.repository(MaterialRequirement).list(draft.project_id) == ()
    assert store.repository(MaterialLedgerEntry).list(draft.project_id) == ()
    assert store.repository(ImportProvenance).list(draft.project_id) == ()
    assert [task.title for task in store.repository(Task).list(draft.project_id)] == [
        "Existing task"
    ]
    actions = {
        activity.action for activity in store.repository(ActivityEvent).list(draft.project_id)
    }
    assert not actions.intersection(
        {
            "task.created",
            "dependency.created",
            "material.created",
            "material.requirement.created",
            "project.initialized",
        }
    )

    retry_store = InMemoryRepositoryStore()
    ProjectSourceService(retry_store).persist_text(
        access,
        source_id="src_commit123",
        name="plan.md",
        text="# Imported residence\nFoundation requires 100 bags.",
    )
    retry_store.repository(ProjectImportRecord).create(
        ProjectImportRecord(
            id=draft.id,
            project_id=draft.project_id,
            source_id=draft.source_id,
            status=ProjectImportStatus.NEEDS_REVIEW,
            draft=draft.model_copy(update={"status": ProjectImportStatus.NEEDS_REVIEW}),
        )
    )
    service = ProjectImportService(retry_store)

    def fail_preparation(_result: object, **_kwargs: object) -> object:
        raise RuntimeError("provider secret must not be persisted")

    monkeypatch.setattr(service, "_prepare_entities", fail_preparation)
    with pytest.raises(RuntimeError, match="provider secret"):
        service.import_confirmed(
            draft,
            access,
            expected_review_version=0,
            decision_idempotency_key="confirm-preparation-failure",
        )

    preparation_failed = retry_store.repository(ProjectImportRecord).require(
        draft.project_id, draft.id
    )
    assert preparation_failed.status is ProjectImportStatus.IMPORT_FAILED
    assert preparation_failed.failure_code == "import_commit_failed"
    assert preparation_failed.failure_message == "Project import commit failed and can be retried."


def test_import_records_have_firestore_collection_bindings() -> None:
    assert firestore_collection_name(Project) == "projects"
    assert firestore_collection_name(ProjectImportRecord) == "project_imports"
    assert firestore_collection_name(ImportProvenance) == "import_provenance"
    assert firestore_collection_name(MaterialRequirement) == "material_requirements"
    assert firestore_collection_name(ProjectPhase) == "project_phases"
    assert firestore_collection_name(ProjectSource) == "project_sources"


def test_top_level_project_writes_do_not_leak_repository_metadata() -> None:
    project = Project(
        id="prj_firestore123",
        name="Ridge House",
        location="East Legon",
        timezone="Africa/Accra",
        created_by="usr_admin123",
    )

    payload = firestore_document_data(project, version=1)

    assert payload["name"] == "Ridge House"
    assert "_repository_version" not in payload
    with pytest.raises(RuntimeError, match="project service"):
        FirestoreRepository(None, Project).create(project)


def test_project_import_record_round_trips_firestore_json_values() -> None:
    record = ProjectImportRecord(
        id="imp_firestore123",
        project_id="prj_firestore123",
        source_id="src_firestore123",
        status=ProjectImportStatus.NEEDS_REVIEW,
        extraction_idempotency_key="import-retry-key",
        extraction_request_fingerprint="a" * 64,
        extraction_session_id="imp_firestore123",
        extraction_invocation_id="extract:imp_firestore123",
        extraction_attempt=2,
        draft=ProjectImportDraft(
            id="imp_firestore123",
            project_id="prj_firestore123",
            source_id="src_firestore123",
            project={"name": "Firestore residence"},
            tasks=[{"temp_id": "tmp_task_foundation", "name": "Foundation"}],
        ),
    )
    payload = firestore_document_data(record, version=3)

    class Snapshot:
        def to_dict(self) -> dict[str, object]:
            return payload

    restored = FirestoreRepository(None, ProjectImportRecord)._decode_snapshot(Snapshot())

    assert restored.version == 3
    assert restored.status is ProjectImportStatus.NEEDS_REVIEW
    assert restored.draft is not None
    assert restored.draft.tasks[0].initial_status is DraftTaskStatus.PROPOSED
    assert restored.extraction_attempt == 2
    assert restored.extraction_session_id == "imp_firestore123"
