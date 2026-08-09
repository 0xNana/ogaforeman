import pytest
import json
from pathlib import Path
from app.domain.facts import ExtractedFactSet, ConfidenceLevel, TaskCompletionFact
from app.agents.interpreter import FakeSiteInterpreter


@pytest.mark.asyncio
async def test_fake_interpreter_returns_empty_by_default():
    interpreter = FakeSiteInterpreter()
    result = await interpreter.extract_facts("Hello")
    assert isinstance(result, ExtractedFactSet)
    assert len(result.tasks) == 0
    assert len(result.materials) == 0
    assert len(result.safety_issues) == 0
    assert interpreter.calls == ["Hello"]


@pytest.mark.asyncio
async def test_fake_interpreter_returns_configured_response():
    response = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                task_name="Framing",
                is_completed=True,
                evidence="Finished framing",
                confidence=ConfidenceLevel.HIGH,
            )
        ]
    )
    interpreter = FakeSiteInterpreter({"Finished framing": response})
    result = await interpreter.extract_facts("Finished framing")
    assert len(result.tasks) == 1
    assert result.tasks[0].task_name == "Framing"


def test_eval_fixtures_format():
    evals_path = Path(__file__).parent.parent.parent / "evals" / "site_updates.json"
    with open(evals_path) as f:
        data = json.load(f)
    assert len(data) == 5
    ids = [item["id"] for item in data]
    assert "explicit_completion" in ids
    assert "absence_negation" in ids
    assert "ambiguity" in ids
    assert "material_quantity" in ids
    assert "safety" in ids
