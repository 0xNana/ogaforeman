"""User-facing knowledge of implemented OG Foreman capabilities."""

from __future__ import annotations

import re


_PRODUCT_HELP_QUESTIONS = tuple(
    re.compile(pattern)
    for pattern in (
        r"how do i get started",
        r"what can you do",
        r"how do i add a site update",
        r"can i send (?:a )?voice(?: note)?",
        r"how do i upload (?:a )?photo",
        r"how do i add (?:a )?photo",
        r"can you read (?:a )?photo",
        r"how do materials work",
        r"how do i create a task",
    )
)


def is_product_help_question(message: str) -> bool:
    """Recognize only bounded, complete product-help utterances."""

    normalized = " ".join(message.casefold().split()).rstrip("?!. ")
    return any(pattern.fullmatch(normalized) for pattern in _PRODUCT_HELP_QUESTIONS)


class ProductKnowledgeService:
    """Answer product questions without reading or mutating project state."""

    def answer(self, message: str) -> str:
        normalized = " ".join(message.casefold().split())
        if "get started" in normalized or "start" in normalized:
            return (
                "Start by telling me what's happening on site. You can type an update, record a "
                "voice note, or add photos. For example: ‘Ground-floor blockwork started today. "
                "We have 60 bags of cement and the electrician comes tomorrow.’ I'll organize "
                "supported updates into tasks, materials, issues, and the daily log."
            )
        if "voice" in normalized:
            return "Yes. Record a voice site update in the composer and I'll process it with the project."
        if "photo" in normalized or "image" in normalized:
            return "Yes. Add site photos in the composer with a short note so I can use them as evidence."
        return (
            "You can tell me what happened on site, ask about current work, get grounded advice, "
            "and update supported tasks, materials, issues, and daily logs. I can also flag blockers "
            "and material risks, prepare consequential actions, and pause for approval when needed."
        )


__all__ = ["ProductKnowledgeService", "is_product_help_question"]
