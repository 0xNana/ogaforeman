"""Run the deterministic local state-integrity capacity baseline.

This is not a substitute for deployed latency/load evidence. It exercises the
capacity envelope against isolated in-memory repositories so concurrency,
idempotency, and model limits regress in ordinary CI.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    ActorType,
    ApprovalActionType,
    ApprovalStatus,
    MemberRole,
    MemberStatus,
    SiteUpdateInputType,
    TaskStatus,
)
from app.domain.events import EventActor, EventActorType, EventSource, EventType, ProjectEvent
from app.domain.models import (
    ActivityEvent,
    Approval,
    OutboxMessage,
    ProcessedEvent,
    ProjectMember,
    SiteUpdate,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.approvals import ApprovalService, ResolutionCommand
from app.worker import process_event


@dataclass(frozen=True, slots=True)
class CapacityScenario:
    name: str
    passed: bool
    count: int
    duration_ms: float
    detail: str


@dataclass(frozen=True, slots=True)
class CapacityEvidence:
    generated_at: str
    environment: str
    passed: bool
    total_duration_ms: float
    git_revision: str | None
    scenarios: tuple[CapacityScenario, ...]

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["scenarios"] = [asdict(scenario) for scenario in self.scenarios]
        return payload


def run_capacity_baseline() -> CapacityEvidence:
    started = monotonic()
    scenarios = (
        _run("100_project_partitions", 100, _exercise_project_partitions),
        _run("25_concurrent_site_updates", 25, _exercise_site_updates),
        _run("10_duplicate_deliveries", 10, _exercise_duplicate_delivery),
        _run("concurrent_approval_decisions", 10, _exercise_approval_decisions),
        _run("100_project_scheduler_burst", 100, _exercise_scheduler_burst),
    )
    return CapacityEvidence(
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        environment="local_in_memory",
        passed=all(scenario.passed for scenario in scenarios),
        total_duration_ms=round((monotonic() - started) * 1_000, 3),
        git_revision=_git_revision(),
        scenarios=scenarios,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Oga local capacity baseline")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    evidence = run_capacity_baseline()
    encoded = json.dumps(evidence.as_json(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if evidence.passed else 1


def _run(name: str, count: int, scenario: Callable[[], str]) -> CapacityScenario:
    started = monotonic()
    try:
        detail = scenario()
    except Exception as exc:
        return CapacityScenario(
            name=name,
            passed=False,
            count=count,
            duration_ms=round((monotonic() - started) * 1_000, 3),
            detail=type(exc).__name__,
        )
    return CapacityScenario(
        name=name,
        passed=True,
        count=count,
        duration_ms=round((monotonic() - started) * 1_000, 3),
        detail=str(detail)[:500],
    )


def _exercise_project_partitions() -> str:
    store = InMemoryRepositoryStore()
    tasks = store.repository(Task)
    for index in range(100):
        project_id = f"prj_capacity{index:03d}"
        tasks.create(
            Task(
                id=f"tsk_capacity{index:03d}",
                project_id=project_id,
                title=f"Capacity task {index}",
            )
        )
    assert all(len(tasks.list(f"prj_capacity{index:03d}")) == 1 for index in range(100))
    return "100 isolated project partitions retained one task each"


def _exercise_site_updates() -> str:
    store = InMemoryRepositoryStore()
    updates = store.repository(SiteUpdate)

    def create(index: int) -> str:
        update = SiteUpdate(
            id=f"upd_capacity{index:03d}",
            project_id="prj_capacity",
            submitted_by="usr_foreman123",
            input_type=SiteUpdateInputType.MIXED,
            raw_text=f"Capacity update {index}",
            attachment_ids=[f"att_capacity{index:03d}_{item:02d}" for item in range(10)],
            client_event_id=f"capacity-client-{index}",
        )
        return updates.create(update).id

    with ThreadPoolExecutor(max_workers=25) as executor:
        created = tuple(executor.map(create, range(25)))
    persisted = updates.list("prj_capacity")
    assert len(created) == len(set(created)) == 25
    assert len(persisted) == 25
    assert all(len(update.attachment_ids) == 10 for update in persisted)
    return "25 concurrent updates retained 10 attachment references each"


def _exercise_duplicate_delivery() -> str:
    store = InMemoryRepositoryStore()
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id="prj_capacity",
            user_id="usr_foreman123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(Task).create(
        Task(
            id="tsk_capacity_duplicate",
            project_id="prj_capacity",
            title="Capacity duplicate task",
            status=TaskStatus.IN_PROGRESS,
        )
    )
    event = _duplicate_event()
    results = [process_event(event.model_dump_json().encode(), store=store) for _ in range(10)]
    claims = store.repository(ProcessedEvent).list(event.project_id)
    assert results[0].status == "completed"
    assert [result.status for result in results[1:]] == ["duplicate"] * 9
    assert len(claims) == 1
    return "one completed claim and nine duplicate replays"


def _exercise_approval_decisions() -> str:
    store = InMemoryRepositoryStore()
    store.repository(Approval).create(
        Approval(
            id="app_capacity123",
            project_id="prj_capacity",
            action_type=ApprovalActionType.PURCHASE,
            proposed_action={"material_id": "mat_cement123", "quantity": "100"},
            reason="Capacity approval fixture",
            requested_by="system",
        )
    )
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="sub_manager123"),
        project_id="prj_capacity",
        role=MemberRole.MANAGER,
    )
    command = ResolutionCommand(
        project_id="prj_capacity",
        approval_id="app_capacity123",
        expected_version=0,
    )
    context = MutationContext(
        project_id="prj_capacity",
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        source_event_id="evt_capacity_decision",
        idempotency_key="capacity-approval-decision",
    )
    service = ApprovalService(store)

    def approve(_: int) -> bool:
        return service.approve(access, command, context).duplicate

    with ThreadPoolExecutor(max_workers=10) as executor:
        duplicates = tuple(executor.map(approve, range(10)))
    approval = store.repository(Approval).require("prj_capacity", "app_capacity123")
    activities = store.repository(ActivityEvent).list("prj_capacity")
    outbox = store.repository(OutboxMessage).list("prj_capacity")
    assert approval.status is ApprovalStatus.APPROVED
    assert duplicates.count(False) == 1
    assert duplicates.count(True) == 9
    assert len(activities) == 1
    assert len(outbox) == 1
    return "one human decision won; nine retries replayed one activity/outbox result"


def _exercise_scheduler_burst() -> str:
    store = InMemoryRepositoryStore()

    def deliver(index: int) -> str:
        event = _brief_event(index)
        return process_event(event.model_dump_json().encode(), store=store).status

    with ThreadPoolExecutor(max_workers=25) as executor:
        statuses = tuple(executor.map(deliver, range(100)))
    assert statuses == ("completed",) * 100
    assert all(
        len(store.repository(ProcessedEvent).list(f"prj_burst{index:03d}")) == 1
        for index in range(100)
    )
    return "100 daily-brief events reached one terminal claim per project"


def _duplicate_event() -> ProjectEvent:
    now = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
    return ProjectEvent(
        event_id="evt_capacity_duplicate",
        project_id="prj_capacity",
        event_type=EventType.TASK_COMPLETED,
        source=EventSource.SYSTEM,
        occurred_at=now,
        received_at=now,
        actor=EventActor(type=EventActorType.USER, id="usr_foreman123"),
        idempotency_key="capacity:duplicate:site-update",
        correlation_id="cor_capacity_duplicate",
        payload={
            "task_id": "tsk_capacity_duplicate",
            "evidence_refs": ["capacity-baseline"],
        },
    )


def _brief_event(index: int) -> ProjectEvent:
    now = datetime(2026, 8, 8, 5, 0, tzinfo=UTC)
    return ProjectEvent(
        event_id=f"evt_burst{index:03d}",
        project_id=f"prj_burst{index:03d}",
        event_type=EventType.DAILY_BRIEF_REQUESTED,
        source=EventSource.SCHEDULER,
        occurred_at=now,
        received_at=now,
        actor=EventActor(type=EventActorType.WORKLOAD, id="wrk_scheduler123"),
        idempotency_key=f"daily-brief:2026-08-08:prj-burst-{index:03d}",
        correlation_id=f"cor_burst{index:03d}",
        payload={"report_date": "2026-08-08", "timezone": "Africa/Accra"},
    )


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision[:64] or None


if __name__ == "__main__":
    raise SystemExit(main())
