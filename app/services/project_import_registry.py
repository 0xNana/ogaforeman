"""Typed model and prompt registry for project-import extraction."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectImportExtractionRegistry:
    prompt_key: str = "project_import_extraction.v3"
    model_key: str = "project_import_gemini.configured"
    prompt_file: str = "project_import_extraction_v3.txt"

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


PROJECT_IMPORT_EXTRACTION = ProjectImportExtractionRegistry()


__all__ = ["PROJECT_IMPORT_EXTRACTION", "ProjectImportExtractionRegistry"]
