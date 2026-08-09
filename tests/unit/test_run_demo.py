from scripts.run_demo import run_local_demo


def test_dry_run_demo_rehearses_three_runs_with_approval_rejection_and_delay() -> None:
    evidence = run_local_demo(mode="dry-run", repetitions=3)

    assert evidence.passed is True
    assert evidence.release_blocked is True
    assert [run.decision for run in evidence.runs] == ["approve", "reject", "approve"]
    assert all(run.continuation_replay_suppressed for run in evidence.runs)
    assert evidence.runs[1].rejection_closed_request is True
    assert evidence.runs[0].delivery_delay_replay_suppressed is True
