from __future__ import annotations

from functools import cached_property

from fastapi import Request

from app.config.settings import Settings
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.infrastructure.firestore import create_firestore_client
from app.repositories.firestore import FirestoreRepository, FirestoreRepositoryStore
from app.repositories.membership import FirestoreIdentityRepository, MembershipRepository
from app.domain.models import ProjectMember
from app.services.projects import FirestoreProjectService

from .auth import FirebaseTokenVerifier, authenticate_bearer, authenticate_or_provision_bearer


class ConfiguredAuthRuntime:
    """Lazy production composition for Firebase identity and Firestore access."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._verifier = FirebaseTokenVerifier(settings)

    @cached_property
    def _identities(self) -> FirestoreIdentityRepository:
        return FirestoreIdentityRepository(self.client)

    @cached_property
    def _memberships(self) -> MembershipRepository:
        return MembershipRepository(FirestoreRepository(self.client, ProjectMember))

    @cached_property
    def client(self):
        return create_firestore_client(self._settings)

    @cached_property
    def store(self) -> FirestoreRepositoryStore:
        return FirestoreRepositoryStore(self.client)

    @cached_property
    def projects(self) -> FirestoreProjectService:
        return FirestoreProjectService(self.client)

    def authenticate(
        self,
        request: Request,
        *,
        provision: bool = False,
        display_name: str | None = None,
    ) -> AuthenticatedUser:
        authorization = request.headers.get("Authorization")
        if provision:
            return authenticate_or_provision_bearer(
                authorization,
                self._verifier,
                self._identities,
                display_name=display_name,
            )
        return authenticate_bearer(authorization, self._verifier, self._identities)

    def project_access(
        self,
        request: Request,
        project_id: str,
        permission: ProjectPermission = ProjectPermission.READ,
    ) -> ProjectAccessContext:
        actor = self.authenticate(request)
        return self._memberships.require_access(actor, project_id, permission)


__all__ = ["ConfiguredAuthRuntime"]
