from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.facts import ExtractedFactSet


@dataclass(frozen=True, slots=True)
class MediaEvidence:
    attachment_id: str
    content_type: str
    data: bytes = field(repr=False)


class SiteInterpreter(Protocol):
    async def transcribe_audio(self, media: MediaEvidence) -> str: ...

    async def extract_facts(
        self,
        text: str,
        *,
        images: Sequence[MediaEvidence] = (),
        project_context: str = "",
    ) -> ExtractedFactSet: ...


class FakeSiteInterpreter:
    def __init__(
        self,
        responses: dict[str, ExtractedFactSet] | None = None,
        *,
        transcriptions: dict[str, str] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.transcriptions = transcriptions or {}
        self.calls: list[str] = []
        self.transcription_calls: list[MediaEvidence] = []
        self.image_calls: list[tuple[MediaEvidence, ...]] = []
        self.project_context_calls: list[str] = []

    async def transcribe_audio(self, media: MediaEvidence) -> str:
        self.transcription_calls.append(media)
        return self.transcriptions.get(media.attachment_id, "")

    async def extract_facts(
        self,
        text: str,
        *,
        images: Sequence[MediaEvidence] = (),
        project_context: str = "",
    ) -> ExtractedFactSet:
        self.calls.append(text)
        self.image_calls.append(tuple(images))
        self.project_context_calls.append(project_context)
        if text in self.responses:
            return self.responses[text]
        return ExtractedFactSet()


__all__ = ["FakeSiteInterpreter", "MediaEvidence", "SiteInterpreter"]
