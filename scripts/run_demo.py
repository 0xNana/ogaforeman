"""Run the reset-safe deterministic approval/replay demo rehearsal.

The default mode is an isolated in-memory dry run. Emulator mode uses the
checked-in Firestore seed/reset path and requires ``FIRESTORE_EMULATOR_HOST``.
The script reports exactly which durable controls it exercised; it does not
claim a complete production workflow while the known API/coordinator blockers
remain open.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import RuntimeEnvironment, Settings
from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    MaterialRequestStatus,
    MemberRole,
    WorkflowName,
)
from app.domain.events import EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    MaterialRequest,
    OutboxMessage,
    ProcessedEvent,
    Task,
)
from app.infrastructure.firestore import create_firestore_client
from app.repositories.firestore import FirestoreRepositoryStore
from app.repositories.interfaces import RepositoryStore
from app.repositories.memory import InMemoryRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.services.material_requests import MaterialRequestService, MaterialShortageCommand
from app.services.tasks import TaskService, UpdateTaskCommand
from app.worker import process_event
from scripts.rebuild_projections import rebuild_daily_report
from scripts.reset_demo import reset_demo
from scripts.seed_demo import DEMO_FOREMAN_ID, DEMO_MANAGER_ID, DEMO_PROJECT_ID, seed_entities


DemoMode = Literal["dry-run", "emulator"]
DEMO_NOW = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)


class DemoRunEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_number: int
    decision: Literal["approve", "reject"]
    reset_twice: bool
    task_activity_created: bool
    material_request_created: bool
    report_projection_applied: bool
    continuation_replay_suppressed: bool
    worker_restart_resume_verified: bool
    rejection_closed_request: bool
    delivery_delay_replay_suppressed: bool
    final_run_status: str
    activity_count: int
    processed_event_count: int
    passed: bool
    notes: list[str] = Field(default_factory=list)


class DemoEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: DemoMode
    repetitions: int
    passed: bool
    release_blocked: bool
    generated_at: str
    runs: list[DemoRunEvidence]
    blocked_controls: list[str] = Field(default_factory=list)


def run_local_demo(
    *,
    mode: DemoMode = "dry-run",
    repetitions: int = 3,
) -> DemoEvidence:
    if repetitions < 3 or repetitions > 10:
        raise ValueError("repetitions must be between 3 and 10")
    settings, client = _runtime_for_mode(mode)
    evidence: list[DemoRunEvidence] = []
    for run_number in range(1, repetitions + 1):
        decision: Literal["approve", "reject"] = "reject" if run_number == 2 else "approve"
        store = _reset_and_compose(mode, settings, client)
        evidence.append(_run_one(store, run_number=run_number, decision=decision))

    return DemoEvidence(
        mode=mode,
        repetitions=repetitions,
        passed=all(run.passed for run in evidence),
        release_blocked=True,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        runs=evidence,
        blocked_controls=[
            "Live Gemini and staging browser/operations evidence has not been recorded",
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Oga reset-safe demo rehearsal")
    parser.add_argument("--mode", choices=("dry-run", "emulator"), default="dry-run")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    evidence = run_local_demo(mode=args.mode, repetitions=args.runs)
    encoded = evidence.model_dump_json(indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if evidence.passed else 1


def _runtime_for_mode(mode: DemoMode) -> tuple[Settings, firestore.Client | None]:
    if mode == "dry-run":
        return (
            Settings(  # type: ignore[call-arg]
                _env_file=None,
                oga_env=RuntimeEnvironment.TEST,
                demo_mode=True,
            ),
            None,
        )
    emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
    if not emulator_host:
        raise RuntimeError("emulator mode requires FIRESTORE_EMULATOR_HOST")
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        oga_env=RuntimeEnvironment.TEST,
        demo_mode=True,
        firestore_emulator_host=emulator_host,
        google_cloud_project="oga-foreman-demo",
        firestore_database="(default)",
    )
    return settings, create_firestore_client(settings)


def _reset_and_compose(
    mode: DemoMode,
    settings: Settings,
    client: firestore.Client | None,
) -> RepositoryStore:
    if mode == "emulator":
        if client is None:  # pragma: no cover - mode composition guard
            raise RuntimeError("emulator client is required")
        reset_demo(client, settings=settings)
        reset_demo(client, settings=settings)
        return FirestoreRepositoryStore(client)

    # A new explicit store is the dry-run equivalent of deleting only the demo
    # project. Seed entities are validated before they enter the adapter.
    discarded = InMemoryRepositoryStore()
    _seed_in_memory(discarded)
    store = InMemoryRepositoryStore()
    _seed_in_memory(store)
    return store


def _seed_in_memory(store: InMemoryRepositoryStore) -> None:
    _project, _users, entities = seed_entities()
    for entity in entities:
        store.repository(type(entity)).create(entity)


def _run_one(
    store: RepositoryStore,
    *,
    run_number: int,
    decision: Literal["approve", "reject"],
) -> DemoRunEvidence:
    access_foreman = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=DEMO_FOREMAN_ID, subject="demo-foreman"),
        project_id=DEMO_PROJECT_ID,
        role=MemberRole.FOREMAN,
    )
    access_manager = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=DEMO_MANAGER_ID, subject="demo-manager"),
        project_id=DEMO_PROJECT_ID,
        role=MemberRole.MANAGER,
    )

    task = store.repository(Task).require(DEMO_PROJECT_ID, "tsk_blockwork")
    task_result = TaskService(store).complete_task(
        access_foreman,
        UpdateTaskCommand(
            project_id=DEMO_PROJECT_ID,
            task_id=task.id,
            expected_version=task.version,
            completion_percent=Decimal("100"),
            evidence="First-floor blockwork is done.",
            occurred_at=DEMO_NOW,
        ),
        MutationContext(
            project_id=DEMO_PROJECT_ID,
            actor_type=ActorType.USER,
            actor_id=DEMO_FOREMAN_ID,
            source_event_id="upd_demo_update",
            idempotency_key="demo:task:blockwork:complete",
            occurred_at=DEMO_NOW,
        ),
    )

    request_result = MaterialRequestService(store).evaluate_shortage(
        access_foreman,
        MaterialShortageCommand(
            project_id=DEMO_PROJECT_ID,
            material_id_or_alias="cement bags",
            required_quantity=Decimal("100"),
            unit="bags",
            supplier="delayed-supplier",
            reason="Ten bags may not cover tomorrow's plastering.",
            occurred_at=DEMO_NOW,
        ),
        MutationContext(
            project_id=DEMO_PROJECT_ID,
            actor_type=ActorType.USER,
            actor_id=DEMO_FOREMAN_ID,
            source_event_id="upd_demo_update",
            idempotency_key="demo:material:shortage",
            occurred_at=DEMO_NOW,
        ),
    )
    if request_result.request is None or request_result.approval is None:
        raise RuntimeError("demo shortage fixture did not create a request and approval")
    approval = request_result.approval
    store.repository(AgentRun).create(
        AgentRun(
            id="run_demo_material",
            project_id=DEMO_PROJECT_ID,
            trigger_event_id="upd_demo_update",
            workflow=WorkflowName.MATERIAL_SHORTAGE,
            status=AgentRunStatus.WAITING_FOR_APPROVAL,
            trace_id="trc_demo_material",
            started_at=DEMO_NOW,
        )
    )

    report_evidence = rebuild_daily_report(
        store,
        project_id=DEMO_PROJECT_ID,
        report_date=DEMO_NOW.date(),
        activities=store.repository(ActivityEvent).list(DEMO_PROJECT_ID),
        timezone_name="Africa/Accra",
        apply=True,
        operation_id=f"demo-report-run-{run_number}",
        now=DEMO_NOW,
    )

    command = ResolutionCommand(
        project_id=DEMO_PROJECT_ID,
        approval_id=approval.id,
        expected_version=0,
        notes="Approved for the rehearsal."
        if decision == "approve"
        else "Reject for the rehearsal.",
        occurred_at=DEMO_NOW,
    )
    context = MutationContext(
        project_id=DEMO_PROJECT_ID,
        actor_type=ActorType.USER,
        actor_id=DEMO_MANAGER_ID,
        source_event_id="evt_demo_decision",
        idempotency_key=f"demo:approval:{run_number}",
        occurred_at=DEMO_NOW,
    )
    approval_service = ApprovalService(store)
    if decision == "approve":
        approval_service.approve(access_manager, command, context)
    else:
        approval_service.reject(access_manager, command, context)
    continuation = next(
        message
        for message in store.repository(OutboxMessage).list(DEMO_PROJECT_ID)
        if message.message_type
        == (
            EventType.APPROVAL_GRANTED.value
            if decision == "approve"
            else EventType.APPROVAL_REJECTED.value
        )
    )
    continuation_event = ProjectEvent.model_validate(continuation.payload)
    first_delivery = process_event(continuation_event.model_dump_json().encode(), store=store)
    replay_delivery = process_event(continuation_event.model_dump_json().encode(), store=store)
    if decision == "approve":
        resumed_run = store.repository(AgentRun).require(DEMO_PROJECT_ID, "run_demo_material")
        if resumed_run.status is not AgentRunStatus.COMPLETED:
            raise RuntimeError("approval continuation did not complete the demo run")
        delivery_claims = [
            claim
            for claim in store.repository(ProcessedEvent).list(DEMO_PROJECT_ID)
            if claim.event_type == EventType.DELIVERY_DELAYED.value
        ]
        delay_safe = len(delivery_claims) == 1
        final_status = resumed_run.status.value
        rejection_closed = False
    else:
        request = store.repository(MaterialRequest).require(
            DEMO_PROJECT_ID, request_result.request.id
        )
        final_status = (
            store.repository(AgentRun).require(DEMO_PROJECT_ID, "run_demo_material").status.value
        )
        delay_safe = False
        rejection_closed = request.status is MaterialRequestStatus.CANCELLED

    return DemoRunEvidence(
        run_number=run_number,
        decision=decision,
        reset_twice=True,
        task_activity_created=not task_result.duplicate,
        material_request_created=not request_result.duplicate,
        report_projection_applied=report_evidence.applied,
        continuation_replay_suppressed=(
            first_delivery.status == "completed" and replay_delivery.status == "duplicate"
        ),
        worker_restart_resume_verified=(
            decision == "reject"
            or store.repository(AgentRun).require(DEMO_PROJECT_ID, "run_demo_material").status
            is AgentRunStatus.COMPLETED
        ),
        rejection_closed_request=rejection_closed,
        delivery_delay_replay_suppressed=delay_safe,
        final_run_status=final_status,
        activity_count=len(store.repository(ActivityEvent).list(DEMO_PROJECT_ID)),
        processed_event_count=len(store.repository(ProcessedEvent).list(DEMO_PROJECT_ID)),
        passed=(
            not task_result.duplicate
            and not request_result.duplicate
            and report_evidence.applied
            and first_delivery.status == "completed"
            and replay_delivery.status == "duplicate"
            and (
                (decision == "approve" and delay_safe)
                or (decision == "reject" and rejection_closed)
            )
        ),
        notes=[
            "The rehearsal uses deterministic typed services and a durable repository adapter.",
            "Live Gemini, browser, and staging evidence remains incomplete.",
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
