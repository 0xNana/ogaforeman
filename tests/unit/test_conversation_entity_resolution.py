from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import EntityKind, EntityResolutionStatus
from app.domain.enums import (
    IssueDetectedBy,
    IssueType,
    MaterialRequestStatus,
    MemberRole,
    MemberStatus,
    Severity,
    TaskStatus,
)
from app.domain.models import (
    ActivityEvent,
    DailyReport,
    Issue,
    Material,
    MaterialRequest,
    ProjectMember,
    Task,
)
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver


PROJECT_ID = "prj_resolution123"


def access(project_id: str = PROJECT_ID) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager-subject"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )


def test_unique_task_reference_resolves_without_mutating_state() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_groundplumbing123",
            project_id=PROJECT_ID,
            title="Ground-floor plumbing",
            status=TaskStatus.IN_PROGRESS,
        )
    )

    result = ConversationEntityResolver(store).resolve(access(), EntityKind.TASK, "plumbing")

    assert result.status is EntityResolutionStatus.RESOLVED
    assert result.entity_id == "tsk_groundplumbing123"
    assert result.display_name == "Ground-floor plumbing"
    assert result.can_mutate is True
    assert store.repository(ActivityEvent).list(PROJECT_ID) == ()


def test_ambiguous_task_reference_returns_bounded_clarification_candidates() -> None:
    store = InMemoryRepositoryStore()
    for task_id, title in (
        ("tsk_groundplumbing123", "Ground-floor plumbing"),
        ("tsk_firstplumbing123", "First-floor plumbing"),
    ):
        store.repository(Task).create(
            Task(id=task_id, project_id=PROJECT_ID, title=title, status=TaskStatus.IN_PROGRESS)
        )

    result = ConversationEntityResolver(store).resolve(access(), EntityKind.TASK, "plumbing")

    assert result.status is EntityResolutionStatus.AMBIGUOUS
    assert result.can_mutate is False
    assert result.clarification == (
        "Which task do you mean — First-floor plumbing or Ground-floor plumbing?"
    )
    assert [candidate.display_name for candidate in result.candidates] == [
        "First-floor plumbing",
        "Ground-floor plumbing",
    ]


def test_material_alias_reuses_canonical_material() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Portland cement",
            normalized_name="portland cement",
            aliases=["cement", "opc"],
            unit="bags",
            available_quantity=Decimal("10"),
        )
    )

    result = ConversationEntityResolver(store).resolve(access(), EntityKind.MATERIAL, "cement")

    assert result.entity_id == "mat_cement123"
    assert result.status is EntityResolutionStatus.RESOLVED


def test_exact_id_cannot_escape_authorized_project_partition() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_otherproject123",
            project_id="prj_other123",
            title="Secret task",
        )
    )

    result = ConversationEntityResolver(store).resolve(
        access(), EntityKind.TASK, "tsk_otherproject123"
    )

    assert result.status is EntityResolutionStatus.NOT_FOUND
    assert result.entity_id is None
    assert "Secret task" not in result.model_dump_json()


def test_typo_requires_strong_unique_fuzzy_match() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_plastering123",
            project_id=PROJECT_ID,
            title="Ground-floor plastering",
        )
    )

    matched = ConversationEntityResolver(store).resolve(
        access(), EntityKind.SCHEDULE_ACTIVITY, "ground floor plasterng"
    )
    unknown = ConversationEntityResolver(store).resolve(
        access(), EntityKind.SCHEDULE_ACTIVITY, "work"
    )

    assert matched.status is EntityResolutionStatus.RESOLVED
    assert matched.entity_id == "tsk_plastering123"
    assert matched.match_method == "fuzzy"
    assert unknown.status is EntityResolutionStatus.NOT_FOUND
    assert unknown.can_mutate is False


def test_contextual_id_is_revalidated_against_kind_and_project() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Issue).create(
        Issue(
            id="iss_electrical123",
            project_id=PROJECT_ID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrical rough-in is blocked",
            detected_by=IssueDetectedBy.USER,
        )
    )

    resolved = ConversationEntityResolver(store).resolve(
        access(), EntityKind.ISSUE, "it", contextual_entity_id="iss_electrical123"
    )
    wrong_kind = ConversationEntityResolver(store).resolve(
        access(), EntityKind.TASK, "it", contextual_entity_id="iss_electrical123"
    )

    assert resolved.status is EntityResolutionStatus.RESOLVED
    assert resolved.match_method == "context"
    assert wrong_kind.status is EntityResolutionStatus.NOT_FOUND


@pytest.mark.parametrize(
    ("kind", "reference", "expected_id"),
    [
        (EntityKind.ISSUE, "electrical blocker", "iss_electrical123"),
        (EntityKind.MATERIAL_REQUEST, "cement request", "mrq_cement123"),
        (EntityKind.PROJECT_MEMBER, "Kofi", "usr_kofi123"),
        (EntityKind.DAILY_LOG, "2026-08-13", "rpt_daily123"),
    ],
)
def test_supported_entity_kinds_resolve_from_project_truth(
    kind: EntityKind,
    reference: str,
    expected_id: str,
) -> None:
    store = InMemoryRepositoryStore()
    store.repository(Issue).create(
        Issue(
            id="iss_electrical123",
            project_id=PROJECT_ID,
            type=IssueType.BLOCKER,
            severity=Severity.HIGH,
            description="Electrical blocker",
            detected_by=IssueDetectedBy.USER,
        )
    )
    store.repository(Material).create(
        Material(
            id="mat_cement123",
            project_id=PROJECT_ID,
            name="Cement",
            normalized_name="cement",
            unit="bags",
        )
    )
    store.repository(MaterialRequest).create(
        MaterialRequest(
            id="mrq_cement123",
            project_id=PROJECT_ID,
            material_id="mat_cement123",
            quantity=Decimal("30"),
            unit="bags",
            reason="Cement shortage",
            source_event_id="evt_source123",
            status=MaterialRequestStatus.PROPOSED,
        )
    )
    store.repository(ProjectMember).create(
        ProjectMember(
            project_id=PROJECT_ID,
            user_id="usr_kofi123",
            role=MemberRole.FOREMAN,
            status=MemberStatus.ACTIVE,
        )
    )
    store.repository(DailyReport).create(
        DailyReport(
            id="rpt_daily123",
            project_id=PROJECT_ID,
            report_date=date(2026, 8, 13),
            summary="Daily site report",
        )
    )
    resolver = ConversationEntityResolver(
        store,
        member_names=lambda project_id: {"usr_kofi123": "Kofi Mensah"},
    )

    result = resolver.resolve(access(), kind, reference)

    assert result.status is EntityResolutionStatus.RESOLVED
    assert result.entity_id == expected_id
