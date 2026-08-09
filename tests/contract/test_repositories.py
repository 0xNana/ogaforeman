from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest

from app.domain.enums import ActorType, TaskStatus
from app.domain.models import ActivityEvent, Task
from app.repositories.memory import InMemoryRepository, InMemoryRepositoryStore
from app.repositories.interfaces import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    VersionConflictError,
)


def make_task(
    task_id: str = "tsk_blockwork",
    *,
    project_id: str = "prj_ridge",
    completion_percent: Decimal = Decimal("0"),
) -> Task:
    return Task(
        id=task_id,
        project_id=project_id,
        title="First-floor blockwork",
        status=TaskStatus.PLANNED,
        completion_percent=completion_percent,
    )


def make_activity() -> ActivityEvent:
    return ActivityEvent(
        id="act_task001",
        project_id="prj_ridge",
        actor_type=ActorType.USER,
        actor_id="usr_manager",
        action="task.updated",
        entity_type="task",
        entity_id="tsk_blockwork",
        summary="Blockwork progress updated",
    )


def test_repository_instances_are_isolated_and_project_scoped() -> None:
    first = InMemoryRepository(Task)
    second = InMemoryRepository(Task)
    first.create(make_task())

    assert first.require("prj_ridge", "tsk_blockwork").id == "tsk_blockwork"
    assert first.get("prj_other", "tsk_blockwork") is None
    assert second.get("prj_ridge", "tsk_blockwork") is None


def test_repository_returns_copies_and_rejects_duplicate_create() -> None:
    repository = InMemoryRepository(Task)
    created = repository.create(make_task())
    created.completion_percent = Decimal("50")

    assert repository.require("prj_ridge", "tsk_blockwork").completion_percent == 0

    with pytest.raises(EntityAlreadyExistsError):
        repository.create(make_task())

    with pytest.raises(EntityNotFoundError):
        repository.require("prj_ridge", "tsk_unknown")


def test_create_requires_initial_version_and_list_order_is_deterministic() -> None:
    repository = InMemoryRepository(Task)

    with pytest.raises(VersionConflictError, match="version 0"):
        repository.create(make_task().model_copy(update={"version": 3}))

    repository.create(make_task("tsk_second"))
    repository.create(make_task("tsk_first"))

    assert [task.id for task in repository.list("prj_ridge")] == [
        "tsk_first",
        "tsk_second",
    ]


def test_save_requires_matching_version_and_increments_domain_version() -> None:
    repository = InMemoryRepository(Task)
    current = repository.create(make_task())
    updated = current.model_copy(update={"completion_percent": Decimal("50")})

    with pytest.raises(VersionConflictError, match="expected_version"):
        repository.save(updated)

    saved = repository.save(updated, expected_version=current.version)

    assert saved.version == current.version + 1
    assert repository.require("prj_ridge", "tsk_blockwork").completion_percent == 50

    with pytest.raises(VersionConflictError):
        repository.save(updated, expected_version=current.version)


def test_transaction_rolls_back_all_changes_on_error() -> None:
    repository = InMemoryRepository(Task)
    current = repository.create(make_task())

    def update_then_abort(transaction) -> None:
        transaction.save(
            current.model_copy(update={"completion_percent": Decimal("75")}),
            expected_version=current.version,
        )
        raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        repository.run_transaction(update_then_abort)

    assert repository.require("prj_ridge", "tsk_blockwork").completion_percent == 0
    assert repository.require("prj_ridge", "tsk_blockwork").version == current.version


def test_store_transaction_is_atomic_across_entity_collections() -> None:
    store = InMemoryRepositoryStore()
    tasks = store.repository(Task)
    activities = store.repository(ActivityEvent)
    current = tasks.create(make_task())

    def update_activity_then_abort(transaction) -> None:
        transaction.repository(Task).save(
            current.model_copy(update={"completion_percent": Decimal("75")}),
            expected_version=current.version,
        )
        transaction.repository(ActivityEvent).create(make_activity())
        raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        store.run_transaction(update_activity_then_abort)

    assert tasks.require("prj_ridge", "tsk_blockwork").completion_percent == 0
    assert activities.get("prj_ridge", "act_task001") is None


def test_concurrent_updates_allow_one_versioned_winner() -> None:
    repository = InMemoryRepository(Task)
    current = repository.create(make_task())
    snapshots = [repository.require("prj_ridge", "tsk_blockwork") for _ in range(2)]
    barrier = Barrier(2)

    def update(snapshot: Task, completion: str) -> Task:
        barrier.wait()
        return repository.save(
            snapshot.model_copy(update={"completion_percent": Decimal(completion)}),
            expected_version=snapshot.version,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(update, snapshots[0], "25"),
            executor.submit(update, snapshots[1], "50"),
        ]
        results = [future for future in futures]

    outcomes = [future.exception() for future in results]
    assert sum(isinstance(error, VersionConflictError) for error in outcomes) == 1
    assert sum(error is None for error in outcomes) == 1
    assert repository.require("prj_ridge", "tsk_blockwork").version == current.version + 1
