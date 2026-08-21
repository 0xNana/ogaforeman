"""Typed runtime registry for project-import extraction."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectImportRuntimeRegistry:
    workflow_name: str = "project_import_extraction_workflow"
    prompt_key: str = "project_import_extraction.v1"
    model_key: str = "project_import_gemini.configured"
    prompt_file: str = "project_import_extraction_v1.txt"

    def render_prompt(self, source_text: str) -> str:
        instructions = _prompt_text(self.prompt_file)
        return (
            f"{instructions}\n\n"
            "<untrusted_project_source>\n"
            f"{source_text}\n"
            "</untrusted_project_source>"
        )


@lru_cache(maxsize=4)
def _prompt_text(filename: str) -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / filename
    return path.read_text(encoding="utf-8").strip()


PROJECT_IMPORT_RUNTIME = ProjectImportRuntimeRegistry()


__all__ = ["PROJECT_IMPORT_RUNTIME", "ProjectImportRuntimeRegistry"]
