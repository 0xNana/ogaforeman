"""Durable materials calculation and request workflow."""

from typing import Any
from datetime import UTC, datetime
import uuid
from decimal import Decimal

from app.services.material_requests import MaterialRequestService, MaterialShortageCommand
from app.workflows.runtime import RuntimeManager
from app.domain.authorization import ProjectAccessContext
from app.domain.enums import WorkflowName, ActorType
from app.domain.activity import MutationContext


def run_materials_workflow(
    site_id: str,
    item_name: str,
    required_qty: float,
    unit: str,
    estimated_unit_cost: float,
    supplier: str,
    urgency: str = "medium",
    *,
    service: MaterialRequestService,
    runtime: RuntimeManager,
    access: ProjectAccessContext,
) -> dict[str, Any]:
    """Workflow 2: Evaluates inventory, prepares material requisitions, and handles HITL approval gates."""
    run_id = f"run_{uuid.uuid4().hex}"
    trigger_event_id = f"evt_{uuid.uuid4().hex[:10]}"

    runtime.start_run(
        project_id=site_id,
        trigger_event_id=trigger_event_id,
        workflow=WorkflowName.MATERIAL_SHORTAGE,
        run_id=run_id,
        trace_id=run_id,
    )

    command = MaterialShortageCommand(
        project_id=site_id,
        material_id_or_alias=item_name,
        required_quantity=Decimal(str(required_qty)),
        unit=unit,
        supplier=supplier,
        estimated_unit_cost=Decimal(str(estimated_unit_cost)),
        occurred_at=datetime.now(UTC),
        reason=f"Urgency: {urgency}. System request for {item_name}",
    )

    context = MutationContext(
        project_id=site_id,
        actor_type=ActorType.USER,
        actor_id=access.actor.user_id,
        idempotency_key=f"idempotency_{run_id}",
        source_event_id=trigger_event_id,
        agent_run_id=run_id,
    )

    result = service.evaluate_shortage(access, command, context)

    if not result.is_shortage:
        runtime.complete_run(site_id, run_id)
        return {
            "status": "in_stock",
            "message": f"Sufficient inventory available for {item_name}.",
            "item_name": item_name,
            "available_qty": float(result.net_shortage),
        }

    runtime.pause_for_approval(site_id, run_id, "approval_required")

    total_cost = 0.0
    if result.request and result.request.estimated_total_cost is not None:
        total_cost = float(result.request.estimated_total_cost)

    return {
        "status": "paused_for_approval",
        "hitl_gate_triggered": True,
        "request_id": result.request.id if result.request else "none",
        "site_id": site_id,
        "item_name": item_name,
        "net_quantity": float(result.net_shortage),
        "unit": unit,
        "total_estimated_cost": total_cost,
        "urgency": urgency,
        "supplier": supplier,
        "approval_status": "PENDING",
        "action_required": "PM Approval needed",
    }
