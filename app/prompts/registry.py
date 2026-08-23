"""Typed registry for production prompt files, not ADK agent declarations."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PromptId(StrEnum):
    SITE_REPORT = "site_report"
    INTENT_ROUTER = "intent_router"
    ACTION_INTERPRETER = "action_interpreter"
    AGENTIC_CONVERSATION = "agentic_conversation"


class PromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: PromptId
    purpose: str = Field(min_length=1, max_length=300)
    prompt_file: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*\.txt$")
    prompt_version: str = Field(default="v1", pattern=r"^[a-z0-9][a-z0-9._-]*$")


class PromptRegistry:
    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self.manifest_path = Path(manifest_path or Path(__file__).with_name("manifest.yaml"))
        self.prompts: dict[PromptId, PromptConfig] = {}
        self._load()

    def _load(self) -> None:
        data = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8")) or {}
        prompt_entries = data.get("prompts", [])
        if not isinstance(prompt_entries, list):
            raise ValueError("prompt manifest 'prompts' must be a list")
        for raw_config in prompt_entries:
            config = PromptConfig.model_validate(raw_config)
            if config.name in self.prompts:
                raise ValueError(f"Duplicate prompt name found: {config.name}")
            prompt_path = self.manifest_path.parent / config.prompt_file
            if not prompt_path.is_file():
                raise ValueError(f"Prompt file not found for {config.name}: {config.prompt_file}")
            self.prompts[config.name] = config

    def get_prompt_config(self, name: PromptId | str) -> PromptConfig:
        prompt_id = PromptId(name)
        if prompt_id not in self.prompts:
            raise KeyError(f"Prompt {prompt_id} not found in registry")
        return self.prompts[prompt_id]

    def get_prompt(self, name: PromptId | str) -> str:
        config = self.get_prompt_config(name)
        return (self.manifest_path.parent / config.prompt_file).read_text(encoding="utf-8")


prompt_registry = PromptRegistry()


__all__ = ["PromptConfig", "PromptId", "PromptRegistry", "prompt_registry"]
