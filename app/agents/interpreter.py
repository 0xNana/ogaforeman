from typing import Protocol
from app.domain.facts import ExtractedFactSet


class SiteInterpreter(Protocol):
    async def extract_facts(self, text: str) -> ExtractedFactSet: ...


class FakeSiteInterpreter:
    def __init__(self, responses: dict[str, ExtractedFactSet] | None = None):
        self.responses = responses or {}
        self.calls: list[str] = []

    async def extract_facts(self, text: str) -> ExtractedFactSet:
        self.calls.append(text)
        if text in self.responses:
            return self.responses[text]
        return ExtractedFactSet()
