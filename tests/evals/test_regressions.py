from pathlib import Path

from app.evals.runner import EvalReport


def test_checked_in_deliberate_regression_artifact_proves_gate_failure() -> None:
    report = EvalReport.model_validate_json(
        Path("artifacts/evals/deliberate-regression.json").read_text(encoding="utf-8")
    )

    regression = next(case for case in report.cases if case.id == "negated_electrician")
    assert report.adapter == "deliberate-regression"
    assert report.passed is False
    assert regression.passed is False
    assert regression.mutation_diff.forbidden == ["task.complete:tsk_electrical"]
