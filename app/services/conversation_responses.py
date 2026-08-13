"""Concise deterministic replies grounded only in authorized project context."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from app.domain.conversation import (
    ContextDomain,
    ContextFocus,
    ConversationReply,
    ConversationalProjectContext,
    IntentDestination,
    IntentRoute,
    ReplyKind,
)


class ConversationResponseService:
    def respond(
        self,
        route: IntentRoute,
        *,
        context: ConversationalProjectContext | None = None,
    ) -> ConversationReply:
        if route.destination is IntentDestination.CASUAL_RESPONSE:
            return self.casual()
        if route.destination is IntentDestination.PROJECT_CONTEXT:
            if context is None:
                raise ValueError("project context is required for a grounded project reply")
            return self.project(context)
        if route.destination is IntentDestination.CLARIFICATION:
            return ConversationReply(
                kind=ReplyKind.CLARIFICATION,
                text=route.decision.ambiguity or "Could you clarify what you need?",
            )
        raise ValueError(
            f"destination {route.destination.value} belongs to a later or operational workflow"
        )

    def casual(self) -> ConversationReply:
        return ConversationReply(kind=ReplyKind.CASUAL, text="What's up?")

    def project(self, context: ConversationalProjectContext) -> ConversationReply:
        focus = context.query.focus
        domains = set(context.query.domains)
        if focus is ContextFocus.TODAY:
            return _today(context)
        if focus is ContextFocus.OVERDUE:
            return _schedule(context, overdue=True)
        if focus is ContextFocus.TOMORROW:
            return _schedule(context, overdue=False)
        if focus is ContextFocus.LOW_STOCK:
            return _materials(context)
        if focus is ContextFocus.PENDING:
            return _approvals(context)
        if ContextDomain.PROJECT_MEMBERS in domains:
            return _owner(context)
        if ContextDomain.DAILY_LOGS in domains and context.query.search_terms:
            return _risk(context)
        if domains == {ContextDomain.ISSUES, ContextDomain.TASKS}:
            return _blockers(context)
        return _overview(context)


def _overview(context: ConversationalProjectContext) -> ConversationReply:
    parts: list[str] = []
    refs: list[str] = []
    completed = next((task for task in context.tasks if task.status == "completed"), None)
    if completed is not None:
        parts.append(f"{completed.title} is done.")
        refs.append(completed.id)
    if context.issues:
        parts.append(_sentence(context.issues[0].description))
        refs.append(context.issues[0].id)
    low = next(
        (
            material
            for material in context.materials
            if material.available_quantity - material.reserved_quantity
            < max(
                material.minimum_required_quantity,
                material.upcoming_requirement_quantity or Decimal("0"),
            )
        ),
        None,
    )
    if low is not None:
        parts.append(f"{low.name} is down to {_quantity(low.available_quantity)} {low.unit}.")
        refs.append(low.id)
    if context.approvals:
        count = len(context.approvals)
        parts.append(f"{_count(count, 'approval')} needs you.")
        refs.extend(item.id for item in context.approvals)
    if not parts:
        return _project_reply("I don't see any urgent project changes right now.")
    return _project_reply(" ".join(parts), refs)


def _today(context: ConversationalProjectContext) -> ConversationReply:
    if context.daily_logs:
        item = context.daily_logs[0]
        return _project_reply(_sentence(item.summary), (item.id,))
    if context.recent_activity:
        activity_items = context.recent_activity[:2]
        return _project_reply(
            "Today: " + " ".join(_sentence(item.summary) for item in activity_items),
            (item.id for item in activity_items),
        )
    if context.tasks:
        task_items = context.tasks[:2]
        return _project_reply(
            "Today, " + " and ".join(f"{item.title} was completed" for item in task_items) + ".",
            (item.id for item in task_items),
        )
    return _project_reply("I don't see any recorded project activity today.")


def _blockers(context: ConversationalProjectContext) -> ConversationReply:
    if not context.issues:
        return _project_reply("I don't see any active blockers in the project.")
    issues = context.issues[:3]
    return _project_reply(
        " ".join(_sentence(issue.description) for issue in issues),
        (issue.id for issue in issues),
    )


def _schedule(
    context: ConversationalProjectContext,
    *,
    overdue: bool,
) -> ConversationReply:
    tasks = context.schedule or context.tasks
    if not tasks:
        return _project_reply(
            "I don't see any overdue work."
            if overdue
            else "I don't see any work scheduled for tomorrow."
        )
    shown = tasks[:3]
    if len(shown) == 1:
        text = f"{shown[0].title} is {'overdue' if overdue else 'planned for tomorrow'}."
    else:
        titles = ", ".join(task.title for task in shown)
        text = f"{'Overdue' if overdue else 'Planned for tomorrow'}: {titles}."
    return _project_reply(text, (task.id for task in shown))


def _materials(context: ConversationalProjectContext) -> ConversationReply:
    if not context.materials:
        return _project_reply("I don't see any materials below their recorded requirement.")
    shown = context.materials[:3]
    return _project_reply(
        " ".join(
            f"{item.name} is down to {_quantity(item.available_quantity)} {item.unit}."
            for item in shown
        ),
        (item.id for item in shown),
    )


def _approvals(context: ConversationalProjectContext) -> ConversationReply:
    if not context.approvals:
        return _project_reply("Nothing is waiting for approval.")
    count = len(context.approvals)
    first = context.approvals[0]
    text = f"{_count(count, 'approval')} needs you: {_sentence(first.reason)}"
    return _project_reply(text, (item.id for item in context.approvals))


def _owner(context: ConversationalProjectContext) -> ConversationReply:
    if not context.tasks:
        return _project_reply("I couldn't find a matching task in this project.")
    task = context.tasks[0]
    if not task.assignee_name:
        return _project_reply(f"{task.title} does not have an assignee yet.", (task.id,))
    return _project_reply(
        f"{task.assignee_name} owns {task.title}.",
        (task.id,),
    )


def _risk(context: ConversationalProjectContext) -> ConversationReply:
    if context.issues:
        issue = context.issues[0]
        subject = context.tasks[0].title if context.tasks else "That work"
        return _project_reply(
            f"{subject} is at risk because {_lower_sentence(issue.description)}",
            _risk_refs(context, issue.id),
        )
    if context.daily_logs and context.daily_logs[0].active_blockers:
        report = context.daily_logs[0]
        return _project_reply(
            _sentence(report.active_blockers[0]),
            (report.id,),
        )
    return _project_reply("I don't see a recorded reason that work is at risk.")


def _risk_refs(context: ConversationalProjectContext, issue_id: str) -> tuple[str, ...]:
    if context.tasks:
        return (context.tasks[0].id, issue_id)
    return (issue_id,)


def _project_reply(text: str, refs: Iterable[str] = ()) -> ConversationReply:
    return ConversationReply(
        kind=ReplyKind.PROJECT,
        text=" ".join(text.split())[:1000],
        cited_record_ids=tuple(dict.fromkeys(refs)),
    )


def _sentence(value: str) -> str:
    text = " ".join(value.split()).strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _lower_sentence(value: str) -> str:
    text = _sentence(value)
    return text[:1].casefold() + text[1:]


def _quantity(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))


def _count(count: int, noun: str) -> str:
    if count == 1:
        return f"One {noun}"
    return f"{count} {noun}s"


__all__ = ["ConversationResponseService"]
