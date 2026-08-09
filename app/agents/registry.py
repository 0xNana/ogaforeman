import os
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    name: str
    description: str
    prompt_file: str
    tools: List[str] = Field(default_factory=list)
    sub_agents: List[str] = Field(default_factory=list)


class Registry:
    def __init__(self, manifest_path: str | None = None):
        if not manifest_path:
            manifest_path = os.path.join(
                os.path.dirname(__file__), "..", "prompts", "manifest.yaml"
            )
        self.manifest_path = manifest_path
        self.agents: Dict[str, AgentConfig] = {}
        self.load()

    def load(self):
        with open(self.manifest_path, "r") as f:
            data = yaml.safe_load(f)

        agents_list = data.get("agents", [])
        for config_dict in agents_list:
            name = config_dict["name"]
            if name in self.agents:
                raise ValueError(f"Duplicate agent name found: {name}")

            config = AgentConfig(**config_dict)
            self.agents[name] = config

            prompt_path = os.path.join(os.path.dirname(self.manifest_path), config.prompt_file)
            if not os.path.exists(prompt_path):
                raise ValueError(f"Prompt file not found for agent {name}: {config.prompt_file}")

        for name, config in self.agents.items():
            for sub_agent in config.sub_agents:
                if sub_agent not in self.agents:
                    raise ValueError(
                        f"Sub-agent {sub_agent} referenced by {name} not found in registry"
                    )

    def get_agent_config(self, name: str) -> AgentConfig:
        if name not in self.agents:
            raise KeyError(f"Agent {name} not found in registry")
        return self.agents[name]

    def get_prompt(self, name: str) -> str:
        config = self.get_agent_config(name)
        prompt_path = os.path.join(os.path.dirname(self.manifest_path), config.prompt_file)
        with open(prompt_path, "r") as f:
            return f.read()


registry = Registry()
