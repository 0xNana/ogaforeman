from datetime import UTC, datetime

import pytest

from app.domain.activity import MutationContext
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    ConversationIssueCommand,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    IssueOperation,
)
from app.domain.enums import (
    ActorType,
    IssueDetectedBy,
    IssueStatus,
    IssueType,
    MemberRole,
    Severity,
)
from app.domain.models import ActivityEvent, Issue, ProjectMember
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_issue_operations import ConversationIssueService
from app.services.issues import IssueService

NOW = datetime(2026, 8, 14, 11, tzinfo=UTC)
PID = "prj_issues123"


def access() -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager"),
        project_id=PID,
        role=MemberRole.MANAGER,
    )


def context(key: str) -> MutationContext:
    return MutationContext(
        project_id=PID,
        actor_type=ActorType.USER,
        actor_id="usr_manager123",
        idempotency_key=key,
        occurred_at=NOW,
    )


def resolved(kind: EntityKind, entity_id: str, name: str) -> EntityResolution:
    return EntityResolution(
        kind=kind,
        reference=name,
        status=EntityResolutionStatus.RESOLVED,
        entity_id=entity_id,
        display_name=name,
        match_method="exact",
        can_mutate=True,
    )


def store() -> InMemoryRepositoryStore:
    result = InMemoryRepositoryStore()
    result.repository(Issue).create(
        Issue(
            id="iss_electrical123",
            project_id=PID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrical rough-in blocked",
            detected_by=IssueDetectedBy.USER,
        )
    )
    result.repository(ProjectMember).create(
        ProjectMember(
            project_id=PID, user_id="usr_kofi123", role=MemberRole.FOREMAN, status="active"
        )
    )
    return result


def issue() -> EntityResolution:
    return resolved(EntityKind.ISSUE, "iss_electrical123", "Electrical rough-in")


def test_resolve_issue_is_atomic_and_replays_once() -> None:
    data = store()
    service = ConversationIssueService(IssueService(data), data)
    command = ConversationIssueCommand(
        operation=IssueOperation.RESOLVE,
        issue=issue(),
        note="Electrical is sorted.",
        evidence="Electrical is sorted.",
    )
    first = service.execute(access(), command, context("og:issue:resolve"))
    replay = service.execute(access(), command, context("og:issue:resolve"))
    assert first.issue.status is IssueStatus.RESOLVED
    assert first.reply == "Got it. I've resolved the electrical rough-in blocker."
    assert replay.duplicate is True
    assert len(data.repository(ActivityEvent).list(PID)) == 1


def test_assign_status_and_note_use_resolved_project_entities() -> None:
    data = store()
    service = ConversationIssueService(IssueService(data), data)
    assigned = service.execute(
        access(),
        ConversationIssueCommand(
            operation=IssueOperation.ASSIGN,
            issue=issue(),
            owner=resolved(EntityKind.PROJECT_MEMBER, "usr_kofi123", "Kofi"),
        ),
        context("og:issue:assign"),
    )
    changed = service.execute(
        access(),
        ConversationIssueCommand(
            operation=IssueOperation.CHANGE_STATUS,
            issue=issue(),
            target_status=IssueStatus.ACKNOWLEDGED,
        ),
        context("og:issue:status"),
    )
    noted = service.execute(
        access(),
        ConversationIssueCommand(
            operation=IssueOperation.ADD_NOTE, issue=issue(), note="Cable trays are on site."
        ),
        context("og:issue:note"),
    )
    assert assigned.issue.owner_id == "usr_kofi123"
    assert changed.issue.status is IssueStatus.ACKNOWLEDGED
    assert noted.issue.notes == ["Cable trays are on site."]


def test_ambiguous_or_negated_resolution_never_mutates() -> None:
    data = store()
    service = ConversationIssueService(IssueService(data), data)
    with pytest.raises(ValueError):
        service.execute(
            access(),
            ConversationIssueCommand(
                operation=IssueOperation.RESOLVE,
                issue=issue(),
                evidence="Electrical is not sorted.",
                negated=True,
            ),
            context("og:issue:unsafe"),
        )
    assert data.repository(Issue).require(PID, "iss_electrical123").status is IssueStatus.OPEN
    assert data.repository(ActivityEvent).list(PID) == ()


def test_create_issue_replays_without_duplicate() -> None:
    data = store()
    service = ConversationIssueService(IssueService(data), data)
    command = ConversationIssueCommand(
        operation=IssueOperation.CREATE,
        issue_type=IssueType.QUALITY,
        severity=Severity.MEDIUM,
        description="Cracked render at stair core",
    )
    first = service.execute(access(), command, context("og:issue:create"))
    replay = service.execute(access(), command, context("og:issue:create"))
    assert first.issue.description == "Cracked render at stair core"
    assert replay.duplicate is True
