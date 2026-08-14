from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.conversation import EntityKind, EntityResolutionStatus
from app.domain.enums import MemberRole, TaskStatus
from app.domain.models import Task
from app.repositories.memory import InMemoryRepositoryStore
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService


def access(project_id: str = "prj_memory123") -> ProjectAccessContext:
    return ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_ace123", subject="ace"),
        project_id=project_id,
        role=MemberRole.MANAGER,
    )


def test_memory_is_scoped_and_revalidates_referenced_entities() -> None:
    store = InMemoryRepositoryStore()
    store.repository(Task).create(
        Task(
            id="tsk_electrical123",
            project_id="prj_memory123",
            title="Electrical rough-in",
            status=TaskStatus.BLOCKED,
        )
    )
    service = ConversationMemoryService(store, ConversationEntityResolver(store))

    saved = service.remember_reference(
        access(), EntityKind.TASK, "tsk_electrical123", topic="electrical"
    )
    resolved = service.resolve_recent(access(), EntityKind.TASK)

    assert saved.actor_id == "usr_ace123"
    assert resolved.status is EntityResolutionStatus.RESOLVED
    assert resolved.entity_id == "tsk_electrical123"
    assert service.load(access("prj_other123")).recent_entities == []


def test_stale_memory_never_becomes_project_truth() -> None:
    store = InMemoryRepositoryStore()
    task = store.repository(Task).create(
        Task(id="tsk_electrical123", project_id="prj_memory123", title="Electrical rough-in")
    )
    service = ConversationMemoryService(store, ConversationEntityResolver(store))
    service.remember_reference(access(), EntityKind.TASK, task.id)
    store.repository(Task).delete(task.project_id, task.id, expected_version=0)

    resolved = service.resolve_recent(access(), EntityKind.TASK)

    assert resolved.status is EntityResolutionStatus.NOT_FOUND
    assert resolved.can_mutate is False
