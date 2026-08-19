from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import (
    ContextDomain,
    ContextQuery,
    ConversationalProjectContext,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
    IssueContextItem,
    IssueOperation,
    MaterialContextItem,
    MaterialRequestContextItem,
    MaterialOperation,
    MutationPolicyClass,
    MutationKind,
    MutationPolicyRequest,
    MemberContextItem,
    TaskContextItem,
    TaskOperation,
)
from app.domain.enums import IssueStatus, MemberRole, TaskStatus
from app.services.conversation_action_composer import (
    ActionComposer,
    IssueActionInterpretation,
    MaterialActionInterpretation,
    PurchaseActionInterpretation,
    ScheduleActionInterpretation,
    TaskActionInterpretation,
    TaskActionBatchInterpretation,
    ambiguous_material_quantity_phrase,
)
from app.services.conversation_mutation_policy import MutationPolicyService


NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
PROJECT_ID = "prj_composer123"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("add 20 bags of cement to inventory", None),
        ("put another 20 bags of cement in stock", None),
        ("add 20 more cement bags", None),
        ("we have 20 bags of cement", None),
        ("20 bags of cement arrived", None),
        ("buy 20 bags", None),
        ("prepare a request for 20 bags", None),
        ("add 20 bags of cement", ("20", "bags", "cement")),
    ],
)
def test_material_quantity_language_distinguishes_bare_addition(
    message: str, expected: tuple[str, str, str] | None
) -> None:
    assert ambiguous_material_quantity_phrase(message) == expected


def access(project_id: str = PROJECT_ID) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="firebase-manager"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )


def resolved(kind: EntityKind, entity_id: str, reference: str) -> EntityResolution:
    return EntityResolution(
        kind=kind,
        reference=reference,
        status=EntityResolutionStatus.RESOLVED,
        entity_id=entity_id,
        display_name=reference.title(),
        match_method="exact",
        can_mutate=True,
    )


def context(project_id: str = PROJECT_ID) -> ConversationalProjectContext:
    return ConversationalProjectContext(
        project_id=project_id,
        retrieved_at=NOW,
        query=ContextQuery(domains=(ContextDomain.MATERIALS, ContextDomain.SCHEDULE)),
        materials=(
            MaterialContextItem(
                id="mat_cement123",
                name="Cement",
                unit="bags",
                available_quantity=Decimal("10"),
                reserved_quantity=Decimal("0"),
                minimum_required_quantity=Decimal("40"),
                version=7,
            ),
        ),
        tasks=(
            TaskContextItem(
                id="tsk_plastering123",
                title="Plastering",
                status="not_started",
                priority="medium",
                version=4,
            ),
        ),
        schedule=(
            TaskContextItem(
                id="tsk_plastering123",
                title="Plastering",
                status="not_started",
                priority="medium",
                version=4,
            ),
        ),
        issues=(
            IssueContextItem(
                id="iss_electrical123",
                type="blocker",
                severity="high",
                description="Electrician did not arrive.",
                status="open",
                version=3,
            ),
        ),
        material_requests=(
            MaterialRequestContextItem(
                id="mrq_cement123",
                material_id="mat_cement123",
                quantity=Decimal("30"),
                delivered_quantity=Decimal("0"),
                unit="bags",
                status="confirmed",
                reason="Cement required for plastering.",
                version=5,
            ),
        ),
        members=(
            MemberContextItem(
                user_id="usr_foreman123",
                display_name="Kofi Mensah",
                role="foreman",
            ),
        ),
    )


def composer() -> ActionComposer:
    return ActionComposer(MutationPolicyService())


def policy(kind: MutationKind) -> MutationPolicyRequest:
    return MutationPolicyRequest(project_id=PROJECT_ID, kind=kind)


def test_task_batches_require_individual_composition() -> None:
    with pytest.raises(ValueError, match="task batches must be composed individually"):
        composer().compose(
            access(),
            TaskActionBatchInterpretation(
                actions=(
                    TaskActionInterpretation(
                        operation=TaskOperation.CREATE,
                        title="Install windows",
                    ),
                    TaskActionInterpretation(
                        operation=TaskOperation.CREATE,
                        title="Paint walls",
                    ),
                )
            ),
            context(),
            (),
            policy(MutationKind.TASK_CREATE),
        )


def test_composes_absolute_material_count_with_authorized_observed_version() -> None:
    proposal = composer().compose(
        access(),
        MaterialActionInterpretation(
            operation=MaterialOperation.SET_ON_SITE,
            material_reference="cement",
            quantity=Decimal("100"),
            unit="bags",
            reason="Reported current stock count.",
        ),
        context(),
        (resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),),
        policy(MutationKind.MATERIAL_QUANTITY),
    )

    assert proposal.kind == "material"
    assert proposal.policy_decision.policy is MutationPolicyClass.AUTO_EXECUTE
    assert proposal.command.operation is MaterialOperation.SET_ON_SITE
    assert proposal.command.material.entity_id == "mat_cement123"
    assert proposal.command.quantity == Decimal("100")
    assert proposal.command.unit == "bags"
    assert proposal.command.expected_version == 7


def test_composes_schedule_proposal_without_executing_or_confirming_it() -> None:
    start = datetime(2026, 8, 21, 8, tzinfo=UTC)
    end = datetime(2026, 8, 21, 17, tzinfo=UTC)

    proposal = composer().compose(
        access(),
        ScheduleActionInterpretation(
            task_reference="plastering",
            planned_start=start,
            planned_end=end,
        ),
        context(),
        (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
        policy(MutationKind.SCHEDULE_DATES),
    )

    assert proposal.kind == "schedule"
    assert proposal.policy_decision.policy is MutationPolicyClass.CONFIRM_FIRST
    assert proposal.command.confirmed is False
    assert proposal.command.proposal is None
    assert proposal.command.task.entity_id == "tsk_plastering123"
    assert proposal.command.expected_version == 4


def test_composes_task_and_issue_commands_with_positive_evidence() -> None:
    task = composer().compose(
        access(),
        TaskActionInterpretation(
            operation=TaskOperation.COMPLETE,
            task_reference="plastering",
            evidence="Foreman explicitly reported plastering complete.",
        ),
        context(),
        (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
        policy(MutationKind.TASK_COMPLETE),
    )
    issue = composer().compose(
        access(),
        IssueActionInterpretation(
            operation=IssueOperation.RESOLVE,
            issue_reference="electrical",
            evidence="Foreman explicitly reported electrical is sorted.",
        ),
        context(),
        (resolved(EntityKind.ISSUE, "iss_electrical123", "electrical"),),
        policy(MutationKind.ISSUE_RESOLVE),
    )

    assert task.kind == "task"
    assert task.command.expected_version == 4
    assert issue.kind == "issue"
    assert issue.command.expected_version == 3
    assert issue.policy_decision.policy is MutationPolicyClass.AUTO_EXECUTE


def test_purchase_is_always_composed_for_existing_approval_workflow() -> None:
    proposal = composer().compose(
        access(),
        PurchaseActionInterpretation(
            material_reference="cement",
            quantity=Decimal("30"),
            unit="bags",
            reason="Cement required for plastering.",
        ),
        context(),
        (resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),),
        policy(MutationKind.MATERIAL_PURCHASE),
    )

    assert proposal.kind == "purchase"
    assert proposal.command.expected_material_version == 7
    assert proposal.policy_decision.policy is MutationPolicyClass.APPROVAL_REQUIRED
    assert proposal.policy_decision.use_existing_approval is True


def test_rejects_purchase_unit_that_conflicts_with_authorized_context() -> None:
    with pytest.raises(ValueError, match="unit does not match"):
        composer().compose(
            access(),
            PurchaseActionInterpretation(
                material_reference="cement",
                quantity=Decimal("30"),
                unit="tonnes",
                reason="Cement required for plastering.",
            ),
            context(),
            (resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),),
            policy(MutationKind.MATERIAL_PURCHASE),
        )


def test_negated_task_completion_never_produces_a_command() -> None:
    with pytest.raises(ValueError, match="clear positive evidence"):
        composer().compose(
            access(),
            TaskActionInterpretation(
                operation=TaskOperation.COMPLETE,
                task_reference="plastering",
                evidence="Plastering is not complete.",
                negated=True,
            ),
            context(),
            (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
            policy(MutationKind.TASK_COMPLETE),
        )


def test_generic_status_operations_cannot_bypass_completion_evidence() -> None:
    with pytest.raises(ValueError, match="typed complete operation"):
        composer().compose(
            access(),
            TaskActionInterpretation(
                operation=TaskOperation.CHANGE_STATUS,
                task_reference="plastering",
                target_status=TaskStatus.COMPLETED,
            ),
            context(),
            (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
            policy(MutationKind.TASK_UPDATE),
        )


def test_ambiguous_or_contradictory_operation_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="ambiguous language"):
        composer().compose(
            access(),
            TaskActionInterpretation(
                operation=TaskOperation.ASSIGN,
                task_reference="plastering",
                assignee_reference="Kofi",
                ambiguous=True,
            ),
            context(),
            (
                resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),
                resolved(EntityKind.PROJECT_MEMBER, "usr_foreman123", "Kofi"),
            ),
            policy(MutationKind.TASK_ASSIGN),
        )

    with pytest.raises(ValueError, match="does not accept fields"):
        composer().compose(
            access(),
            TaskActionInterpretation(
                operation=TaskOperation.COMPLETE,
                task_reference="plastering",
                evidence="Plastering is complete.",
                target_status=TaskStatus.CANCELLED,
            ),
            context(),
            (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
            policy(MutationKind.TASK_COMPLETE),
        )


def test_zero_quantity_delivery_is_not_a_valid_domain_command() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        composer().compose(
            access(),
            MaterialActionInterpretation(
                operation=MaterialOperation.RECORD_DELIVERY,
                material_reference="cement",
                material_request_reference="cement request",
                quantity=Decimal("0"),
                unit="bags",
            ),
            context(),
            (
                resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),
                resolved(EntityKind.MATERIAL_REQUEST, "mrq_cement123", "cement request"),
            ),
            policy(MutationKind.MATERIAL_DELIVERY),
        )


def test_delivery_requires_ready_request_and_valid_remaining_quantity() -> None:
    snapshot = context()
    awaiting = snapshot.model_copy(
        update={
            "material_requests": (
                snapshot.material_requests[0].model_copy(update={"status": "awaiting_approval"}),
            )
        }
    )
    interpretation = MaterialActionInterpretation(
        operation=MaterialOperation.RECORD_DELIVERY,
        material_reference="cement",
        material_request_reference="cement request",
        quantity=Decimal("31"),
        unit="bags",
    )
    entities = (
        resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),
        resolved(EntityKind.MATERIAL_REQUEST, "mrq_cement123", "cement request"),
    )

    with pytest.raises(ValueError, match="not ready"):
        composer().compose(
            access(), interpretation, awaiting, entities, policy(MutationKind.MATERIAL_DELIVERY)
        )
    with pytest.raises(ValueError, match="exceeds"):
        composer().compose(
            access(), interpretation, snapshot, entities, policy(MutationKind.MATERIAL_DELIVERY)
        )


def test_task_creation_rejects_inverted_date_range() -> None:
    with pytest.raises(ValueError, match="planned_end cannot be before"):
        composer().compose(
            access(),
            TaskActionInterpretation(
                operation=TaskOperation.CREATE,
                title="Roofing",
                planned_start=datetime(2026, 8, 22, 8, tzinfo=UTC),
                planned_end=datetime(2026, 8, 21, 17, tzinfo=UTC),
            ),
            context(),
            (),
            policy(MutationKind.TASK_CREATE),
        )


def test_reopening_is_derived_from_observed_task_state() -> None:
    snapshot = context()
    completed = snapshot.model_copy(
        update={
            "tasks": (snapshot.tasks[0].model_copy(update={"status": "completed"}),),
            "schedule": (snapshot.schedule[0].model_copy(update={"status": "completed"}),),
        }
    )

    proposal = composer().compose(
        access(),
        TaskActionInterpretation(
            operation=TaskOperation.CHANGE_STATUS,
            task_reference="plastering",
            target_status=TaskStatus.IN_PROGRESS,
        ),
        completed,
        (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
        policy(MutationKind.TASK_REOPEN),
    )

    assert proposal.command.reopening is True
    assert proposal.policy_decision.policy is MutationPolicyClass.CONFIRM_FIRST

    with pytest.raises(ValueError, match="typed resolve operation"):
        composer().compose(
            access(),
            IssueActionInterpretation(
                operation=IssueOperation.CHANGE_STATUS,
                issue_reference="electrical",
                target_status=IssueStatus.RESOLVED,
            ),
            context(),
            (resolved(EntityKind.ISSUE, "iss_electrical123", "electrical"),),
            policy(MutationKind.ISSUE_UPDATE),
        )


def test_task_cancellation_policy_requires_human_approval() -> None:
    proposal = composer().compose(
        access(),
        TaskActionInterpretation(
            operation=TaskOperation.CHANGE_STATUS,
            task_reference="plastering",
            target_status=TaskStatus.CANCELLED,
        ),
        context(),
        (resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),),
        policy(MutationKind.TASK_CANCEL),
    )

    assert proposal.policy_decision.policy is MutationPolicyClass.APPROVAL_REQUIRED


def test_rejects_context_absent_assignee() -> None:
    with pytest.raises(ValueError, match="project member is absent"):
        composer().compose(
            access(),
            TaskActionInterpretation(
                operation=TaskOperation.ASSIGN,
                task_reference="plastering",
                assignee_reference="Ama",
            ),
            context(),
            (
                resolved(EntityKind.TASK, "tsk_plastering123", "plastering"),
                resolved(EntityKind.PROJECT_MEMBER, "usr_other123", "Ama"),
            ),
            policy(MutationKind.TASK_ASSIGN),
        )


def test_delivery_binds_both_material_and_request_versions() -> None:
    proposal = composer().compose(
        access(),
        MaterialActionInterpretation(
            operation=MaterialOperation.RECORD_DELIVERY,
            material_reference="cement",
            material_request_reference="cement request",
            quantity=Decimal("30"),
            unit="bags",
        ),
        context(),
        (
            resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),
            resolved(
                EntityKind.MATERIAL_REQUEST,
                "mrq_cement123",
                "cement request",
            ),
        ),
        policy(MutationKind.MATERIAL_DELIVERY),
    )

    assert proposal.command.expected_version == 7
    assert proposal.command.expected_material_request_version == 5


def test_rejects_resolved_entity_that_is_absent_from_authorized_context() -> None:
    interpretation = MaterialActionInterpretation(
        operation=MaterialOperation.SET_ON_SITE,
        material_reference="cement",
        quantity=Decimal("100"),
        unit="bags",
    )

    with pytest.raises(ValueError, match="authorized project context"):
        composer().compose(
            access(),
            interpretation,
            context(),
            (resolved(EntityKind.MATERIAL, "mat_other123", "cement"),),
            policy(MutationKind.MATERIAL_QUANTITY),
        )


def test_rejects_cross_project_context_before_composition() -> None:
    interpretation = MaterialActionInterpretation(
        operation=MaterialOperation.SET_ON_SITE,
        material_reference="cement",
        quantity=Decimal("100"),
        unit="bags",
    )

    with pytest.raises(PermissionError):
        composer().compose(
            access(),
            interpretation,
            context("prj_other123"),
            (resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),),
            policy(MutationKind.MATERIAL_QUANTITY),
        )


def test_rejects_policy_for_a_different_mutation_kind() -> None:
    with pytest.raises(ValueError, match="mutation policy does not match"):
        composer().compose(
            access(),
            MaterialActionInterpretation(
                operation=MaterialOperation.SET_ON_SITE,
                material_reference="cement",
                quantity=Decimal("100"),
                unit="bags",
            ),
            context(),
            (resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),),
            policy(MutationKind.ISSUE_RESOLVE),
        )


def test_rejects_material_unit_that_conflicts_with_authorized_context() -> None:
    with pytest.raises(ValueError, match="unit does not match"):
        composer().compose(
            access(),
            MaterialActionInterpretation(
                operation=MaterialOperation.SET_ON_SITE,
                material_reference="cement",
                quantity=Decimal("100"),
                unit="tonnes",
            ),
            context(),
            (resolved(EntityKind.MATERIAL, "mat_cement123", "cement"),),
            policy(MutationKind.MATERIAL_QUANTITY),
        )


def test_interpretation_contract_forbids_untyped_extra_model_fields() -> None:
    with pytest.raises(ValueError):
        MaterialActionInterpretation.model_validate(
            {
                "kind": "material",
                "operation": "set_on_site",
                "material_reference": "cement",
                "quantity": "100",
                "unit": "bags",
                "execute_now": True,
            }
        )


def test_operation_enums_remain_separate_between_domains() -> None:
    with pytest.raises(ValueError):
        MaterialActionInterpretation(
            operation=TaskOperation.COMPLETE,
            material_reference="cement",
            quantity=Decimal("100"),
            unit="bags",
        )

    assert IssueOperation.RESOLVE.value == "resolve"
