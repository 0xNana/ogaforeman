"""Entity resolution for unstructured text."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from app.domain.models import Task, Material

T = TypeVar("T")


class MatchConfidence(str, Enum):
    HIGH = "high"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResolutionResult(Generic[T]):
    confidence: MatchConfidence
    candidates: list[T]

    @property
    def resolved_entity(self) -> T | None:
        if self.confidence == MatchConfidence.HIGH and len(self.candidates) == 1:
            return self.candidates[0]
        return None


def normalize_text(text: str) -> str:
    normalized = text.casefold().strip()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def resolve_task(query: str, tasks: Sequence[Task]) -> ResolutionResult[Task]:
    norm_query = normalize_text(query)
    if not norm_query:
        return ResolutionResult(MatchConfidence.UNKNOWN, [])

    exact_matches = []
    partial_matches = []

    for task in tasks:
        norm_title = normalize_text(task.title)
        if norm_title == norm_query:
            exact_matches.append(task)
        elif norm_query in norm_title or (
            task.description and norm_query in normalize_text(task.description)
        ):
            partial_matches.append(task)

    if len(exact_matches) == 1:
        return ResolutionResult(MatchConfidence.HIGH, exact_matches)
    if len(exact_matches) > 1:
        return ResolutionResult(MatchConfidence.AMBIGUOUS, exact_matches)

    if len(partial_matches) == 1:
        return ResolutionResult(MatchConfidence.HIGH, partial_matches)
    if len(partial_matches) > 1:
        return ResolutionResult(MatchConfidence.AMBIGUOUS, partial_matches)

    return ResolutionResult(MatchConfidence.UNKNOWN, [])


def resolve_material(query: str, materials: Sequence[Material]) -> ResolutionResult[Material]:
    norm_query = normalize_text(query)
    if not norm_query:
        return ResolutionResult(MatchConfidence.UNKNOWN, [])

    exact_matches = []
    partial_matches = []

    for material in materials:
        names_to_check = [normalize_text(material.name), material.normalized_name]
        for alias in material.aliases:
            names_to_check.append(normalize_text(alias))

        is_exact = False
        is_partial = False
        for name in names_to_check:
            if name == norm_query:
                is_exact = True
            elif norm_query in name:
                is_partial = True

        if is_exact:
            exact_matches.append(material)
        elif is_partial:
            partial_matches.append(material)

    # Remove duplicates
    exact_matches = list({m.id: m for m in exact_matches}.values())
    partial_matches = list({m.id: m for m in partial_matches}.values())

    if len(exact_matches) == 1:
        return ResolutionResult(MatchConfidence.HIGH, exact_matches)
    if len(exact_matches) > 1:
        return ResolutionResult(MatchConfidence.AMBIGUOUS, exact_matches)

    if len(partial_matches) == 1:
        return ResolutionResult(MatchConfidence.HIGH, partial_matches)
    if len(partial_matches) > 1:
        return ResolutionResult(MatchConfidence.AMBIGUOUS, partial_matches)

    return ResolutionResult(MatchConfidence.UNKNOWN, [])
