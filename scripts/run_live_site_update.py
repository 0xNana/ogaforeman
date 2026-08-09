"""Run a real Gemini site-update workflow against the local Firestore emulator."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.interpreter import SiteInterpreter
from app.config.settings import RuntimeEnvironment, Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import (
    AgentRunStatus,
    ApprovalStatus,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    ProcessingStatus,
    TaskStatus,
)
from app.domain.facts import ExtractedFactSet
from app.domain.materials import MaterialLedgerEntry
from app.domain.models import (
    ActivityEvent,
    AgentRun,
    Approval,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    SiteUpdate,
    Task,
)
from app.infrastructure.firestore import create_firestore_client
from app.infrastructure.gemini import GeminiSiteInterpreter
from app.repositories.firestore import FirestoreRepositoryStore
from app.services.site_update_intake import SiteUpdateIntakeService
from app.worker import process_event_async
from scripts.reset_demo import reset_demo
from scripts.seed_demo import DEMO_FOREMAN_ID, DEMO_PROJECT_ID


CANONICAL_SITE_UPDATE = (
    "First-floor blockwork is done. Electrician did not come. "
    "We have ten bags of cement left. Plastering is tomorrow."
)


class RecordingInterpreter(SiteInterpreter):
    """Record structured facts while delegating every extraction to real Gemini."""

    def __init__(self, delegate: SiteInterpreter) -> None:
        self._delegate = delegate
        self.facts: ExtractedFactSet | None = None

    async def extract_facts(self, text: str) -> ExtractedFactSet:
        self.facts = await self._delegate.extract_facts(text)
        return self.facts


class CapturingPublisher:
    def __init__(self) -> None:
        self.event_data: bytes | None = None

    def publish(
        self,
        topic: str | None,
        data: bytes,
        *,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        del topic, attributes
        self.event_data = data
        return "msg_local_live_gemini"


async def run_live_site_update(settings: Settings) -> dict[str, Any]:
    _assert_live_local_runtime(settings)
    client = create_firestore_client(settings)
    reset_demo(client, settings=settings)
    store = FirestoreRepositoryStore(client)
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id=DEMO_FOREMAN_ID, subject="demo-foreman"),
        project_id=DEMO_PROJECT_ID,
        role=MemberRole.FOREMAN,
    )
    interpreter = RecordingInterpreter(GeminiSiteInterpreter(settings))
    publisher = CapturingPublisher()

    task_before = store.repository(Task).require(DEMO_PROJECT_ID, "tsk_blockwork")
    material_before = store.repository(Material).require(DEMO_PROJECT_ID, "mat_cement")
    accepted = SiteUpdateIntakeService(store, publisher).submit(
        access,
        idempotency_key="live-gemini-site-update-v1",
        raw_text=CANONICAL_SITE_UPDATE,
    )
    if publisher.event_data is None:
        raise RuntimeError("site update intake did not publish its persisted event")
    worker_result = await process_event_async(
        publisher.event_data,
        store=store,
        settings=settings,
        site_interpreter=interpreter,
    )
    task_after = store.repository(Task).require(DEMO_PROJECT_ID, "tsk_blockwork")
    material_after = store.repository(Material).require(DEMO_PROJECT_ID, "mat_cement")
    update = store.repository(SiteUpdate).require(DEMO_PROJECT_ID, accepted.site_update_id)
    activities = store.repository(ActivityEvent).list(DEMO_PROJECT_ID)
    ledger = store.repository(MaterialLedgerEntry).list(DEMO_PROJECT_ID)
    runs = store.repository(AgentRun).list(DEMO_PROJECT_ID)
    issues = store.repository(Issue).list(DEMO_PROJECT_ID)
    requests = store.repository(MaterialRequest).list(DEMO_PROJECT_ID)
    approvals = store.repository(Approval).list(DEMO_PROJECT_ID)
    reports = store.repository(DailyReport).list(DEMO_PROJECT_ID)

    passed = (
        worker_result.status == "completed"
        and worker_result.result_ref == f"run:{accepted.agent_run_id}"
        and task_before.status is TaskStatus.IN_PROGRESS
        and task_after.status is TaskStatus.COMPLETED
        and material_before.available_quantity == Decimal("25")
        and material_after.available_quantity == Decimal("10")
        and update.processing_status is ProcessingStatus.WAITING_FOR_APPROVAL
        and len(issues) == 2
        and {issue.type for issue in issues} == {IssueType.BLOCKER, IssueType.DELAY_RISK}
        and len(requests) == 1
        and requests[0].status is MaterialRequestStatus.AWAITING_APPROVAL
        and requests[0].quantity == Decimal("30")
        and len(approvals) == 1
        and approvals[0].status is ApprovalStatus.PENDING
        and approvals[0].id == requests[0].approval_id
        and len(reports) == 1
        and reports[0].source_update_ids == [update.id]
        and len(reports[0].completed_work) == 1
        and len(reports[0].active_blockers) == 2
        and len(reports[0].material_risks) == 1
        and len(reports[0].next_focus) == 1
        and len(ledger) == 1
        and len(runs) == 1
        and runs[0].status is AgentRunStatus.WAITING_FOR_APPROVAL
    )
    return {
        "passed": passed,
        "model_backend": "gemini_developer_api"
        if settings.gemini_api_key is not None
        else "vertex_ai",
        "model_id": settings.gemini_model_id,
        "firestore": "emulator",
        "input": CANONICAL_SITE_UPDATE,
        "extracted_facts": (
            interpreter.facts.model_dump(mode="json") if interpreter.facts is not None else None
        ),
        "intake": {
            "site_update_id": accepted.site_update_id,
            "event_id": accepted.event_id,
            "agent_run_id": accepted.agent_run_id,
        },
        "worker": {
            "status": worker_result.status,
            "route": worker_result.route,
            "result_ref": worker_result.result_ref,
        },
        "persisted": {
            "task_status_before": task_before.status.value,
            "task_status_after": task_after.status.value,
            "material_quantity_before": str(material_before.available_quantity),
            "material_quantity_after": str(material_after.available_quantity),
            "activity_actions": [activity.action for activity in activities],
            "material_ledger_entries": len(ledger),
            "issue_types": [issue.type.value for issue in issues],
            "material_request_statuses": [request.status.value for request in requests],
            "approval_statuses": [approval.status.value for approval in approvals],
            "report_ids": [report.id for report in reports],
            "agent_run_statuses": [run.status.value for run in runs],
            "site_update_status": update.processing_status.value,
        },
    }


def _assert_live_local_runtime(settings: Settings) -> None:
    if settings.oga_env not in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}:
        raise RuntimeError("Live local rehearsal is restricted to OGA_ENV=local or test")
    if not settings.demo_mode:
        raise RuntimeError("Live local rehearsal requires DEMO_MODE=true")
    if not settings.firestore_emulator_host:
        raise RuntimeError("Live local rehearsal requires FIRESTORE_EMULATOR_HOST")
    if settings.use_fake_model:
        raise RuntimeError("Live local rehearsal requires USE_FAKE_MODEL=false")
    if not settings.gemini_model_id:
        raise RuntimeError("Live local rehearsal requires GEMINI_MODEL_ID")
    if settings.gemini_api_key is None and not (
        settings.google_cloud_project and settings.gemini_location
    ):
        raise RuntimeError(
            "Live local rehearsal requires GEMINI_API_KEY, or Vertex project and location"
        )


def main() -> None:
    evidence = asyncio.run(run_live_site_update(Settings()))
    print(json.dumps(evidence, indent=2))
    raise SystemExit(0 if evidence["passed"] else 1)


if __name__ == "__main__":
    main()
