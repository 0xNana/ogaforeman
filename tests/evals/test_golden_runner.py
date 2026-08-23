from __future__ import annotations

import pytest

from app.agents.interpreter import FakeSiteInterpreter
from app.evals.golden import (
    GOLDEN_CHECK_IDS,
    GOLDEN_UPDATE_TEXT,
    golden_fixture_fact_set,
    run_golden_evaluation,
)
from tests.fakes import FakeProjectNotificationGateway


@pytest.mark.asyncio
async def test_golden_operational_eval_passes_all_eight_checks() -> None:
    interpreter = FakeSiteInterpreter(responses={GOLDEN_UPDATE_TEXT: golden_fixture_fact_set()})

    report = await run_golden_evaluation(
        interpreter,
        adapter="fixture",
        model_id=None,
        backend="fixture",
        notification_gateway=FakeProjectNotificationGateway(),
    )

    assert report.passed is True
    assert report.metrics.case_pass_rate == 1
    assert report.metrics.canonical_entity_resolution_accuracy == 1
    assert tuple(check.id for check in report.checks) == GOLDEN_CHECK_IDS
    assert all(check.passed for check in report.checks)
    assert interpreter.calls == [GOLDEN_UPDATE_TEXT]


@pytest.mark.asyncio
async def test_golden_operational_eval_fails_when_electrical_blocker_is_missing() -> None:
    prediction = golden_fixture_fact_set().model_copy(update={"issues": []})
    interpreter = FakeSiteInterpreter(responses={GOLDEN_UPDATE_TEXT: prediction})

    report = await run_golden_evaluation(
        interpreter,
        adapter="fixture-regression",
        model_id=None,
        backend="fixture",
        notification_gateway=FakeProjectNotificationGateway(),
    )

    checks = {check.id: check for check in report.checks}
    assert report.passed is False
    assert checks["electrical_blocker"].passed is False
    assert report.metrics.case_pass_rate < 1


@pytest.mark.asyncio
async def test_live_golden_eval_rejects_dirty_source_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.evals.golden._worktree_dirty", lambda: True)
    interpreter = FakeSiteInterpreter(responses={GOLDEN_UPDATE_TEXT: golden_fixture_fact_set()})

    report = await run_golden_evaluation(
        interpreter,
        adapter="gemini",
        model_id="configured-model",
        backend="vertex",
        cloud_project="configured-project",
        cloud_location="global",
        notification_gateway=FakeProjectNotificationGateway(),
    )

    assert all(check.passed for check in report.checks)
    assert report.source_tree_dirty is True
    assert report.passed is False
