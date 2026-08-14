"""Conversational issue commands composed from the typed issue service."""

from dataclasses import dataclass

from app.domain.activity import MutationContext
from app.domain.authorization import ProjectAccessContext
from app.domain.conversation import (
    ConversationIssueCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    IssueOperation,
)
from app.domain.enums import IssueDetectedBy, IssueStatus
from app.domain.models import Issue
from app.repositories.interfaces import RepositoryStore
from app.services.issues import CreateIssueCommand, IssueChange, IssueService, UpdateIssueCommand


@dataclass(frozen=True, slots=True)
class ConversationIssueResult:
    issue: Issue
    activity_id: str
    reply: str
    duplicate: bool


class ConversationIssueService:
    def __init__(self, issues: IssueService, store: RepositoryStore) -> None:
        self._issues = issues
        self._store = store

    def execute(
        self,
        access: ProjectAccessContext,
        command: ConversationIssueCommand,
        context: MutationContext,
    ) -> ConversationIssueResult:
        if command.operation is IssueOperation.CREATE:
            if (
                command.issue_type is None
                or command.severity is None
                or command.description is None
            ):
                raise ValueError("issue type, severity, and description are required")
            change = self._issues.create_issue(
                access,
                CreateIssueCommand(
                    project_id=access.project_id,
                    issue_type=command.issue_type,
                    severity=command.severity,
                    description=command.description,
                    detected_by=IssueDetectedBy.USER,
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            return _result(
                change, f"Done. I created the {change.issue.type.value.replace('_', ' ')} issue."
            )
        issue_id = _resolved(command.issue, EntityKind.ISSUE, "issue")
        current = self._store.repository(Issue).require(access.project_id, issue_id)
        version = self._store.repository(Issue).version_of(access.project_id, issue_id)
        if version is None:
            raise RuntimeError("resolved issue has no persisted version")
        if command.operation is IssueOperation.RESOLVE:
            if command.negated or command.ambiguous or not command.evidence:
                raise ValueError("issue resolution requires clear positive evidence")
            target = IssueStatus.RESOLVED
        elif command.operation is IssueOperation.CHANGE_STATUS:
            if command.target_status is None:
                raise ValueError("target issue status is required")
            target = command.target_status
        else:
            target = None
        if target is not None:
            change = self._issues.update_issue(
                access,
                UpdateIssueCommand(
                    project_id=access.project_id,
                    issue_id=issue_id,
                    expected_version=version,
                    target_status=target,
                    occurred_at=context.occurred_at,
                ),
                context,
            )
            if target is IssueStatus.RESOLVED:
                label = (
                    command.issue.display_name.casefold()
                    if command.issue and command.issue.display_name
                    else current.type.value
                )
                return _result(change, f"Got it. I've resolved the {label} blocker.")
            return _result(
                change, f"Done. {current.description} is now {target.value.replace('_', ' ')}."
            )
        if command.operation is IssueOperation.ASSIGN:
            owner_id = _resolved(command.owner, EntityKind.PROJECT_MEMBER, "project member")
            update = UpdateIssueCommand(
                project_id=access.project_id,
                issue_id=issue_id,
                expected_version=version,
                owner_id=owner_id,
                occurred_at=context.occurred_at,
            )
            reply = f"Done. I assigned {current.description}."
        else:
            if command.note is None:
                raise ValueError("issue note is required")
            update = UpdateIssueCommand(
                project_id=access.project_id,
                issue_id=issue_id,
                expected_version=version,
                note=command.note,
                occurred_at=context.occurred_at,
            )
            reply = f"Done. I added the note to {current.description}."
        return _result(self._issues.update_issue(access, update, context), reply)


def _resolved(value: EntityResolution | None, kind: EntityKind, label: str) -> str:
    if (
        value is None
        or value.kind is not kind
        or value.status is not EntityResolutionStatus.RESOLVED
        or not value.can_mutate
        or value.entity_id is None
    ):
        raise ValueError(f"a resolved {label} is required")
    return value.entity_id


def _result(change: IssueChange, reply: str) -> ConversationIssueResult:
    return ConversationIssueResult(change.issue, change.activity.id, reply, change.duplicate)


__all__ = ["ConversationIssueResult", "ConversationIssueService"]
