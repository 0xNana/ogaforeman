"""Safe, typed semantic events for reconstructing durable workflows."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
import re

from app.domain.activity import ActivitySpec, MutationContext, WorkflowActivityAction
from app.domain.enums import ActorType
from app.domain.models import ActivityEvent
from app.repositories.interfaces import RepositoryStore
from app.services.activity import ActivityService, AdditionalActivity


_WORKFLOW_AUDIT_METADATA_FIELDS = frozenset(
    {
        "active_blocker_count",
        "active_task_ids",
        "adapter",
        "affected_task_ids",
        "approval_id",
        "attempt",
        "audio_attachment_count",
        "audio_attachment_ids",
        "available_quantity",
        "blocked_task_id",
        "clarification_count",
        "completed_work_count",
        "delivery_event_id",
        "dependency_edge_count",
        "error_code",
        "external_status",
        "image_attachment_count",
        "image_attachment_ids",
        "issue_count",
        "issue_fact_count",
        "issue_id",
        "issue_type",
        "material_count",
        "material_fact_count",
        "material_id",
        "material_ids",
        "material_request_id",
        "material_risk_count",
        "media_attachment_count",
        "next_focus_count",
        "next_focus_fact_count",
        "observation_count",
        "outbox_message_id",
        "outcome",
        "pending_approval_count",
        "processing_status",
        "reason_code",
        "report_date",
        "report_id",
        "required_quantity",
        "run_status",
        "safety_fact_count",
        "safety_stop_count",
        "severity",
        "shortage_quantity",
        "source_site_update_id",
        "status",
        "step",
        "task_count",
        "task_fact_count",
        "task_ids",
        "text_input_present",
        "trace_id",
        "transcribed_attachment_ids",
        "trigger_event_id",
        "unit",
        "workflow",
    }
)
_CODE_FIELDS = frozenset(
    {
        "adapter",
        "error_code",
        "external_status",
        "issue_type",
        "outcome",
        "processing_status",
        "reason_code",
        "run_status",
        "severity",
        "status",
        "step",
        "trace_id",
        "workflow",
    }
)
_ID_FIELDS = frozenset(
    {
        "approval_id",
        "blocked_task_id",
        "delivery_event_id",
        "issue_id",
        "material_id",
        "material_request_id",
        "outbox_message_id",
        "report_id",
        "source_site_update_id",
        "trigger_event_id",
    }
)
_ID_LIST_FIELDS = frozenset(
    {
        "active_task_ids",
        "affected_task_ids",
        "audio_attachment_ids",
        "image_attachment_ids",
        "material_ids",
        "task_ids",
        "transcribed_attachment_ids",
    }
)
_QUANTITY_FIELDS = frozenset({"available_quantity", "required_quantity", "shortage_quantity"})
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ID_RE = re.compile(r"^[a-z][a-z0-9]{1,15}_[a-z0-9][a-z0-9_-]{2,127}$")
_QUANTITY_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class WorkflowAuditService:
    """Append replay-safe observable workflow events with allowlisted metadata."""

    def __init__(self, store: RepositoryStore) -> None:
        self._activities = ActivityService(store)

    def record(
        self,
        context: MutationContext,
        *,
        action: WorkflowActivityAction,
        entity_type: str,
        entity_id: str,
        summary: str,
        metadata: Mapping[str, object] | None = None,
    ) -> ActivityEvent:
        return self._activities.mutate(
            context,
            ActivitySpec(
                action=action.value,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                metadata=_validated_workflow_metadata(metadata),
            ),
            lambda _session: None,
        ).activity


def workflow_audit_activity(
    context: MutationContext,
    *,
    action: WorkflowActivityAction,
    entity_type: str,
    entity_id: str,
    summary: str,
    metadata: Mapping[str, object] | None = None,
) -> AdditionalActivity | None:
    """Build a system-attributed semantic event for an existing workflow mutation."""

    if context.source_event_id is None or context.agent_run_id is None:
        return None
    digest = sha256(
        f"{context.idempotency_key}\x00{action.value}\x00{entity_id}".encode("utf-8")
    ).hexdigest()[:32]
    audit_context = MutationContext(
        project_id=context.project_id,
        actor_type=ActorType.SYSTEM,
        source_event_id=context.source_event_id,
        agent_run_id=context.agent_run_id,
        idempotency_key=f"workflow-audit:{digest}",
        occurred_at=datetime.now(UTC),
    )
    return (
        audit_context,
        ActivitySpec(
            action=action.value,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            metadata=_validated_workflow_metadata(metadata),
        ),
    )


def _validated_workflow_metadata(
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    safe_metadata = dict(metadata or {})
    unexpected = sorted(set(safe_metadata) - _WORKFLOW_AUDIT_METADATA_FIELDS)
    if unexpected:
        raise ValueError(f"workflow audit metadata field is not allowlisted: {unexpected[0]}")
    for field_name, value in safe_metadata.items():
        if value is None:
            continue
        if field_name in _CODE_FIELDS:
            if not isinstance(value, str) or _CODE_RE.fullmatch(value) is None:
                raise ValueError(f"workflow audit {field_name} must be a bounded code")
            continue
        if field_name in _ID_FIELDS:
            if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
                raise ValueError(f"workflow audit {field_name} must be a canonical ID")
            continue
        if field_name in _ID_LIST_FIELDS:
            if (
                not isinstance(value, list)
                or len(value) > 100
                or any(
                    not isinstance(item, str) or _ID_RE.fullmatch(item) is None for item in value
                )
            ):
                raise ValueError(f"workflow audit {field_name} must contain bounded canonical IDs")
            continue
        if field_name in _QUANTITY_FIELDS:
            if not isinstance(value, str) or _QUANTITY_RE.fullmatch(value) is None:
                raise ValueError(f"workflow audit {field_name} must be a decimal string")
            continue
        if field_name == "text_input_present":
            if not isinstance(value, bool):
                raise ValueError("workflow audit text_input_present must be a boolean")
            continue
        if field_name == "report_date":
            if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
                raise ValueError("workflow audit report_date must be an ISO date")
            continue
        if field_name == "unit":
            if not isinstance(value, str) or not 1 <= len(value) <= 100 or "\n" in value:
                raise ValueError("workflow audit unit must be a bounded unit label")
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"workflow audit {field_name} must be a non-negative integer")
    return safe_metadata


__all__ = ["WorkflowAuditService", "workflow_audit_activity"]
