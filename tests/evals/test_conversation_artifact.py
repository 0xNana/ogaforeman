from pathlib import Path

from app.evals.conversation import ConversationEvalReport


def test_checked_in_conversation_regression_artifact_proves_gate_failure() -> None:
    report = ConversationEvalReport.model_validate_json(
        Path("artifacts/evals/conversation-deliberate-regression.json").read_text(encoding="utf-8")
    )

    assert report.adapter == "conversation-regression:unsafe_mutation"
    assert report.passed is False
    failed = next(case for case in report.cases if case.id == "ambiguous_completion")
    assert failed.passed is False
    assert "mutation_count" in failed.mismatches
