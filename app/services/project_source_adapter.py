"""Structured text ingestion boundary for project initialization sources."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

from app.domain.project_import import SourceType


class StructuredTextInputError(ValueError):
    code = "PROJECT_SOURCE_INVALID"


@dataclass(frozen=True, slots=True)
class StructuredTextSource:
    """Normalized source payload handed to the extraction workflow."""

    name: str
    source_type: SourceType
    text: str
    checksum: str


class StructuredTextProjectAdapter:
    """Accept reasonable pasted text, Markdown, and OG-template variation.

    This adapter deliberately does not extract canonical entities. It only
    normalizes source text so the ADK/Gemini extraction boundary receives a
    stable, bounded document while preserving evidence and unresolved dates.
    """

    # Keep inline Firestore source documents safely below the 1 MiB document
    # limit, including UTF-8 expansion and document metadata.
    _MAX_SOURCE_CHARS = 800_000
    _DATE_LABELS = re.compile(r"^(due|date|finish|finished by|planned finish)\s*:\s*(.+)$", re.I)
    _TASK_LABEL = re.compile(r"^(?:task|activity|work item)\s*:\s*(.+)$", re.I)
    _DEPENDENCY_LABEL = re.compile(r"^(?:depends on|dependency|predecessor)\s*:\s*(.+)$", re.I)
    _MATERIALS_HEADING = re.compile(r"^(?:materials?|material requirements?)\s*:?\s*$", re.I)

    def __init__(
        self, *, name: str = "pasted-project.txt", source_type: SourceType | None = None
    ) -> None:
        if not name.strip():
            raise StructuredTextInputError("source name cannot be empty")
        self._name = name.strip()
        self._source_type = source_type or self._infer_source_type(name)

    def load(self, text: str) -> StructuredTextSource:
        normalized = self.normalize_input(text)
        return StructuredTextSource(
            name=self._name,
            source_type=self._source_type,
            text=normalized,
            checksum=sha256(normalized.encode("utf-8")).hexdigest(),
        )

    def normalize_input(self, text: str) -> str:
        if not isinstance(text, str):
            raise StructuredTextInputError("structured project source must be text")
        if not text.strip():
            raise StructuredTextInputError("structured project source cannot be empty")
        if len(text) > self._MAX_SOURCE_CHARS or len(text.encode("utf-8")) > 800_000:
            raise StructuredTextInputError("structured project source exceeds the input limit")

        normalized_lines: list[str] = []
        for raw_line in (
            unicodedata.normalize("NFKC", text)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .split("\n")
        ):
            line = raw_line.strip()
            if not line:
                if normalized_lines and normalized_lines[-1] != "":
                    normalized_lines.append("")
                continue
            line = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", line)
            line = self._normalize_label(line)
            normalized_lines.append(line)

        while normalized_lines and normalized_lines[-1] == "":
            normalized_lines.pop()
        if not normalized_lines:
            raise StructuredTextInputError("structured project source cannot be empty")
        return "\n".join(normalized_lines) + "\n"

    def extract(self, text: str) -> str:
        """Return normalized source text for the ADK/Gemini extraction step."""

        return self.load(text).text

    def _normalize_label(self, line: str) -> str:
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            line = heading.group(1).strip()
        task = self._TASK_LABEL.match(line)
        if task:
            return f"Task: {task.group(1).strip()}"
        dependency = self._DEPENDENCY_LABEL.match(line)
        if dependency:
            return f"Depends on: {dependency.group(1).strip()}"
        date_match = self._DATE_LABELS.match(line)
        if date_match:
            return f"Due: {date_match.group(2).strip()}"
        if self._MATERIALS_HEADING.match(line):
            return "Materials:"
        return line

    @staticmethod
    def _infer_source_type(name: str) -> SourceType:
        lowered = name.casefold()
        if lowered.endswith((".md", ".markdown")):
            return SourceType.MARKDOWN
        return SourceType.TEXT


__all__ = ["StructuredTextInputError", "StructuredTextProjectAdapter", "StructuredTextSource"]
