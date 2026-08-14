import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import MutationKind, MutationPolicyClass, MutationPolicyRequest
from app.domain.enums import MemberRole
from app.services.conversation_mutation_policy import MutationPolicyService


def access(role: MemberRole = MemberRole.MANAGER) -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_manager123", subject="manager"),
        project_id="prj_policy123",
        role=role,
    )


@pytest.mark.parametrize(
    "kind",
    [
        MutationKind.TASK_COMPLETE,
        MutationKind.TASK_ASSIGN,
        MutationKind.ADD_NOTE,
        MutationKind.ISSUE_RESOLVE,
        MutationKind.MATERIAL_QUANTITY,
    ],
)
def test_routine_mutations_auto_execute(kind: MutationKind) -> None:
    decision = MutationPolicyService().classify(
        access(), MutationPolicyRequest(project_id="prj_policy123", kind=kind)
    )
    assert decision.policy is MutationPolicyClass.AUTO_EXECUTE


def test_task_creation_requires_manage_permission() -> None:
    for role in (MemberRole.MANAGER, MemberRole.FOREMAN):
        decision = MutationPolicyService().classify(
            access(role),
            MutationPolicyRequest(project_id="prj_policy123", kind=MutationKind.TASK_CREATE),
        )
        assert decision.policy is MutationPolicyClass.DENY_OR_ESCALATE
        assert decision.reason_code == "insufficient_permission"

    admin_decision = MutationPolicyService().classify(
        access(MemberRole.ADMIN),
        MutationPolicyRequest(project_id="prj_policy123", kind=MutationKind.TASK_CREATE),
    )
    assert admin_decision.policy is MutationPolicyClass.AUTO_EXECUTE


@pytest.mark.parametrize(
    "kind",
    [
        MutationKind.SCHEDULE_DATES,
        MutationKind.TASK_DEPENDENCIES,
        MutationKind.BULK_TASK_UPDATE,
        MutationKind.TASK_REOPEN,
        MutationKind.TASK_CANCEL,
        MutationKind.RECORD_DELETE,
    ],
)
def test_consequential_reversible_changes_confirm_first(kind: MutationKind) -> None:
    assert (
        MutationPolicyService()
        .classify(access(), MutationPolicyRequest(project_id="prj_policy123", kind=kind))
        .policy
        is MutationPolicyClass.CONFIRM_FIRST
    )


@pytest.mark.parametrize(
    "kind",
    [
        MutationKind.MATERIAL_PURCHASE,
        MutationKind.FINANCIAL_COMMITMENT,
        MutationKind.EXTERNAL_COMMITMENT,
        MutationKind.MAJOR_SCHEDULE_CHANGE,
    ],
)
def test_commitments_require_existing_approval_infrastructure(kind: MutationKind) -> None:
    decision = MutationPolicyService().classify(
        access(), MutationPolicyRequest(project_id="prj_policy123", kind=kind)
    )
    assert decision.policy is MutationPolicyClass.APPROVAL_REQUIRED
    assert decision.use_existing_approval is True


@pytest.mark.parametrize(
    "kind",
    [
        MutationKind.STRUCTURAL_CERTIFICATION,
        MutationKind.UNSAFE_ENGINEERING_JUDGMENT,
        MutationKind.CONCEAL_SAFETY_RISK,
    ],
)
def test_unsafe_or_professional_claims_are_denied(kind: MutationKind) -> None:
    assert (
        MutationPolicyService()
        .classify(access(), MutationPolicyRequest(project_id="prj_policy123", kind=kind))
        .policy
        is MutationPolicyClass.DENY_OR_ESCALATE
    )


def test_role_and_project_scope_are_deterministic_policy_inputs() -> None:
    denied = MutationPolicyService().classify(
        access(MemberRole.VIEWER),
        MutationPolicyRequest(project_id="prj_policy123", kind=MutationKind.TASK_COMPLETE),
    )
    assert denied.policy is MutationPolicyClass.DENY_OR_ESCALATE
    with pytest.raises(PermissionError):
        MutationPolicyService().classify(
            access(), MutationPolicyRequest(project_id="prj_other123", kind=MutationKind.ADD_NOTE)
        )
