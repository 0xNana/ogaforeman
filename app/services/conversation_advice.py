"""Grounded project recommendations with a strict read-only boundary."""

from __future__ import annotations

import re
from decimal import Decimal

from app.domain.conversation import (
    AdviceReply,
    ContextDomain,
    ContextQuery,
    ConversationalProjectContext,
)


_ADVICE_DOMAINS = (
    ContextDomain.TASKS,
    ContextDomain.SCHEDULE,
    ContextDomain.ISSUES,
    ContextDomain.MATERIALS,
    ContextDomain.MATERIAL_REQUESTS,
    ContextDomain.APPROVALS,
)
_STOP_WORDS = frozenset({"wdyt", "what", "do", "you", "think", "about", "tomorrow", "today"})


def plan_advice_query(message: str) -> ContextQuery:
    terms = tuple(
        word for word in re.findall(r"[a-z0-9]+", message.casefold()) if word not in _STOP_WORDS
    )[:8]
    return ContextQuery(domains=_ADVICE_DOMAINS, search_terms=terms)


class ConversationAdviceService:
    def advise(self, message: str, context: ConversationalProjectContext) -> AdviceReply:
        del message  # The recommendation is derived only from the authorized snapshot.
        refs: list[str] = []
        risks: list[str] = []
        subject = context.tasks[0] if context.tasks else None
        if subject is not None:
            refs.append(subject.id)
        low = next(
            (
                item
                for item in context.materials
                if item.available_quantity - item.reserved_quantity
                < max(
                    item.minimum_required_quantity,
                    item.upcoming_requirement_quantity or Decimal("0"),
                )
            ),
            None,
        )
        if low is not None:
            required = max(
                low.minimum_required_quantity, low.upcoming_requirement_quantity or Decimal("0")
            )
            risks.append(
                f"{low.name} is at {low.available_quantity:g} {low.unit}, below the {required:g} required"
            )
            refs.append(low.id)
        if context.issues:
            issue = context.issues[0]
            risks.append(issue.description.rstrip("."))
            refs.append(issue.id)
        if risks:
            return AdviceReply(
                text=f"I'd hold off committing yet. {'; '.join(risks)}.",
                recommendation="hold",
                cited_record_ids=tuple(dict.fromkeys(refs)),
            )
        if subject is None:
            return AdviceReply(
                text="I don't have enough recorded project context to recommend a change yet.",
                recommendation="review",
            )
        return AdviceReply(
            text=f"{subject.title} looks clear to proceed based on the current recorded state.",
            recommendation="proceed",
            cited_record_ids=(subject.id,),
        )


__all__ = ["ConversationAdviceService", "plan_advice_query"]
