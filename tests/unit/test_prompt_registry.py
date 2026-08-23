from pathlib import Path

import pytest
from pydantic import ValidationError

from app.prompts import PromptId, PromptRegistry


def test_registry_contains_only_production_prompt_profiles() -> None:
    registry = PromptRegistry()

    assert set(registry.prompts) == set(PromptId)
    assert registry.get_prompt_config(PromptId.SITE_REPORT).prompt_version == "v2"
    assert "Extract every independent fact" in registry.get_prompt(PromptId.SITE_REPORT)


def test_registry_rejects_duplicate_prompt_name(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
prompts:
  - name: site_report
    purpose: first
    prompt_file: site_report.txt
  - name: site_report
    purpose: duplicate
    prompt_file: site_report.txt
""",
        encoding="utf-8",
    )
    (tmp_path / "site_report.txt").write_text("test", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate prompt name found: site_report"):
        PromptRegistry(manifest_path)


def test_registry_rejects_missing_prompt_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
prompts:
  - name: site_report
    purpose: extraction
    prompt_file: missing.txt
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Prompt file not found for site_report: missing.txt"):
        PromptRegistry(manifest_path)


def test_registry_rejects_unknown_agent_shaped_declaration(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
prompts:
  - name: site_report
    purpose: extraction
    prompt_file: site_report.txt
    sub_agents: [planner]
""",
        encoding="utf-8",
    )
    (tmp_path / "site_report.txt").write_text("test", encoding="utf-8")

    with pytest.raises(ValidationError, match="sub_agents"):
        PromptRegistry(manifest_path)
