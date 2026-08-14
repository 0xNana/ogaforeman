"""Deterministic safety policy for conversational mutations."""

from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.conversation import (
    MutationKind,
    MutationPolicyClass,
    MutationPolicyDecision,
    MutationPolicyRequest,
)

_AUTO = {
    MutationKind.TASK_CREATE,
    MutationKind.TASK_COMPLETE,
    MutationKind.TASK_ASSIGN,
    MutationKind.MATERIAL_QUANTITY,
    MutationKind.ISSUE_RESOLVE,
    MutationKind.ADD_NOTE,
}
_CONFIRM = {
    MutationKind.SCHEDULE_DATES,
    MutationKind.TASK_DEPENDENCIES,
    MutationKind.BULK_TASK_UPDATE,
    MutationKind.TASK_REOPEN,
    MutationKind.TASK_CANCEL,
    MutationKind.RECORD_DELETE,
}
_APPROVAL = {
    MutationKind.MATERIAL_PURCHASE,
    MutationKind.FINANCIAL_COMMITMENT,
    MutationKind.EXTERNAL_COMMITMENT,
    MutationKind.MAJOR_SCHEDULE_CHANGE,
}


class MutationPolicyService:
    def classify(
        self, access: ProjectAccessContext, request: MutationPolicyRequest
    ) -> MutationPolicyDecision:
        ensure_project_scope(access, request.project_id)
        try:
            ensure_permission(access, ProjectPermission.OPERATE)
        except PermissionError:
            return MutationPolicyDecision(
                policy=MutationPolicyClass.DENY_OR_ESCALATE, reason_code="insufficient_permission"
            )
        if request.kind in _AUTO:
            policy, reason = MutationPolicyClass.AUTO_EXECUTE, "routine_reversible_operation"
        elif request.kind in _CONFIRM:
            policy, reason = MutationPolicyClass.CONFIRM_FIRST, "consequential_reversible_change"
        elif request.kind in _APPROVAL:
            policy, reason = MutationPolicyClass.APPROVAL_REQUIRED, "human_approval_required"
        else:
            policy, reason = MutationPolicyClass.DENY_OR_ESCALATE, "unsafe_or_professional_boundary"
        return MutationPolicyDecision(
            policy=policy,
            reason_code=reason,
            use_existing_approval=policy is MutationPolicyClass.APPROVAL_REQUIRED,
        )


__all__ = ["MutationPolicyService"]
