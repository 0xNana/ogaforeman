from enum import StrEnum

from pydantic import ConfigDict

from .enums import MemberRole, MemberStatus
from .models import CanonicalId, DomainModel, ProjectMember


class AuthenticationRequiredError(ValueError):
    code = "AUTH_REQUIRED"


class ProjectForbiddenError(PermissionError):
    code = "AUTH_PROJECT_FORBIDDEN"


class RoleRequiredError(PermissionError):
    code = "ROLE_REQUIRED"


class ProjectPermission(StrEnum):
    READ = "read"
    OPERATE = "operate"
    APPROVE = "approve"
    MANAGE = "manage"


_ROLE_PERMISSIONS: dict[MemberRole, frozenset[ProjectPermission]] = {
    MemberRole.ADMIN: frozenset(ProjectPermission),
    MemberRole.MANAGER: frozenset(
        {ProjectPermission.READ, ProjectPermission.OPERATE, ProjectPermission.APPROVE}
    ),
    MemberRole.FOREMAN: frozenset({ProjectPermission.READ, ProjectPermission.OPERATE}),
    MemberRole.VIEWER: frozenset({ProjectPermission.READ}),
}


class AuthenticatedUser(DomainModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    user_id: CanonicalId
    subject: str
    email: str | None = None


class ProjectAccessContext(DomainModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    actor: AuthenticatedUser
    project_id: CanonicalId
    role: MemberRole


def authorize_project_member(
    actor: AuthenticatedUser,
    project_id: str,
    membership: ProjectMember | None,
    permission: ProjectPermission,
) -> ProjectAccessContext:
    if (
        membership is None
        or membership.project_id != project_id
        or membership.user_id != actor.user_id
        or membership.status is not MemberStatus.ACTIVE
    ):
        raise ProjectForbiddenError("actor does not have an active membership for this project")

    access = ProjectAccessContext(actor=actor, project_id=project_id, role=membership.role)
    ensure_permission(access, permission)
    return access


def ensure_permission(access: ProjectAccessContext, permission: ProjectPermission) -> None:
    if permission not in _ROLE_PERMISSIONS[access.role]:
        raise RoleRequiredError(
            f"role {access.role} does not grant project permission {permission}"
        )


def ensure_project_scope(access: ProjectAccessContext, project_id: str) -> None:
    if access.project_id != project_id:
        raise ProjectForbiddenError("authorized project context does not match requested project")
