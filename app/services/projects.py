from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.transaction import Transaction

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext, ensure_project_scope
from app.domain.enums import ActorType, MemberRole, MemberStatus, ProjectStatus
from app.domain.models import ActivityEvent, Project, ProjectMember
from app.infrastructure.firestore import decode_firestore_value, encode_firestore_value


class FirestoreProjectService:
    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def list_for_user(self, actor: AuthenticatedUser) -> Sequence[Project]:
        memberships = (
            self._client.collection_group("members")
            .where(filter=FieldFilter("user_id", "==", actor.user_id))
            .where(filter=FieldFilter("status", "==", MemberStatus.ACTIVE.value))
            .limit(100)
            .stream()
        )
        projects: list[Project] = []
        seen_project_ids: set[str] = set()
        for membership in memberships:
            project_reference = membership.reference.parent.parent
            if project_reference is None:
                continue
            if project_reference.id in seen_project_ids:
                continue
            seen_project_ids.add(project_reference.id)
            snapshot = project_reference.get()
            if snapshot.exists:
                projects.append(
                    Project.model_validate(decode_firestore_value(snapshot.to_dict() or {}))
                )
        return tuple(sorted(projects, key=lambda project: (project.name.casefold(), project.id)))

    def create(
        self,
        actor: AuthenticatedUser,
        *,
        name: str,
        location: str,
        timezone: str,
        idempotency_key: str,
    ) -> Project:
        digest = sha256(f"{actor.user_id}\x00{idempotency_key}".encode()).hexdigest()[:32]
        project = Project(
            id=f"prj_{digest}",
            name=name,
            location=location,
            timezone=timezone,
            status=ProjectStatus.ACTIVE,
            created_by=actor.user_id,
        )
        membership = ProjectMember(
            project_id=project.id,
            user_id=actor.user_id,
            role=MemberRole.ADMIN,
            status=MemberStatus.ACTIVE,
        )
        activity = ActivityEvent(
            id=f"act_{digest}",
            project_id=project.id,
            actor_type=ActorType.USER,
            actor_id=actor.user_id,
            action="project.created",
            entity_type="project",
            entity_id=project.id,
            summary=f"Created project {project.name}.",
        )
        project_reference = self._client.collection("projects").document(project.id)
        transaction = self._client.transaction()

        @firestore.transactional
        def create_in_transaction(active_transaction: Transaction) -> Project:
            existing = project_reference.get(transaction=active_transaction)
            if existing.exists:
                stored = Project.model_validate(decode_firestore_value(existing.to_dict() or {}))
                if stored.created_by != actor.user_id:
                    raise ValueError("idempotency key identifies another project")
                return stored
            active_transaction.create(project_reference, encode_firestore_value(project))
            active_transaction.create(
                project_reference.collection("members").document(actor.user_id),
                encode_firestore_value(membership),
            )
            active_transaction.create(
                project_reference.collection("activity").document(activity.id),
                encode_firestore_value(activity),
            )
            return project

        return create_in_transaction(transaction)

    def require(self, access: ProjectAccessContext) -> Project:
        ensure_project_scope(access, access.project_id)
        snapshot = self._client.collection("projects").document(access.project_id).get()
        if not snapshot.exists:
            raise LookupError("project was not found")
        return Project.model_validate(decode_firestore_value(snapshot.to_dict() or {}))


__all__ = ["FirestoreProjectService"]
