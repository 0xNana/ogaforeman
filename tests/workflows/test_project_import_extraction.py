from typing import Any
from decimal import Decimal

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.project_import_execution import AdkProjectImportExecutor
from app.agents.project_import_extraction import (
    ProjectImportCandidate,
    build_project_import_app,
    build_project_import_workflow,
)
from app.domain.project_import import (
    PROJECT_IMPORT_STATUS_TRANSITIONS,
    DraftTaskStatus,
    ProjectImportStatus,
)
from app.config.settings import Settings
from app.repositories.memory import InMemoryRepositoryStore


class FakeProjectExtractor:
    async def extract(self, source_text: str) -> ProjectImportCandidate:
        assert "Foundation" in source_text
        return ProjectImportCandidate.model_validate(
            {
                "project": {"name": "Imported residence"},
                "phases": [{"temp_id": "tmp_phase_one", "name": "Substructure", "sequence": 1}],
                "tasks": [
                    {
                        "temp_id": "tmp_task_foundation",
                        "name": "Foundation",
                        "phase_temp_id": "tmp_phase_one",
                        "initial_status": DraftTaskStatus.PLANNED,
                    }
                ],
                "materials": [],
            }
        )


class AliasUnitProjectExtractor:
    async def extract(self, source_text: str) -> ProjectImportCandidate:
        return ProjectImportCandidate.model_validate(
            {
                "project": {"name": "Imported residence"},
                "tasks": [{"temp_id": "tmp_task_foundation", "name": "Foundation"}],
                "materials": [
                    {
                        "temp_id": "tmp_material_cement",
                        "name": "Cement",
                        "canonical_unit": "pices",
                        "initial_on_hand_quantity": Decimal("10"),
                    }
                ],
                "material_requirements": [
                    {
                        "task_temp_id": "tmp_task_foundation",
                        "material_temp_id": "tmp_material_cement",
                        "required_quantity": Decimal("2"),
                        "unit": "pcs",
                    }
                ],
            }
        )


def test_project_import_status_transition_table_is_complete_and_terminal_safe() -> None:
    assert PROJECT_IMPORT_STATUS_TRANSITIONS == {
        ProjectImportStatus.UPLOADED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.EXTRACTING: frozenset(
            {
                ProjectImportStatus.DRAFT,
                ProjectImportStatus.EXTRACTION_FAILED,
                ProjectImportStatus.CANCELLED,
            }
        ),
        ProjectImportStatus.DRAFT: frozenset(
            {ProjectImportStatus.VALIDATING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.VALIDATING: frozenset(
            {
                ProjectImportStatus.NEEDS_REVIEW,
                ProjectImportStatus.VALIDATION_FAILED,
                ProjectImportStatus.CANCELLED,
            }
        ),
        ProjectImportStatus.NEEDS_REVIEW: frozenset(
            {ProjectImportStatus.CONFIRMED, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.CONFIRMED: frozenset({ProjectImportStatus.IMPORTING}),
        ProjectImportStatus.IMPORTING: frozenset(
            {ProjectImportStatus.IMPORTED, ProjectImportStatus.IMPORT_FAILED}
        ),
        ProjectImportStatus.EXTRACTION_FAILED: frozenset(
            {ProjectImportStatus.EXTRACTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.VALIDATION_FAILED: frozenset({ProjectImportStatus.CANCELLED}),
        ProjectImportStatus.IMPORT_FAILED: frozenset(
            {ProjectImportStatus.IMPORTING, ProjectImportStatus.CANCELLED}
        ),
        ProjectImportStatus.IMPORTED: frozenset(),
        ProjectImportStatus.CANCELLED: frozenset(),
    }


def test_project_import_graph_exposes_native_extraction_nodes() -> None:
    workflow = build_project_import_workflow(
        source_text="Task: Foundation",
        project_id="prj_extract123",
        import_id="imp_extract123",
        source_id="src_extract123",
        extractor=FakeProjectExtractor(),
    )

    assert workflow.graph is not None
    assert [node.name for node in workflow.graph.nodes if node.name != "__START__"] == [
        "source_received",
        "load_source",
        "gemini_extraction",
        "schema_validation",
        "normalize_draft",
        "deterministic_validation",
        "needs_review",
    ]


@pytest.mark.asyncio
async def test_project_import_runner_records_extraction_trace() -> None:
    app = build_project_import_app(
        "project-import-test",
        source_text="Task: Foundation",
        project_id="prj_extract123",
        import_id="imp_extract123",
        source_id="src_extract123",
        extractor=FakeProjectExtractor(),
        timeout_seconds=10,
    )
    runner = Runner(
        app=app,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )

    events = [
        event
        async for event in runner.run_async(
            user_id="usr_extract123",
            session_id="imp_extract123",
            invocation_id="evt_extract123",
            new_message=types.Content(
                role="user", parts=[types.Part(text="Extract this project source.")]
            ),
        )
    ]

    node_names = {
        node_name
        for event in events
        if event.actions and event.actions.agent_state
        for node_name in event.actions.agent_state.get("nodes", {})
    }
    assert {
        "source_received",
        "load_source",
        "gemini_extraction",
        "schema_validation",
        "normalize_draft",
        "deterministic_validation",
        "needs_review",
    } <= node_names


@pytest.mark.asyncio
async def test_workflow_normalizes_gemini_unit_aliases_before_validation() -> None:
    app = build_project_import_app(
        "project-import-normalization-test",
        source_text="Task: Foundation",
        project_id="prj_extract123",
        import_id="imp_extract123",
        source_id="src_extract123",
        extractor=AliasUnitProjectExtractor(),
        timeout_seconds=10,
    )
    runner = Runner(
        app=app,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )

    events = [
        event
        async for event in runner.run_async(
            user_id="usr_extract123",
            session_id="imp_extract123",
            invocation_id="evt_normalize123",
            new_message=types.Content(role="user", parts=[types.Part(text="Extract source.")]),
        )
    ]

    draft = next(
        event.actions.state_delta["draft"]
        for event in events
        if event.actions and "draft" in event.actions.state_delta
    )
    assert draft["materials"][0]["canonical_unit"] == "pieces"
    assert draft["material_requirements"][0]["unit"] == "pieces"


@pytest.mark.asyncio
async def test_adk_project_import_executor_returns_the_typed_draft(tmp_path: Any) -> None:
    settings = Settings(
        use_fake_model=True,
        adk_session_backend="database",
        adk_session_database_url=f"sqlite+aiosqlite:///{tmp_path / 'executor.db'}",
        agent_workflow_timeout_seconds=45,
        event_claim_lease_seconds=60,
    )
    executor = AdkProjectImportExecutor(
        InMemoryRepositoryStore(),
        settings,
        FakeProjectExtractor(),
    )

    draft = await executor.extract(
        project_id="prj_extract123",
        import_id="imp_executor123",
        source_id="src_executor123",
        source_text="Task: Foundation",
    )

    assert draft.id == "imp_executor123"
    assert draft.project_id == "prj_extract123"
    assert draft.source_id == "src_executor123"
    assert draft.tasks[0].name == "Foundation"
