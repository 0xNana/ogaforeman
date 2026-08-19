"""Durable project-source persistence for import provenance and reprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from app.domain.activity import ActivitySpec, MutationContext
from app.domain.authorization import ProjectAccessContext, ProjectPermission, ensure_permission
from app.domain.enums import ActorType
from app.domain.import_records import ProjectSource, ProjectSourceStatus
from app.domain.project_import import SourceType
from app.domain.models import ActivityEvent
from app.repositories.activity import ActivityRepository
from app.repositories.interfaces import RepositoryStore
from app.repositories.membership import AuthorizedProjectRepository


class ProjectSourceConflictError(ValueError):
    code = "PROJECT_SOURCE_CONFLICT"


@dataclass(frozen=True, slots=True)
class ProjectSourceResult:
    source: ProjectSource
    replayed: bool = False


class ProjectSourceService:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def persist_text(
        self,
        access: ProjectAccessContext,
        *,
        source_id: str,
        name: str,
        text: str,
        source_type: SourceType = SourceType.MARKDOWN,
    ) -> ProjectSourceResult:
        ensure_permission(access, ProjectPermission.MANAGE)
        source = ProjectSource.from_text(
            id=source_id,
            project_id=access.project_id,
            source_type=source_type,
            name=name,
            text=text,
            created_by=access.actor.user_id,
        )

        def operation(session):
            repository = AuthorizedProjectRepository(
                session.repository(ProjectSource),
                access,
                mutation_permission=ProjectPermission.MANAGE,
            )
            existing = repository.get(access.project_id, source_id)
            if existing is not None:
                if existing.checksum != source.checksum or existing.project_id != source.project_id:
                    raise ProjectSourceConflictError(
                        f"source {source_id} already exists with different content"
                    )
                return ProjectSourceResult(source=existing, replayed=True)
            repository.create(source)
            context = MutationContext(
                project_id=access.project_id,
                actor_type=ActorType.USER,
                actor_id=access.actor.user_id,
                idempotency_key=f"project-source:{source_id}:created",
            )
            AuthorizedProjectRepository(
                session.repository(ActivityEvent),
                access,
                mutation_permission=ProjectPermission.MANAGE,
            ).create(
                ActivityRepository.build_event(
                    context,
                    ActivitySpec(
                        action="project.source.created",
                        entity_type="project_source",
                        entity_id=source_id,
                        summary="Stored a project source for import provenance and reprocessing.",
                        metadata={"source_type": source.type.value, "checksum": source.checksum},
                    ),
                )
            )
            return ProjectSourceResult(source=source)

        return self._store.run_transaction(operation)

    def archive(self, access: ProjectAccessContext, source_id: str) -> ProjectSource:
        ensure_permission(access, ProjectPermission.MANAGE)

        def operation(session):
            repository = AuthorizedProjectRepository(
                session.repository(ProjectSource),
                access,
                mutation_permission=ProjectPermission.MANAGE,
            )
            source = repository.require(access.project_id, source_id)
            if source.status == ProjectSourceStatus.ARCHIVED:
                return source
            archived = repository.save(
                source.model_copy(update={"status": ProjectSourceStatus.ARCHIVED}),
                expected_version=source.version,
            )
            AuthorizedProjectRepository(
                session.repository(ActivityEvent),
                access,
                mutation_permission=ProjectPermission.MANAGE,
            ).create(
                ActivityRepository.build_event(
                    MutationContext(
                        project_id=access.project_id,
                        actor_type=ActorType.USER,
                        actor_id=access.actor.user_id,
                        idempotency_key=f"project-source:{source_id}:archived",
                    ),
                    ActivitySpec(
                        action="project.source.archived",
                        entity_type="project_source",
                        entity_id=source_id,
                        summary="Archived a project source from future imports.",
                        metadata={},
                    ),
                )
            )
            return archived

        return self._store.run_transaction(operation)


__all__ = ["ProjectSourceConflictError", "ProjectSourceResult", "ProjectSourceService"]
