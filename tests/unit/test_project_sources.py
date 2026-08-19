import hashlib

import pytest

from app.domain.authorization import AuthenticatedUser, ProjectAccessContext
from app.domain.enums import MemberRole
from app.domain.import_records import ProjectSource, ProjectSourceStatus
from app.repositories.memory import InMemoryRepositoryStore
from app.services.project_sources import ProjectSourceConflictError, ProjectSourceService


def test_pasted_text_source_persists_checksum_and_replays() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_source123", subject="test"),
        project_id="prj_source123",
        role=MemberRole.ADMIN,
    )
    service = ProjectSourceService(store)
    text = "# Foundation\n100 bags of cement"

    first = service.persist_text(
        access,
        source_id="src_source123",
        name="plan.md",
        text=text,
    )
    replay = service.persist_text(
        access,
        source_id="src_source123",
        name="plan.md",
        text=text,
    )

    assert first.source.checksum == hashlib.sha256(text.encode()).hexdigest()
    assert first.source.content_text == text
    assert replay.replayed
    assert (
        store.repository(ProjectSource).require("prj_source123", "src_source123").status
        == ProjectSourceStatus.ACTIVE
    )

    with pytest.raises(ProjectSourceConflictError):
        service.persist_text(
            access,
            source_id="src_source123",
            name="plan.md",
            text="changed",
        )


def test_archiving_a_source_is_idempotent_and_emits_one_activity() -> None:
    store = InMemoryRepositoryStore()
    access = ProjectAccessContext(
        actor=AuthenticatedUser(user_id="usr_source123", subject="test"),
        project_id="prj_source123",
        role=MemberRole.ADMIN,
    )
    service = ProjectSourceService(store)
    service.persist_text(
        access,
        source_id="src_source123",
        name="plan.md",
        text="# Foundation",
    )

    first = service.archive(access, "src_source123")
    replay = service.archive(access, "src_source123")

    assert first.status == ProjectSourceStatus.ARCHIVED
    assert replay == first
