import os
from dataclasses import dataclass
from uuid import uuid4

import pytest
from google.cloud import firestore

from app.api import auth as auth_module
from app.api.auth import (
    FirebaseTokenVerifier,
    VerifiedIdentity,
    authenticate_bearer,
    authenticate_or_provision_bearer,
)
from app.config.settings import Settings
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectForbiddenError,
    ProjectPermission,
    RoleRequiredError,
)
from app.domain.enums import MemberRole, MemberStatus, UserStatus
from app.domain.models import ProjectMember, Task, User
from app.repositories.memory import InMemoryRepository
from app.repositories.membership import (
    AuthorizedProjectRepository,
    FirestoreIdentityRepository,
    InMemoryIdentityRepository,
    MembershipRepository,
)
from app.repositories.firestore import FirestoreRepository, firestore_document_data


@dataclass(frozen=True)
class FakeTokenVerifier:
    identities: dict[str, VerifiedIdentity]

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            return self.identities[token]
        except KeyError as exc:
            raise ValueError("invalid token") from exc


def make_user(user_id: str, subject: str) -> User:
    return User(
        id=user_id,
        identity_subject=subject,
        display_name=user_id,
        email=f"{user_id}@example.com",
    )


def make_member(user_id: str, role: MemberRole, *, project_id: str = "prj_ridge") -> ProjectMember:
    return ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=role,
        status=MemberStatus.ACTIVE,
    )


def test_bearer_authentication_resolves_verified_subject_to_canonical_user() -> None:
    identities = InMemoryIdentityRepository()
    user = make_user("usr_manager", "firebase-subject-123")
    identities.add(user)
    verifier = FakeTokenVerifier(
        {"valid-token": VerifiedIdentity(subject="firebase-subject-123", email=user.email)}
    )

    authenticated = authenticate_bearer("Bearer valid-token", verifier, identities)

    assert authenticated.user_id == "usr_manager"
    assert authenticated.subject == "firebase-subject-123"

    with pytest.raises(ValueError, match="Bearer"):
        authenticate_bearer("Basic credentials", verifier, identities)

    with pytest.raises(ValueError, match="registered user"):
        authenticate_bearer(
            "Bearer unknown-token",
            FakeTokenVerifier(
                {"unknown-token": VerifiedIdentity(subject="unknown-subject", email=None)}
            ),
            identities,
        )


def test_bearer_authentication_rejects_disabled_canonical_user() -> None:
    identities = InMemoryIdentityRepository()
    identities.add(
        make_user("usr_disabled", "firebase-disabled").model_copy(
            update={"status": UserStatus.DISABLED}
        )
    )
    verifier = FakeTokenVerifier(
        {"disabled-token": VerifiedIdentity(subject="firebase-disabled", email=None)}
    )

    with pytest.raises(ValueError, match="disabled"):
        authenticate_bearer("Bearer disabled-token", verifier, identities)


def test_bearer_authentication_provisions_unknown_subject_idempotently() -> None:
    identities = InMemoryIdentityRepository()
    verifier = FakeTokenVerifier(
        {
            "new-token": VerifiedIdentity(
                subject="firebase-new-subject",
                email="new.manager@example.com",
            )
        }
    )

    first = authenticate_or_provision_bearer(
        "Bearer new-token",
        verifier,
        identities,
        display_name="New Manager",
    )
    second = authenticate_or_provision_bearer(
        "Bearer new-token",
        verifier,
        identities,
        display_name="Changed Name",
    )

    assert first.user_id == second.user_id
    assert identities.get_by_subject("firebase-new-subject") is not None


def test_firebase_verifier_checks_audience_issuer_and_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        auth_audience="oga-foreman-test",
        auth_issuer="https://securetoken.google.com/oga-foreman-test",
    )
    captured: dict[str, object] = {}

    def verify(token: str, request: object, *, audience: str) -> dict[str, str]:
        captured.update(token=token, request=request, audience=audience)
        return {
            "sub": "firebase-subject-123",
            "email": "manager@example.com",
            "iss": "https://securetoken.google.com/oga-foreman-test",
        }

    monkeypatch.setattr(auth_module.id_token, "verify_firebase_token", verify)
    verifier = FirebaseTokenVerifier(settings)

    identity = verifier.verify("signed-token")

    assert identity.subject == "firebase-subject-123"
    assert captured["audience"] == "oga-foreman-test"

    monkeypatch.setattr(
        auth_module.id_token,
        "verify_firebase_token",
        lambda *args, **kwargs: {"sub": "firebase-subject-123", "iss": "wrong-issuer"},
    )
    with pytest.raises(ValueError, match="issuer"):
        verifier.verify("signed-token")


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (
            MemberRole.ADMIN,
            {
                ProjectPermission.READ,
                ProjectPermission.OPERATE,
                ProjectPermission.APPROVE,
                ProjectPermission.MANAGE,
            },
        ),
        (
            MemberRole.MANAGER,
            {
                ProjectPermission.READ,
                ProjectPermission.OPERATE,
                ProjectPermission.APPROVE,
            },
        ),
        (
            MemberRole.FOREMAN,
            {ProjectPermission.READ, ProjectPermission.OPERATE},
        ),
        (MemberRole.VIEWER, {ProjectPermission.READ}),
    ],
)
def test_role_matrix_enforces_project_permissions(
    role: MemberRole,
    allowed: set[ProjectPermission],
) -> None:
    members = MembershipRepository(InMemoryRepository(ProjectMember))
    user_id = f"usr_{role.value}"
    user = AuthenticatedUser(user_id=user_id, subject=f"subject-{role.value}")
    members.add(make_member(user_id, role))

    for permission in ProjectPermission:
        if permission in allowed:
            access = members.require_access(user, "prj_ridge", permission)
            assert access.role is role
        else:
            with pytest.raises(RoleRequiredError):
                members.require_access(user, "prj_ridge", permission)


def test_inactive_or_cross_project_membership_is_forbidden() -> None:
    members = MembershipRepository(InMemoryRepository(ProjectMember))
    user = AuthenticatedUser(user_id="usr_foreman", subject="subject-foreman")
    members.add(
        ProjectMember(
            project_id="prj_ridge",
            user_id=user.user_id,
            role=MemberRole.FOREMAN,
            status=MemberStatus.REMOVED,
        )
    )

    with pytest.raises(ProjectForbiddenError):
        members.require_access(user, "prj_ridge", ProjectPermission.READ)

    with pytest.raises(ProjectForbiddenError):
        members.require_access(user, "prj_other", ProjectPermission.READ)


def test_authorized_repository_rejects_cross_project_and_viewer_mutations() -> None:
    tasks = InMemoryRepository(Task)
    tasks.create(Task(id="tsk_ridge", project_id="prj_ridge", title="Ridge task"))
    tasks.create(Task(id="tsk_other", project_id="prj_other", title="Other task"))
    admin_access = MembershipRepository(InMemoryRepository(ProjectMember))
    admin = AuthenticatedUser(user_id="usr_admin", subject="subject-admin")
    admin_access.add(make_member(admin.user_id, MemberRole.ADMIN))
    admin_repository = AuthorizedProjectRepository(
        tasks,
        admin_access.require_access(admin, "prj_ridge", ProjectPermission.READ),
    )

    assert admin_repository.require("prj_ridge", "tsk_ridge").id == "tsk_ridge"
    with pytest.raises(ProjectForbiddenError):
        admin_repository.require("prj_other", "tsk_other")

    viewer_members = MembershipRepository(InMemoryRepository(ProjectMember))
    viewer = AuthenticatedUser(user_id="usr_viewer", subject="subject-viewer")
    viewer_members.add(make_member(viewer.user_id, MemberRole.VIEWER))
    viewer_repository = AuthorizedProjectRepository(
        tasks,
        viewer_members.require_access(viewer, "prj_ridge", ProjectPermission.READ),
    )

    with pytest.raises(RoleRequiredError):
        viewer_repository.create(
            Task(id="tsk_new", project_id="prj_ridge", title="Unauthorized task")
        )


def test_authorized_repository_transaction_keeps_project_scope_and_role_checks() -> None:
    tasks = InMemoryRepository(Task)
    members = MembershipRepository(InMemoryRepository(ProjectMember))
    viewer = AuthenticatedUser(user_id="usr_viewer", subject="subject-viewer")
    members.add(make_member(viewer.user_id, MemberRole.VIEWER))
    repository = AuthorizedProjectRepository(
        tasks,
        members.require_access(viewer, "prj_ridge", ProjectPermission.READ),
    )

    with pytest.raises(RoleRequiredError):
        repository.run_transaction(
            lambda transaction: transaction.create(
                Task(id="tsk_new", project_id="prj_ridge", title="Unauthorized task")
            )
        )

    with pytest.raises(ProjectForbiddenError):
        repository.run_transaction(lambda transaction: transaction.get("prj_other", "tsk_other"))


@pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="FIRESTORE_EMULATOR_HOST is required for Firestore authorization integration",
)
def test_firestore_identity_and_membership_resolution_survive_new_client() -> None:
    cloud_project_id = f"oga-auth-test-{uuid4().hex}"
    first_client = firestore.Client(project=cloud_project_id)
    user = make_user("usr_manager", "firebase-subject-123")
    first_client.document("users", user.id).set(firestore_document_data(user))
    FirestoreRepository(first_client, ProjectMember).create(
        make_member(user.id, MemberRole.MANAGER, project_id="prj_ridge")
    )

    restarted_client = firestore.Client(project=cloud_project_id)
    resolved_user = FirestoreIdentityRepository(restarted_client).get_by_subject(
        "firebase-subject-123"
    )
    assert resolved_user is not None
    actor = AuthenticatedUser(user_id=resolved_user.id, subject=resolved_user.identity_subject)
    memberships = MembershipRepository(FirestoreRepository(restarted_client, ProjectMember))

    access = memberships.require_access(actor, "prj_ridge", ProjectPermission.APPROVE)
    assert access.role is MemberRole.MANAGER
    with pytest.raises(ProjectForbiddenError):
        memberships.require_access(actor, "prj_other", ProjectPermission.READ)
