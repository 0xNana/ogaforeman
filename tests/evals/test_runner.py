from pathlib import Path

import pytest

from app.evals.runner import (
    DeliberateRegressionAdapter,
    FixtureEvalAdapter,
    _gemini_eval_prompt,
    load_dataset,
    run_evaluation,
)


@pytest.mark.asyncio
async def test_locked_fixture_eval_passes_all_mutation_and_policy_thresholds() -> None:
    dataset = load_dataset(Path("evals/site_updates_v1.json"))
    report = await run_evaluation(dataset, FixtureEvalAdapter())
    assert report.passed is True
    assert report.metrics.case_pass_rate == 1
    assert report.metrics.safety_stop_recall == 1
    assert report.metrics.approval_policy_precision == 1


@pytest.mark.asyncio
async def test_eval_fails_when_a_regression_allows_forbidden_mutation() -> None:
    dataset = load_dataset(Path("evals/site_updates_v1.json"))
    report = await run_evaluation(dataset, DeliberateRegressionAdapter())
    assert report.passed is False
    assert report.cases[3].mutation_diff.forbidden == ["task.complete:tsk_electrical"]


def test_gemini_eval_prompt_provides_authorized_context_without_expected_answers() -> None:
    dataset = load_dataset(Path("evals/site_updates_v1.json"))
    case = dataset.cases[0]

    prompt = _gemini_eval_prompt(case)

    assert "tsk_plumbing" in prompt
    assert "task.complete:<task_id>" in prompt
    assert "required_mutations" not in prompt
    assert "forbidden_mutations" not in prompt
