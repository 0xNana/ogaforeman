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
    ProjectReadinessState,
    ProjectSetupStatus,
)
from app.services.product_knowledge import ProductKnowledgeService


class ConversationResponseService:
    def respond(
        self,
        route: IntentRoute,
        *,
        context: ConversationalProjectContext | None = None,
    ) -> ConversationReply:
        if route.destination is IntentDestination.CASUAL_RESPONSE:
            return self.casual()
        if route.destination is IntentDestination.PRODUCT_HELP:
            return self.help("")
        if route.destination is IntentDestination.PROJECT_CONTEXT:
            if context is None:
                raise ValueError("project context is required for a grounded project reply")
            return self.project(context)
        if route.destination is IntentDestination.CLARIFICATION:
            if route.decision.intent.value == "unknown" and route.decision.reason_code in {
                "no_classification",
                "empty_model_response",
            }:
                return ConversationReply(
                    kind=ReplyKind.CLARIFICATION,
                    text=(
                        "I'm not sure what you mean yet. If you're getting started, tell me what's "
                        "happening on site or ask about tasks, materials, issues, or today's work."
                    ),
                )
            return ConversationReply(
                kind=ReplyKind.CLARIFICATION,
                text=route.decision.ambiguity or "Could you clarify what you need?",
            )
        raise ValueError(
            f"destination {route.destination.value} belongs to a later or operational workflow"
        )

    def casual(self) -> ConversationReply:
        return ConversationReply(kind=ReplyKind.CASUAL, text="What's up?")

    def help(self, message: str) -> ConversationReply:
        return ConversationReply(
            kind=ReplyKind.HELP,
            text=ProductKnowledgeService().answer(message),
        )

    def project_setup(self, status: ProjectSetupStatus) -> ConversationReply:
        if not status.project_exists:
            return _project_reply(
                "Not yet. Create or open a project first, then tell me what's happening on site "
                "and I'll start organizing it."
            )
        name = status.project_name or "The project"
        if status.readiness_state is ProjectReadinessState.EMPTY:
            return _project_reply(
                f"{name} is created, but it's still mostly empty. The fastest way to get it going "
                "is to tell me what's happening on site today — work underway, materials on hand, "
                "blockers, or what's planned next."
            )
        if status.readiness_state is ProjectReadinessState.PARTIALLY_CONFIGURED:
            return _project_reply(
                f"{name} has some project records, but it needs tasks before OG can reason "
                "usefully about the work."
            )
        facts = [f"I have {_count(status.task_count, 'task')}"]
        if status.dependency_count:
            facts.append(f"{status.dependency_count} dependencies")
        if status.material_requirement_task_count:
            facts.append(
                "material requirements for "
                + _count(status.material_requirement_task_count, "task")
            )
        if status.planned_tasks_without_material_requirements:
            facts.append(
                f"{status.planned_tasks_without_material_requirements} planned activities "
                "without material requirements"
            )
        if status.open_issue_count:
            facts.append(f"{_count(status.open_issue_count, 'open issue')}")
        if status.has_materials:
            facts.append("materials are being tracked")
        return _project_reply(f"Yes. {name} is operational. " + _join_facts(facts) + ".")

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
        if domains == {ContextDomain.MATERIALS, ContextDomain.MATERIAL_REQUESTS}:
            if context.query.search_terms:
                return _entity_status(context)
            return _material_status(context)
        if context.query.search_terms:
            return _entity_status(context)
        return _overview(context)


def _overview(context: ConversationalProjectContext) -> ConversationReply:
    parts: list[str] = []
    refs: list[str] = []
    if context.project is not None:
        parts.append(f"{context.project.name} is {context.project.status}.")
    completed = [task for task in context.tasks if task.status == "completed"]
    active = [task for task in context.tasks if task.status == "in_progress"]
    blocked = [task for task in context.tasks if task.status == "blocked"]
    upcoming = [task for task in context.tasks if task.status in {"planned", "proposed"}]
    if completed:
        parts.append(" ".join(f"{task.title} is done." for task in completed[:3]))
        refs.extend(task.id for task in completed[:3])
    if active:
        parts.append("In progress: " + ", ".join(task.title for task in active[:3]) + ".")
        refs.extend(task.id for task in active[:3])
    blocked_without_issue = [
        task for task in blocked if not any(task.id in issue.task_ids for issue in context.issues)
    ]
    if blocked_without_issue:
        parts.append(
            "Blocked: " + ", ".join(task.title for task in blocked_without_issue[:3]) + "."
        )
        refs.extend(task.id for task in blocked_without_issue[:3])
    if upcoming:
        parts.append("Next: " + ", ".join(task.title for task in upcoming[:3]) + ".")
        refs.extend(task.id for task in upcoming[:3])
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
        return _project_reply("I don't have any persisted project activity to report yet.")
    return _project_reply(" ".join(parts), refs)


def _entity_status(context: ConversationalProjectContext) -> ConversationReply:
    if (
        not context.tasks
        and not context.issues
        and not context.materials
        and not context.material_requirements
    ):
        return _project_reply("I can't find a matching activity in this project.")
    if context.tasks:
        task = context.tasks[0]
        status = task.status.replace("_", " ")
        text = f"{task.title} is {status}."
        if task.completion_percent:
            text += f" It is {_quantity(task.completion_percent)}% complete."
        if task.assignee_name:
            text += f" {task.assignee_name} is assigned."
        if task.actual_completion:
            text += f" It was completed on {task.actual_completion.date().isoformat()}."

        issue = next((item for item in context.issues if task.id in item.task_ids), None)
        refs = [task.id]
        if issue:
            text += f" Blocker: {_sentence(issue.description)}"
            refs.append(issue.id)

        search_terms = context.query.search_terms
        if any(term in ("after", "slips", "delayed", "happens") for term in search_terms):
            dependents = [t for t in context.tasks if task.id in t.dependency_ids]
            if dependents:
                text += f" {', '.join(t.title for t in dependents)} depends on it."
                refs.extend(t.id for t in dependents)
            else:
                text += " Nothing depends on it."

        if (
            any(term in ("need", "needs", "require", "requires") for term in search_terms)
            and context.material_requirements
        ):
            reqs = [r for r in context.material_requirements if r.task_id == task.id]
            if reqs:
                mat_dict = {m.id: m.name for m in context.materials}
                req_texts = [
                    f"{_quantity(r.required_quantity)} {r.unit} of {mat_dict.get(r.material_id, 'material')}"
                    for r in reqs
                ]
                text += f" It requires {' and '.join(req_texts)}."
                refs.extend(r.id for r in reqs)

        return _project_reply(text, refs)
    if context.issues:
        issue = context.issues[0]
        return _project_reply(_sentence(issue.description), (issue.id,))
    material = context.materials[0]
    return _project_reply(
        f"{material.name} has {_quantity(material.available_quantity)} {material.unit} available.",
        (material.id,),
    )


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
        (record_id for issue in issues for record_id in (issue.id, *issue.task_ids)),
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


def _material_status(context: ConversationalProjectContext) -> ConversationReply:
    if not context.materials:
        return _project_reply("I don't see any materials being tracked for this project.")
    shown = context.materials[:3]
    return _project_reply(
        " ".join(
            f"We have {_quantity(item.available_quantity)} {item.unit} of {item.name}."
            for item in shown
        ),
        (item.id for item in shown),
    )


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


def _join_facts(facts: list[str]) -> str:
    if len(facts) == 1:
        return facts[0]
    if len(facts) == 2:
        return " and ".join(facts)
    return ", ".join(facts[:-1]) + ", and " + facts[-1]


__all__ = ["ConversationResponseService"]
