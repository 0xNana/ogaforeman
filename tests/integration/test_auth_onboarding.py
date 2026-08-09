from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from google.cloud import firestore

from app.api.auth import (
    VerifiedIdentity,
    authenticate_bearer,
    authenticate_or_provision_bearer,
    canonical_user_id,
)
from app.api.errors import install_error_handlers, install_request_id_middleware
from app.api.v1.router import api_router
from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ProjectPermission
from app.domain.enums import UserStatus
from app.domain.models import ActivityEvent, ProjectMember, User
from app.repositories.firestore import FirestoreRepository, FirestoreRepositoryStore
from app.repositories.membership import FirestoreIdentityRepository, MembershipRepository
from app.services.projects import FirestoreProjectService


pytestmark = [
    pytest.mark.backing_services,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"),
        reason="FIRESTORE_EMULATOR_HOST is required for auth onboarding integration",
    ),
]


@dataclass(frozen=True)
class FakeTokenVerifier:
    identities: dict[str, VerifiedIdentity]

    def verify(self, token: str) -> VerifiedIdentity:
        return self.identities[token]


class EmulatorAuthRuntime:
    def __init__(self, client: firestore.Client, verifier: FakeTokenVerifier) -> None:
        self._verifier = verifier
        self.identities = FirestoreIdentityRepository(client)
        self.memberships = MembershipRepository(FirestoreRepository(client, ProjectMember))
        self.projects = FirestoreProjectService(client)
        self.store = FirestoreRepositoryStore(client)

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
                self.identities,
                display_name=display_name,
            )
        return authenticate_bearer(authorization, self._verifier, self.identities)

    def project_access(
        self,
        request: Request,
        project_id: str,
        permission: ProjectPermission = ProjectPermission.READ,
    ) -> ProjectAccessContext:
        return self.memberships.require_access(
            self.authenticate(request),
            project_id,
            permission,
        )


def make_app(runtime: EmulatorAuthRuntime) -> FastAPI:
    app = FastAPI()
    app.state.auth_runtime = runtime
    app.state.project_access_provider = runtime.project_access
    install_request_id_middleware(app)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


def test_firestore_bootstrap_is_idempotent_under_concurrency() -> None:
    project = f"oga-auth-bootstrap-{uuid4().hex}"
    subject = "firebase-concurrent-subject"
    verifier = FakeTokenVerifier(
        {
            "new-token": VerifiedIdentity(
                subject=subject,
                email="foreman@example.com",
            )
        }
    )

    def provision() -> str:
        identities = FirestoreIdentityRepository(firestore.Client(project=project))
        actor = authenticate_or_provision_bearer(
            "Bearer new-token",
            verifier,
            identities,
            display_name="Site Foreman",
        )
        return actor.user_id

    with ThreadPoolExecutor(max_workers=16) as pool:
        user_ids = list(pool.map(lambda _: provision(), range(32)))

    assert set(user_ids) == {canonical_user_id(subject)}
    users = list(firestore.Client(project=project).collection("users").stream())
    assert len(users) == 1


@pytest.mark.asyncio
async def test_bootstrap_and_project_onboarding_are_persisted_and_project_scoped() -> None:
    cloud_project = f"oga-auth-onboarding-{uuid4().hex}"
    client = firestore.Client(project=cloud_project)
    verifier = FakeTokenVerifier(
        {
            "admin-token": VerifiedIdentity(
                subject="firebase-admin-subject",
                email="admin@example.com",
            ),
            "other-token": VerifiedIdentity(
                subject="firebase-other-subject",
                email="other@example.com",
            ),
        }
    )
    runtime = EmulatorAuthRuntime(client, verifier)
    app = make_app(runtime)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        bootstrap = await api.post(
            "/api/v1/auth/bootstrap",
            json={"display_name": "Ama Builder"},
            headers={"Authorization": "Bearer admin-token"},
        )
        bootstrap_replay = await api.post(
            "/api/v1/auth/bootstrap",
            json={"display_name": "Ama Builder"},
            headers={"Authorization": "Bearer admin-token"},
        )
        other_bootstrap = await api.post(
            "/api/v1/auth/bootstrap",
            json={"display_name": "Other Builder"},
            headers={"Authorization": "Bearer other-token"},
        )
        created = await api.post(
            "/api/v1/projects",
            json={
                "name": "Ridge House",
                "location": "East Legon, Accra",
                "timezone": "Africa/Accra",
            },
            headers={
                "Authorization": "Bearer admin-token",
                "Idempotency-Key": "project:ridge-house:001",
            },
        )
        created_replay = await api.post(
            "/api/v1/projects",
            json={
                "name": "Ridge House",
                "location": "East Legon, Accra",
                "timezone": "Africa/Accra",
            },
            headers={
                "Authorization": "Bearer admin-token",
                "Idempotency-Key": "project:ridge-house:001",
            },
        )
        projects = await api.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer admin-token"},
        )
        project_id = created.json()["id"]
        project = await api.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": "Bearer admin-token"},
        )
        snapshot = await api.get(
            f"/api/v1/projects/{project_id}/snapshot",
            headers={"Authorization": "Bearer admin-token"},
        )
        forbidden = await api.get(
            f"/api/v1/projects/{project_id}",
            headers={"Authorization": "Bearer other-token"},
        )

    assert bootstrap.status_code == 200
    assert bootstrap_replay.json()["id"] == bootstrap.json()["id"]
    assert other_bootstrap.status_code == 200
    assert created.status_code == 201
    assert created_replay.json() == created.json()
    assert projects.json()["data"] == [created.json()]
    assert project.json() == created.json()
    assert snapshot.status_code == 200
    assert snapshot.json()["project"] == created.json()
    assert snapshot.json()["tasks"] == []
    assert snapshot.json()["materials"] == []
    assert snapshot.json()["approvals"] == []
    assert snapshot.json()["activities"][0]["title"] == "Created project Ridge House."
    assert forbidden.status_code == 403
    project_reference = client.collection("projects").document(project_id)
    assert project_reference.get().exists
    assert project_reference.collection("members").document(bootstrap.json()["id"]).get().exists
    activities = FirestoreRepository(client, ActivityEvent).list(project_id)
    assert len(activities) == 1
    assert activities[0].action == "project.created"


@pytest.mark.asyncio
async def test_disabled_firestore_user_cannot_bootstrap_or_access_projects() -> None:
    cloud_project = f"oga-auth-disabled-{uuid4().hex}"
    client = firestore.Client(project=cloud_project)
    subject = "firebase-disabled-subject"
    user = User(
        id=canonical_user_id(subject),
        identity_subject=subject,
        display_name="Disabled User",
        email="disabled@example.com",
        status=UserStatus.DISABLED,
    )
    client.collection("users").document(user.id).set(user.model_dump(mode="python"))
    runtime = EmulatorAuthRuntime(
        client,
        FakeTokenVerifier(
            {
                "disabled-token": VerifiedIdentity(
                    subject=subject,
                    email=user.email,
                )
            }
        ),
    )
    transport = httpx.ASGITransport(app=make_app(runtime), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        bootstrap = await api.post(
            "/api/v1/auth/bootstrap",
            json={"display_name": "Disabled User"},
            headers={"Authorization": "Bearer disabled-token"},
        )
        projects = await api.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer disabled-token"},
        )

    assert bootstrap.status_code == 401
    assert projects.status_code == 401
