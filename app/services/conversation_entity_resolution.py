"""Project-scoped entity resolution before conversational mutations."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.domain.authorization import (
    ProjectAccessContext,
    ProjectPermission,
    ensure_permission,
    ensure_project_scope,
)
from app.domain.conversation import (
    EntityCandidate,
    EntityKind,
    EntityResolution,
    EntityResolutionStatus,
)
from app.domain.enums import MemberStatus
from app.domain.models import DailyReport, Issue, Material, MaterialRequest, ProjectMember, Task
from app.repositories.interfaces import RepositoryStore
from app.services.entity_resolution import normalize_text


@dataclass(frozen=True, slots=True)
class _EntityRecord:
    entity_id: str
    display_name: str
    searchable_names: tuple[str, ...]


class ConversationEntityResolver:
    def __init__(
        self,
        store: RepositoryStore,
        *,
        member_names: Callable[[str], dict[str, str]] | None = None,
        fuzzy_threshold: float = 0.84,
        fuzzy_margin: float = 0.08,
        max_candidates: int = 5,
    ) -> None:
        if not 0.0 <= fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold must be between zero and one")
        if not 0.0 <= fuzzy_margin <= 1.0:
            raise ValueError("fuzzy_margin must be between zero and one")
        if not 1 <= max_candidates <= 5:
            raise ValueError("max_candidates must be between one and five")
        self._store = store
        self._member_names = member_names or (lambda project_id: {})
        self._fuzzy_threshold = fuzzy_threshold
        self._fuzzy_margin = fuzzy_margin
        self._max_candidates = max_candidates

    def resolve(
        self,
        access: ProjectAccessContext,
        kind: EntityKind,
        reference: str,
        *,
        contextual_entity_id: str | None = None,
    ) -> EntityResolution:
        ensure_project_scope(access, access.project_id)
        ensure_permission(access, ProjectPermission.READ)
        normalized = normalize_text(reference)
        if not normalized:
            raise ValueError("entity reference cannot be empty")
        records = self._records(access.project_id, kind)

        if contextual_entity_id:
            contextual = next(
                (record for record in records if record.entity_id == contextual_entity_id), None
            )
            if contextual is not None:
                return _resolved(kind, reference, contextual, "context", 1.0)

        id_match = next((record for record in records if record.entity_id == reference), None)
        if id_match is not None:
            return _resolved(kind, reference, id_match, "id", 1.0)

        exact = [record for record in records if normalized in record.searchable_names]
        if len(exact) == 1:
            return _resolved(kind, reference, exact[0], "exact", 1.0)
        if len(exact) > 1:
            return self._ambiguous(kind, reference, exact, 1.0)

        partial = [
            record
            for record in records
            if any(normalized in name or name in normalized for name in record.searchable_names)
        ]
        if len(partial) == 1:
            return _resolved(kind, reference, partial[0], "partial", 0.95)
        if len(partial) > 1:
            return self._ambiguous(kind, reference, partial, 0.95)

        ranked = sorted(
            (
                (max(_similarity(normalized, name) for name in record.searchable_names), record)
                for record in records
            ),
            key=lambda item: (-item[0], item[1].display_name.casefold(), item[1].entity_id),
        )
        if ranked and ranked[0][0] >= self._fuzzy_threshold:
            if len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= self._fuzzy_margin:
                return _resolved(kind, reference, ranked[0][1], "fuzzy", ranked[0][0])
            close = [item for item in ranked if ranked[0][0] - item[0] < self._fuzzy_margin]
            return self._ambiguous(
                kind,
                reference,
                [record for _, record in close],
                ranked[0][0],
            )
        return EntityResolution(
            kind=kind,
            reference=reference,
            status=EntityResolutionStatus.NOT_FOUND,
            clarification=f"I couldn't find that {kind.value.replace('_', ' ')} in this project.",
        )

    def _ambiguous(
        self,
        kind: EntityKind,
        reference: str,
        records: Sequence[_EntityRecord],
        score: float,
    ) -> EntityResolution:
        ordered = sorted(records, key=lambda item: (item.display_name.casefold(), item.entity_id))[
            : self._max_candidates
        ]
        names = [record.display_name for record in ordered]
        return EntityResolution(
            kind=kind,
            reference=reference,
            status=EntityResolutionStatus.AMBIGUOUS,
            candidates=tuple(
                EntityCandidate(
                    entity_id=record.entity_id,
                    kind=kind,
                    display_name=record.display_name,
                    match_score=score,
                )
                for record in ordered
            ),
            clarification=(
                f"Which {kind.value.replace('_', ' ')} do you mean — {_choices(names)}?"
            ),
        )

    def _records(self, project_id: str, kind: EntityKind) -> tuple[_EntityRecord, ...]:
        if kind in {EntityKind.TASK, EntityKind.SCHEDULE_ACTIVITY}:
            return tuple(
                _record(
                    task.id, task.title, task.title, task.description, task.trade, task.location
                )
                for task in self._store.repository(Task).list(project_id)
            )
        if kind is EntityKind.ISSUE:
            return tuple(
                _record(issue.id, issue.description, issue.description, issue.type.value)
                for issue in self._store.repository(Issue).list(project_id)
            )
        if kind is EntityKind.MATERIAL:
            return tuple(
                _record(
                    material.id,
                    material.name,
                    material.name,
                    material.normalized_name,
                    *material.aliases,
                )
                for material in self._store.repository(Material).list(project_id)
            )
        if kind is EntityKind.MATERIAL_REQUEST:
            materials = {
                material.id: material
                for material in self._store.repository(Material).list(project_id)
            }
            return tuple(
                _record(
                    request.id,
                    f"{materials[request.material_id].name} request"
                    if request.material_id in materials
                    else "Material request",
                    request.reason,
                    materials[request.material_id].name
                    if request.material_id in materials
                    else None,
                    f"{materials[request.material_id].name} request"
                    if request.material_id in materials
                    else None,
                )
                for request in self._store.repository(MaterialRequest).list(project_id)
            )
        if kind is EntityKind.PROJECT_MEMBER:
            names = self._member_names(project_id)
            return tuple(
                _record(
                    member.user_id,
                    names.get(member.user_id, "Project member"),
                    names.get(member.user_id),
                )
                for member in self._store.repository(ProjectMember).list(project_id)
                if member.status is MemberStatus.ACTIVE
            )
        return tuple(
            _record(
                report.id,
                f"Daily log for {report.report_date.isoformat()}",
                report.report_date.isoformat(),
                report.summary,
            )
            for report in self._store.repository(DailyReport).list(project_id)
        )


def _record(
    entity_id: str,
    display_name: str,
    *names: str | None,
) -> _EntityRecord:
    searchable = tuple(
        dict.fromkeys(normalized for name in names if name if (normalized := normalize_text(name)))
    )
    return _EntityRecord(entity_id, display_name, searchable or (normalize_text(display_name),))


def _resolved(
    kind: EntityKind,
    reference: str,
    record: _EntityRecord,
    method: str,
    score: float,
) -> EntityResolution:
    return EntityResolution(
        kind=kind,
        reference=reference,
        status=EntityResolutionStatus.RESOLVED,
        entity_id=record.entity_id,
        display_name=record.display_name,
        match_method=method,
        candidates=(
            EntityCandidate(
                entity_id=record.entity_id,
                kind=kind,
                display_name=record.display_name,
                match_score=score,
            ),
        ),
        can_mutate=True,
    )


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _choices(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} or {names[1]}"
    return f"{', '.join(names[:-1])}, or {names[-1]}"


__all__ = ["ConversationEntityResolver"]
