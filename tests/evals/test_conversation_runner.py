from pathlib import Path

import pytest

from app.evals.conversation import (
    REQUIRED_CONVERSATION_CATEGORIES,
    ConversationFixtureAdapter,
    ConversationGuardRegressionAdapter,
    _gemini_conversation_prompt,
    load_conversation_dataset,
    run_conversation_evaluation,
)


DATASET = Path("evals/conversations_v1.json")


def test_locked_dataset_covers_every_required_category_once_or_more() -> None:
    dataset = load_conversation_dataset(DATASET)

    assert {case.category for case in dataset.cases} == REQUIRED_CONVERSATION_CATEGORIES
    assert len({case.id for case in dataset.cases}) == len(dataset.cases)


def test_dataset_validation_rejects_missing_required_category(tmp_path: Path) -> None:
    raw = DATASET.read_text(encoding="utf-8").replace(
        '      "category": "permissions",',
        '      "category": "casual",',
        1,
    )
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="missing required conversational eval categories"):
        load_conversation_dataset(incomplete)


def test_dataset_validation_rejects_thresholds_outside_probability_range(
    tmp_path: Path,
) -> None:
    raw = DATASET.read_text(encoding="utf-8").replace(
        '"routing_accuracy": 1.0',
        '"routing_accuracy": 1.01',
        1,
    )
    invalid = tmp_path / "invalid-threshold.json"
    invalid.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="less than or equal to 1"):
        load_conversation_dataset(invalid)


def test_dataset_validation_rejects_category_label_swaps(tmp_path: Path) -> None:
    raw = DATASET.read_text(encoding="utf-8")
    raw = raw.replace(
        '"expected": {"intent": "casual"',
        '"expected": {"intent": "project_query"',
        1,
    )
    invalid = tmp_path / "swapped-categories.json"
    invalid.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid expected route"):
        load_conversation_dataset(invalid)


@pytest.mark.asyncio
async def test_fixture_benchmark_passes_every_release_threshold() -> None:
    dataset = load_conversation_dataset(DATASET)

    report = await run_conversation_evaluation(dataset, ConversationFixtureAdapter())

    assert report.passed is True
    assert all(value == 1 for value in report.metrics.model_dump().values())
    assert all(case.passed for case in report.cases)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("guard", "case_id"),
    [
        ("unsafe_mutation", "ambiguous_completion"),
        ("approval_bypass", "approval_purchase"),
        ("external_action_bypass", "approval_purchase"),
        ("permission_bypass", "viewer_task_mutation"),
        ("unauthorized_mutation", "viewer_task_mutation"),
        ("duplicate_suppression_bypass", "duplicate_task_command"),
        ("duplicate_side_effect", "duplicate_task_command"),
        ("stale_conflict_bypass", "stale_material_quantity"),
        ("stale_overwrite", "stale_material_quantity"),
        ("memory_as_truth", "multi_turn_task_reference"),
        ("missing_audit", "task_completion"),
        ("fabricated_audit", "task_completion"),
        ("unauthorized_grounding", "project_blocker_query"),
    ],
)
async def test_each_control_regression_fails_the_gate(guard: str, case_id: str) -> None:
    dataset = load_conversation_dataset(DATASET)

    report = await run_conversation_evaluation(dataset, ConversationGuardRegressionAdapter(guard))

    assert report.passed is False
    failed = {case.id for case in report.cases if not case.passed}
    assert case_id in failed


def test_gemini_prompt_contains_contract_but_not_locked_answers() -> None:
    case = load_conversation_dataset(DATASET).cases[0]

    prompt = _gemini_conversation_prompt(case)

    assert "AUTHORIZED PROJECT CONTEXT" in prompt
    assert "CONVERSATION TURN" in prompt
    assert "fake_prediction" not in prompt
    assert "expected" not in prompt.casefold()
