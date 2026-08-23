"""Versioned prompt profiles consumed by bounded Gemini adapters."""

from app.prompts.registry import PromptConfig, PromptId, PromptRegistry, prompt_registry

__all__ = ["PromptConfig", "PromptId", "PromptRegistry", "prompt_registry"]
