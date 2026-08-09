from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal

from google.cloud import firestore
from pydantic import BaseModel

from app.config.settings import Settings
from app.domain.enums import (
    AttachmentUploadStatus,
    MemberRole,
    MemberStatus,
    ProjectStatus,
    TaskPriority,
    TaskSource,
    TaskStatus,
    UserStatus,
)
from app.domain.models import (
    Attachment,
    Material,
    Project,
    ProjectMember,
    Task,
    User,
)
from app.infrastructure.firestore import assert_demo_environment, create_firestore_client
from app.repositories.firestore import (
    firestore_collection_name,
    firestore_document_data,
    firestore_entity_id,
)


DEMO_PROJECT_ID = "prj_ridge"
DEMO_ADMIN_ID = "usr_admin"
DEMO_MANAGER_ID = "usr_manager"
DEMO_FOREMAN_ID = "usr_foreman"
SEED_TIME = datetime(2026, 8, 7, 8, 0, tzinfo=UTC)


@dataclass(frozen=True)
class SeedResult:
    project_id: str
    document_count: int


def seed_entities(
    project_id: str = DEMO_PROJECT_ID,
) -> tuple[Project, tuple[User, ...], tuple[BaseModel, ...]]:
    """Build deterministic, validated seed entities without performing I/O."""

    project = Project(
        id=project_id,
        name="Ridge Project",
        location="Accra",
        description="Deterministic demo project",
        timezone="Africa/Accra",
        start_date=SEED_TIME.date(),
        target_end_date=(SEED_TIME + timedelta(days=90)).date(),
        status=ProjectStatus.ACTIVE,
        created_by=DEMO_ADMIN_ID,
        created_at=SEED_TIME,
        updated_at=SEED_TIME,
    )
    users = (
        User(
            id=DEMO_ADMIN_ID,
            identity_subject="demo-admin",
            display_name="Oga Admin",
            email="admin@oga-foreman.local",
            status=UserStatus.ACTIVE,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
        User(
            id=DEMO_MANAGER_ID,
            identity_subject="demo-manager",
            display_name="Project Manager",
            email="manager@oga-foreman.local",
            status=UserStatus.ACTIVE,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
        User(
            id=DEMO_FOREMAN_ID,
            identity_subject="demo-foreman",
            display_name="Site Foreman",
            email="foreman@oga-foreman.local",
            status=UserStatus.ACTIVE,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
    )
    tasks = (
        Task(
            id="tsk_foundation",
            project_id=project_id,
            title="Foundation works",
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.HIGH,
            completion_percent=Decimal("100"),
            actual_completion=SEED_TIME - timedelta(days=2),
            source=TaskSource.MANUAL,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
        Task(
            id="tsk_blockwork",
            project_id=project_id,
            title="First-floor blockwork",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            completion_percent=Decimal("80"),
            dependency_ids=["tsk_foundation"],
            source=TaskSource.MANUAL,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
        Task(
            id="tsk_electrical",
            project_id=project_id,
            title="Electrical rough-in",
            status=TaskStatus.PLANNED,
            priority=TaskPriority.HIGH,
            dependency_ids=["tsk_blockwork"],
            source=TaskSource.MANUAL,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
        Task(
            id="tsk_plastering",
            project_id=project_id,
            title="First-floor plastering",
            status=TaskStatus.PLANNED,
            priority=TaskPriority.HIGH,
            planned_start=SEED_TIME + timedelta(days=1),
            planned_end=SEED_TIME + timedelta(days=3),
            dependency_ids=["tsk_blockwork", "tsk_electrical"],
            source=TaskSource.MANUAL,
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        ),
    )
    project_entities: tuple[BaseModel, ...] = (
        *(
            ProjectMember(
                project_id=project_id,
                user_id=user_id,
                role=role,
                status=MemberStatus.ACTIVE,
                created_at=SEED_TIME,
                updated_at=SEED_TIME,
            )
            for user_id, role in (
                (DEMO_ADMIN_ID, MemberRole.ADMIN),
                (DEMO_MANAGER_ID, MemberRole.MANAGER),
                (DEMO_FOREMAN_ID, MemberRole.FOREMAN),
            )
        ),
        *tasks,
        Material(
            id="mat_cement",
            project_id=project_id,
            name="Cement Bags",
            normalized_name="cement bags",
            unit="bags",
            available_quantity=Decimal("25"),
            minimum_required_quantity=Decimal("20"),
            upcoming_requirement_quantity=Decimal("40"),
            updated_at=SEED_TIME,
        ),
        Attachment(
            id="att_demo001",
            project_id=project_id,
            object_path=f"projects/{project_id}/attachments/att_demo001.jpg",
            content_type="image/jpeg",
            byte_size=1,
            sha256="a" * 64,
            upload_status=AttachmentUploadStatus.VERIFIED,
            metadata={"placeholder": True},
            created_at=SEED_TIME,
        ),
        Attachment(
            id="att_demo002",
            project_id=project_id,
            object_path=f"projects/{project_id}/attachments/att_demo002.jpg",
            content_type="image/jpeg",
            byte_size=1,
            sha256="b" * 64,
            upload_status=AttachmentUploadStatus.VERIFIED,
            metadata={"placeholder": True},
            created_at=SEED_TIME,
        ),
    )
    return project, users, project_entities


def seed_demo(client: firestore.Client, *, settings: Settings | None = None) -> SeedResult:
    assert_demo_environment(settings)
    project, users, project_entities = seed_entities()
    batch = client.batch()
    batch.set(client.document("projects", project.id), firestore_document_data(project))
    for user in users:
        batch.set(client.document("users", user.id), firestore_document_data(user))
    for entity in project_entities:
        batch.set(
            client.document(
                "projects",
                project.id,
                firestore_collection_name(type(entity)),
                firestore_entity_id(entity),
            ),
            firestore_document_data(entity),
        )
    batch.commit()
    return SeedResult(project_id=project.id, document_count=1 + len(users) + len(project_entities))


def main() -> None:
    settings = Settings()
    client = create_firestore_client(settings)
    result = seed_demo(client, settings=settings)
    print(f"Seeded {result.document_count} documents for {result.project_id}.")


if __name__ == "__main__":
    main()
