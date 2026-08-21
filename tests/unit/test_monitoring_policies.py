from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / "infra" / "monitoring"


def test_phase8_monitoring_policy_templates_are_complete_and_bounded() -> None:
    expected = {
        "api-5xx-rate.json",
        "api-latency.json",
        "pubsub-queue-age.json",
        "dead-letter-count.json",
        "backup-failure.json",
        "project-import-stuck.json",
        "project-import-extraction-failures.json",
        "project-import-commit-failures.json",
    }
    policies = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in POLICY_DIR.glob("*.json")
    }

    assert set(policies) == expected
    for name, policy in policies.items():
        assert policy["enabled"] is True
        assert policy["combiner"] == "OR"
        assert policy["documentation"]["mimeType"] == "text/markdown"
        assert len(policy["conditions"]) == 1
        threshold = policy["conditions"][0]["conditionThreshold"]
        assert threshold["trigger"] == {"count": 1}
        assert threshold["comparison"] == "COMPARISON_GT"
        assert threshold["aggregations"]
        assert "metric.type=" in threshold["filter"], name


def test_monitoring_templates_only_use_documented_placeholders() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(POLICY_DIR.glob("*.json"))
    )

    assert "${PROJECT_ID}" not in source
    assert source.count("${API_SERVICE}") == 3
    assert source.count("${WORKER_SUBSCRIPTION}") == 1
    assert source.count("${DEAD_LETTER_SUBSCRIPTION}") == 1


def test_repeated_import_failure_rate_represents_more_than_two_in_five_minutes() -> None:
    policy = json.loads(
        (POLICY_DIR / "project-import-extraction-failures.json").read_text(encoding="utf-8")
    )
    threshold = policy["conditions"][0]["conditionThreshold"]

    assert threshold["aggregations"][0]["alignmentPeriod"] == "300s"
    assert threshold["aggregations"][0]["perSeriesAligner"] == "ALIGN_RATE"
    assert 2 / 300 < threshold["thresholdValue"] < 3 / 300


def test_monitoring_apply_matches_policy_names_client_side_without_duplicates() -> None:
    source = (POLICY_DIR / "apply.sh").read_text(encoding="utf-8")

    assert "--format=json" in source
    assert 'item.get("displayName") == target' in source
    assert "multiple alert policies matched" in source
    assert '--filter "displayName=' not in source
