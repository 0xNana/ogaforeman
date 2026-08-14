"""Run Phase 17 evaluations against the production conversation API pipeline."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest


RUNTIME_CASES: dict[str, str] = {
    "grounded_query_no_mutation": "test_advice_is_grounded_and_does_not_emit_mutation_activity",
    "material_typed_mutation": "test_routine_material_action_dispatches_through_typed_service_and_replays",
    "task_and_issue_typed_mutations": "test_routine_task_and_issue_actions_use_typed_services",
    "schedule_pending_no_mutation": "test_project_change_is_proposed_audited_and_replay_safe",
    "schedule_confirm_and_duplicate": "test_server_proposal_confirmation_executes_once_and_consumes_command",
    "purchase_approval_no_external_action": "test_purchase_routes_to_existing_durable_approval_workflow_exactly_once",
    "stale_proposal": "test_confirmation_rejects_stale_state_and_browser_command_payload",
    "cancelled_proposal": "test_pending_proposal_can_be_reloaded_and_cancelled_without_domain_mutation",
    "unauthorized_command": "test_unauthorized_conversation_action_is_rejected_without_mutation",
    "ambiguous_entity": "test_ambiguous_entity_requests_clarification_without_mutation",
    "expired_proposal": "test_expired_unreserved_proposal_is_rejected_without_mutation",
}


class _ReportCollector:
    def __init__(self) -> None:
        self.outcomes: dict[str, list[str]] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when in {"setup", "call"} and (report.failed or report.when == "call"):
            self.outcomes.setdefault(report.nodeid, []).append(report.outcome)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default="artifacts/evals/conversation-runtime-latest.json"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    collector = _ReportCollector()
    exit_code = pytest.main(
        ["-q", "tests/integration/test_conversation_api.py"], plugins=[collector]
    )
    case_results = []
    for case_id, test_name in RUNTIME_CASES.items():
        matched = [
            outcome
            for node_id, outcomes in collector.outcomes.items()
            if test_name in node_id
            for outcome in outcomes
        ]
        case_results.append(
            {
                "id": case_id,
                "passed": bool(matched) and all(item == "passed" for item in matched),
                "executed_test_count": len(matched),
            }
        )
    passed = exit_code == pytest.ExitCode.OK and all(
        item["passed"] for item in case_results
    )
    artifact = {
        "suite": "phase17-conversation-runtime-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "adapter": "production-api-typed-services",
        "passed": passed,
        "cases": case_results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Conversation runtime eval passed={passed} artifact={output}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
