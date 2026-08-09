from datetime import UTC, datetime
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import ActorType, MemberRole, TaskStatus
from app.domain.models import ActivityEvent, Task
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.tasks import TaskService, UpdateTaskCommand


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for Firestore task integration",
    ),
]


def test_firestore_task_update_and_activity_survive_new_client() -> None:
    project = f"oga-task-test-{uuid4().hex}"
    project_id = "prj_ridge"
    now = datetime(2026, 8, 7, 13, 30, tzinfo=UTC)
    first_store = FirestoreRepositoryStore(firestore.Client(project=project))
    first_store.repository(Task).create(
        Task(
            id="tsk_blockwork",
            project_id=project_id,
            title="Blockwork",
            status=TaskStatus.IN_PROGRESS,
            completion_percent=Decimal("40"),
        )
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_foreman", subject="firebase-foreman"),
        project_id=project_id,
        role=MemberRole.FOREMAN,
    )
    context = MutationContext(
        project_id=project_id,
        actor_type=ActorType.AGENT,
        actor_id="agt_site_report",
        source_event_id="evt_update001",
        agent_run_id="run_update001",
        idempotency_key="task-update:evt_update001:tsk_blockwork",
        occurred_at=now,
    )
    command = UpdateTaskCommand(
        project_id=project_id,
        task_id="tsk_blockwork",
        expected_version=0,
        completion_percent=Decimal("75"),
        evidence="Foreman confirmed progress.",
        occurred_at=now,
    )

    changed = TaskService(first_store).update_task(access, command, context)
    replay = TaskService(first_store).update_task(access, command, context)

    restarted = FirestoreRepositoryStore(firestore.Client(project=project))
    assert changed.task.version == 1
    assert replay.duplicate is True
    assert restarted.repository(Task).require(project_id, "tsk_blockwork").completion_percent == 75
    assert len(restarted.repository(ActivityEvent).list(project_id)) == 1
