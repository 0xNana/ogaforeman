from pathlib import Path

import pytest
from google.adk.agents import LlmAgent

from app.agents.factory import create_agent
from app.agents.registry import Registry


def test_registry_loads_manifest():
    registry = Registry()

    assert "oga_coordinator" in registry.agents
    assert "site_report" in registry.agents
    assert "planner" in registry.agents
    assert "materials" in registry.agents
    assert "communicator" in registry.agents
    assert "intent_router" in registry.agents

    coord = registry.get_agent_config("oga_coordinator")
    assert "site_report" in coord.sub_agents
    assert all(not config.tools for config in registry.agents.values())


def test_registry_duplicate_name(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("""
agents:
  - name: test_agent
    description: "test"
    prompt_file: "test.txt"
  - name: test_agent
    description: "test 2"
    prompt_file: "test.txt"
""")

    (tmp_path / "test.txt").write_text("test")

    with pytest.raises(ValueError, match="Duplicate agent name found: test_agent"):
        Registry(str(manifest_path))


def test_registry_missing_prompt(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("""
agents:
  - name: test_agent
    description: "test"
    prompt_file: "missing.txt"
""")

    with pytest.raises(ValueError, match="Prompt file not found for agent test_agent: missing.txt"):
        Registry(str(manifest_path))


def test_registry_missing_sub_agent(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("""
agents:
  - name: root
    description: "test"
    prompt_file: "root.txt"
    sub_agents:
      - missing
""")
    (tmp_path / "root.txt").write_text("test")

    with pytest.raises(
        ValueError, match="Sub-agent missing referenced by root not found in registry"
    ):
        Registry(str(manifest_path))


def test_factory_creates_agent():
    agent = create_agent("communicator")
    assert isinstance(agent, LlmAgent)
    assert agent.name == "communicator"
    assert "briefs" in agent.instruction


def test_factory_creates_coordinator_with_subagents():
    agent = create_agent("oga_coordinator")
    assert isinstance(agent, LlmAgent)
    assert agent.name == "oga_coordinator"
    assert len(agent.sub_agents) == 4
    sub_names = [sub.name for sub in agent.sub_agents]
    assert "site_report" in sub_names
    assert "planner" in sub_names
    assert "materials" in sub_names
    assert "communicator" in sub_names
