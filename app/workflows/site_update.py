"""Daily Site Update orchestration workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.authorization import ProjectAccessContext
from app.domain.enums import WorkflowName
from app.domain.models import SiteUpdate, SiteUpdateInputType
from app.services.site_updates import SiteUpdateService
from app.workflows.runtime import RuntimeManager


async def run_site_update_workflow(
    site_id: str,
    raw_text: str,
    voice_transcript: str | None = None,
    photo_urls: list[str] | None = None,
    *,
    service: SiteUpdateService | None = None,
    runtime: RuntimeManager | None = None,
    access: ProjectAccessContext | None = None,
) -> dict[str, Any]:
    """Process one site update through explicitly composed production dependencies."""

    if service is None or runtime is None or access is None:
        raise RuntimeError(
            "site-update workflow requires explicit service, runtime, and access dependencies"
        )

    del photo_urls  # Attachment IDs are persisted by intake before this workflow runs.
    update_id = f"upd_{uuid4().hex[:10]}"
    site_update = SiteUpdate(
        id=update_id,
        project_id=site_id,
        submitted_by=access.actor.user_id,
        input_type=(
            SiteUpdateInputType.MIXED if voice_transcript and raw_text else SiteUpdateInputType.TEXT
        ),
        raw_text=raw_text,
        transcript=voice_transcript,
        client_event_id=update_id,
        submitted_at=datetime.now(UTC),
    )

    run_id = f"run_{uuid4().hex}"
    runtime.start_run(
        project_id=site_id,
        trigger_event_id=update_id,
        workflow=WorkflowName.DAILY_SITE_UPDATE,
        run_id=run_id,
        trace_id=run_id,
    )
    result = await service.process_update(
        access=access,
        site_update=site_update,
        run_id=run_id,
        trace_id=run_id,
        source_event_id=update_id,
    )

    if result.has_safety_stops:
        runtime.pause_for_clarification(site_id, run_id, "safety_stop")
    elif result.has_clarifications:
        runtime.pause_for_clarification(site_id, run_id, "clarification_needed")
    elif result.has_pending_approvals:
        runtime.pause_for_approval(site_id, run_id, "approval_required")
    else:
        runtime.complete_run(site_id, run_id)

    return {
        "status": (
            "completed"
            if not result.has_safety_stops
            and not result.has_clarifications
            and not result.has_pending_approvals
            else "paused"
        ),
        "update_id": update_id,
        "site_id": site_id,
        "tasks_updated": result.tasks_updated,
        "materials_updated": result.materials_updated,
        "issues_created": result.issues_created,
        "material_requests_created": result.material_requests_created,
        "approvals_requested": result.approvals_requested,
        "report_id": result.report_id,
        "has_safety_stops": result.has_safety_stops,
        "has_clarifications": result.has_clarifications,
        "has_pending_approvals": result.has_pending_approvals,
        "summary": result.summary,
        "pending_actions": list(result.pending_actions),
        "timestamp": datetime.now(UTC).isoformat(),
    }


__all__ = ["run_site_update_workflow"]
