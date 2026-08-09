from scripts.run_capacity_baseline import run_capacity_baseline


def test_initial_capacity_envelope_preserves_state_integrity() -> None:
    evidence = run_capacity_baseline()

    assert evidence.passed is True
    assert {scenario.name: scenario.count for scenario in evidence.scenarios} == {
        "100_project_partitions": 100,
        "25_concurrent_site_updates": 25,
        "10_duplicate_deliveries": 10,
        "concurrent_approval_decisions": 10,
        "100_project_scheduler_burst": 100,
    }
    assert all(scenario.passed for scenario in evidence.scenarios)
