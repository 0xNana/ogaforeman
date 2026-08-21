from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.project_import_extraction import (
    GeminiProjectImportExtractor,
    ProjectImportCandidate,
    _gemini_candidate_schema,
)
from app.config.settings import Settings
from app.evals.project_import import (
    ProjectImportEvalCase,
    evaluate_project_import_candidate,
    load_project_import_dataset,
    run_project_import_evaluation,
)


def _candidate() -> ProjectImportCandidate:
    return ProjectImportCandidate.model_validate(
        {
            "project": {"name": "Ridge House"},
            "tasks": [{"temp_id": "tmp_task_plastering", "name": "Plastering"}],
            "materials": [
                {
                    "temp_id": "tmp_material_cement",
                    "name": "Cement",
                    "canonical_unit": "bags",
                }
            ],
            "material_requirements": [
                {
                    "task_temp_id": "tmp_task_plastering",
                    "material_temp_id": "tmp_material_cement",
                    "required_quantity": Decimal("100"),
                    "unit": "bags",
                }
            ],
        }
    )


class _FixtureExtractor:
    async def extract(self, source_text: str) -> ProjectImportCandidate:
        del source_text
        return _candidate()


class _FailingExtractor:
    async def extract(self, source_text: str) -> ProjectImportCandidate:
        del source_text
        raise RuntimeError("private provider detail")


@pytest.mark.asyncio
async def test_live_extractor_uses_developer_api_compatible_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_content = AsyncMock(return_value=SimpleNamespace(text=_candidate().model_dump_json()))
    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    monkeypatch.setattr(
        "app.infrastructure.gemini.create_gemini_client",
        Mock(return_value=client),
    )
    extractor = GeminiProjectImportExtractor(
        Settings(
            _env_file=None,
            use_fake_model=False,
            gemini_api_key="developer-key",
            gemini_model_id="configured-model",
        )
    )

    result = await extractor.extract("Ridge House plastering plan")

    assert result.project.name == "Ridge House"
    config = generate_content.await_args.kwargs["config"]
    assert config.response_json_schema is not None
    assert config.response_schema is None


def test_live_extractor_can_force_vertex_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    create_client = Mock(
        return_value=SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock()))
        )
    )
    monkeypatch.setattr("app.infrastructure.gemini.create_gemini_client", create_client)
    settings = Settings(
        _env_file=None,
        use_fake_model=False,
        google_cloud_project="oga-eval",
        gemini_location="global",
        gemini_model_id="configured-model",
    )

    GeminiProjectImportExtractor(settings, prefer_vertex=True)

    create_client.assert_called_once_with(settings, prefer_vertex=True)


def test_generation_schema_omits_vertex_unsupported_constraints() -> None:
    schema = _gemini_candidate_schema()
    encoded = str(schema)

    assert "additionalProperties" not in encoded
    assert "pattern" not in encoded
    assert "format" not in encoded
    assert "ProjectImportCandidate" in encoded
    assert set(schema["required"]) == set(schema["properties"])


def test_structured_requirement_assertions_pass_on_draft_references() -> None:
    dataset = load_project_import_dataset(Path("evals/project_import_v1.json"))

    result = evaluate_project_import_candidate(dataset.cases[0], _candidate())

    assert result.passed is True
    assert all(assertion.passed for assertion in result.assertions)


def test_eval_fails_closed_when_ambiguous_quantity_becomes_a_requirement() -> None:
    case = ProjectImportEvalCase.model_validate(
        {
            "id": "ambiguous",
            "category": "ambiguous_requirement",
            "source": "quantity undecided",
            "expected": {
                "forbid_material_requirements": True,
                "require_unresolved_warning": True,
            },
        }
    )

    result = evaluate_project_import_candidate(case, _candidate())

    assert result.passed is False
    failed = {assertion.name for assertion in result.assertions if not assertion.passed}
    assert failed == {"ambiguous_requirement_absent", "unresolved_warning"}


@pytest.mark.asyncio
async def test_report_records_registry_model_time_sha_and_assertions() -> None:
    dataset = load_project_import_dataset(Path("evals/project_import_v1.json"))
    single_case = dataset.model_copy(update={"cases": [dataset.cases[0]]})

    report = await run_project_import_evaluation(
        single_case,
        _FixtureExtractor(),
        model_id="fixture-model",
    )

    assert report.passed is True
    assert report.prompt_registry_key == "project_import_extraction.v1"
    assert report.model_registry_key == "project_import_gemini.configured"
    assert report.model_id == "fixture-model"
    assert report.generated_at.tzinfo is not None
    assert report.commit_sha
    assert report.cases[0].assertions


@pytest.mark.asyncio
async def test_live_failure_becomes_safe_failing_artifact_result() -> None:
    dataset = load_project_import_dataset(Path("evals/project_import_v1.json"))
    single_case = dataset.model_copy(update={"cases": [dataset.cases[0]]})

    report = await run_project_import_evaluation(
        single_case,
        _FailingExtractor(),
        model_id="failing-model",
    )

    assert report.passed is False
    assertion = report.cases[0].assertions[0]
    assert assertion.name == "extraction_succeeded"
    assert assertion.detail == "live extraction failed with RuntimeError"
    assert "private provider detail" not in report.model_dump_json()
