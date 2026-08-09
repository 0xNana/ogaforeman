"""Authorized, idempotent issue mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.activity import ActivitySpec, MutationContext, WorkflowActivityAction
from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.enums import ActorType, IssueDetectedBy, IssueStatus, IssueType, Severity
from app.domain.models import ActivityEvent, Issue
from app.repositories.interfaces import RepositoryStore
from app.services.activity import ActivityService
from app.services.workflow_audit import workflow_audit_activity


class CreateIssueCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    project_id: str
    issue_type: IssueType
    severity: Severity
    description: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    detected_by: IssueDetectedBy = IssueDetectedBy.SITE_UPDATE
    audit_reason_code: str | None = Field(default=None, max_length=128)
    audit_blocked_task_id: str | None = Field(default=None, max_length=145)
    audit_material_id: str | None = Field(default=None, max_length=145)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class IssueChange:
    issue: Issue
    activity: ActivityEvent
    duplicate: bool = False


class IssueService:
    def __init__(self, store: RepositoryStore) -> None:
        self._activities = ActivityService(store)

    def create_issue(
        self,
        access: ProjectAccessContext,
        command: CreateIssueCommand,
        context: MutationContext,
    ) -> IssueChange:
        ensure_project_scope(access, command.project_id)
        ensure_project_scope(access, context.project_id)
        ensure_permission(access, ProjectPermission.OPERATE)
        if context.actor_type is ActorType.USER and context.actor_id != access.actor.user_id:
            raise PermissionError("mutation actor does not match the authorized user")

        issue_id = _issue_id(context)
        semantic_activity = _issue_audit_activity(context, command, issue_id)
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="issue.created",
                entity_type="issue",
                entity_id=issue_id,
                summary=f"Created {command.issue_type.value.replace('_', ' ')} issue.",
                metadata={
                    "issue_type": command.issue_type.value,
                    "severity": command.severity.value,
                    "task_ids": command.task_ids,
                    "description_digest": sha256(command.description.encode("utf-8")).hexdigest()[
                        :16
                    ],
                },
            ),
            lambda session: session.repository(Issue).create(
                Issue(
                    id=issue_id,
                    project_id=command.project_id,
                    type=command.issue_type,
                    severity=command.severity,
                    description=command.description,
                    evidence_refs=command.evidence_refs,
                    task_ids=command.task_ids,
                    detected_by=command.detected_by,
                    created_at=command.occurred_at,
                    updated_at=command.occurred_at,
                )
            ),
            replay=lambda session, activity: session.repository(Issue).require(
                command.project_id, activity.entity_id
            ),
            additional_activities=(semantic_activity,) if semantic_activity else (),
        )
        if result.value is None:
            raise RuntimeError("issue replay did not resolve persisted state")
        return IssueChange(
            issue=result.value,
            activity=result.activity,
            duplicate=result.duplicate,
        )


def resolve_issue(issue: Issue, resolution_notes: str, resolved_by: str) -> Issue:
    del resolution_notes
    return issue.model_copy(
        update={
            "status": IssueStatus.RESOLVED,
            "resolved_at": datetime.now(UTC),
            "owner_id": resolved_by,
        }
    )


def _issue_id(context: MutationContext) -> str:
    raw = f"{context.project_id}\x00{context.actor_id or 'system'}\x00{context.idempotency_key}"
    return f"iss_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _issue_audit_activity(
    context: MutationContext,
    command: CreateIssueCommand,
    issue_id: str,
) -> tuple[MutationContext, ActivitySpec] | None:
    if command.issue_type is IssueType.BLOCKER:
        action = WorkflowActivityAction.BLOCKER_DETECTED
        summary = "Detected a project blocker from the site update."
        default_reason = "reported_task_blocker"
    elif command.issue_type is IssueType.DELAY_RISK:
        action = WorkflowActivityAction.SCHEDULE_RISK_DETECTED
        summary = "Detected schedule risk for supported project work."
        default_reason = "project_schedule_risk"
    else:
        return None
    metadata: dict[str, object] = {
        "status": IssueStatus.OPEN.value,
        "issue_id": issue_id,
        "issue_type": command.issue_type.value,
        "severity": command.severity.value,
        "task_ids": command.task_ids[:100],
        "reason_code": command.audit_reason_code or default_reason,
    }
    if command.audit_blocked_task_id is not None:
        metadata["blocked_task_id"] = command.audit_blocked_task_id
    if command.audit_material_id is not None:
        metadata["material_id"] = command.audit_material_id
    return workflow_audit_activity(
        context,
        action=action,
        entity_type="issue",
        entity_id=issue_id,
        summary=summary,
        metadata=metadata,
    )


__all__ = ["CreateIssueCommand", "IssueChange", "IssueService", "resolve_issue"]
