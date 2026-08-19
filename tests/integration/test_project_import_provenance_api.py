from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import install_error_handlers, install_request_id_middleware
from app.api.v1.router import api_router
from app.domain.authorization import (
    AuthenticatedUser,
    ProjectAccessContext,
    ProjectForbiddenError,
    ProjectPermission,
)
from app.domain.enums import MemberRole
from app.domain.import_records import (
    ImportProvenance,
    ImportProvenanceTargetType,
    import_dependency_target_id,
    import_provenance_id,
)
from app.domain.project_import import SourceType
from app.repositories.memory import InMemoryRepositoryStore


PROJECT_ID = "prj_provenanceapi123"
TARGET_ID = "tsk_foundation123"


def _provenance(
    project_id: str,
    target_id: str = TARGET_ID,
    target_type: ImportProvenanceTargetType = ImportProvenanceTargetType.TASK,
) -> ImportProvenance:
    return ImportProvenance(
        id=import_provenance_id(target_type, target_id),
        project_id=project_id,
        import_id="imp_provenanceapi123",
        source_id="src_provenanceapi123",
        source_checksum="b" * 64,
        source_type=SourceType.MARKDOWN,
        source_name="trusted-plan.md",
        target_entity_type=target_type,
        target_entity_id=target_id,
        section="Substructure",
        imported_by="usr_admin123",
        imported_at=datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
        idempotency_key="project-import:provenance-api:task",
    )


def _make_app(store: InMemoryRepositoryStore) -> FastAPI:
    app = FastAPI()
    app.state.auth_runtime = SimpleNamespace(store=store)

    def access_provider(
        _request: object,
        project_id: str,
        permission: ProjectPermission,
    ) -> ProjectAccessContext:
        if project_id != PROJECT_ID:
            raise ProjectForbiddenError("project access is forbidden")
        assert permission is ProjectPermission.READ
        return ProjectAccessContext(
            actor=AuthenticatedUser(user_id="usr_viewer123", subject="test"),
            project_id=project_id,
            role=MemberRole.VIEWER,
        )

    app.state.project_access_provider = access_provider
    install_request_id_middleware(app)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_provenance_api_explains_a_target_without_exposing_source_content() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ImportProvenance).create(_provenance(PROJECT_ID))
    transport = httpx.ASGITransport(app=_make_app(store), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/projects/{PROJECT_ID}/provenance/task/{TARGET_ID}")
        linked = await client.get(
            f"/api/v1/projects/{PROJECT_ID}/provenance/records/"
            f"{import_provenance_id(ImportProvenanceTargetType.TASK, TARGET_ID)}"
        )

    assert response.status_code == 200
    assert response.json() == {
        "import_id": "imp_provenanceapi123",
        "source_id": "src_provenanceapi123",
        "source_checksum": "b" * 64,
        "source_type": "markdown",
        "source_name": "trusted-plan.md",
        "target_entity_type": "task",
        "target_entity_id": TARGET_ID,
        "section": "Substructure",
        "external_reference": None,
        "imported_by": "usr_admin123",
        "imported_at": "2026-08-19T12:00:00Z",
    }
    assert linked.status_code == 200
    assert linked.json() == response.json()
    assert "content_text" not in response.json()


@pytest.mark.asyncio
async def test_provenance_api_resolves_dependency_from_canonical_task_pair() -> None:
    predecessor_id = "tsk_excavation123"
    dependency_id = import_dependency_target_id(predecessor_id, TARGET_ID)
    store = InMemoryRepositoryStore()
    store.repository(ImportProvenance).create(
        _provenance(
            PROJECT_ID,
            dependency_id,
            ImportProvenanceTargetType.DEPENDENCY,
        )
    )
    transport = httpx.ASGITransport(app=_make_app(store), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/projects/{PROJECT_ID}/provenance/dependencies/{predecessor_id}/{TARGET_ID}"
        )

    assert response.status_code == 200
    assert response.json()["target_entity_type"] == "dependency"
    assert response.json()["target_entity_id"] == dependency_id


@pytest.mark.asyncio
async def test_provenance_api_hides_other_projects_and_rejects_cross_project_access() -> None:
    store = InMemoryRepositoryStore()
    store.repository(ImportProvenance).create(_provenance("prj_other123"))
    transport = httpx.ASGITransport(app=_make_app(store), raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        hidden = await client.get(f"/api/v1/projects/{PROJECT_ID}/provenance/task/{TARGET_ID}")
        hidden_link = await client.get(
            f"/api/v1/projects/{PROJECT_ID}/provenance/records/"
            f"{import_provenance_id(ImportProvenanceTargetType.TASK, TARGET_ID)}"
        )
        forbidden = await client.get(f"/api/v1/projects/prj_other123/provenance/task/{TARGET_ID}")

    assert hidden.status_code == 404
    assert hidden_link.status_code == 404
    assert forbidden.status_code == 403
