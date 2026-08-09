from dataclasses import dataclass

from app.domain.facts import (
    BaseFact,
    ExtractedFactSet,
    IssueFact,
    MaterialQuantityFact,
    NextFocusFact,
    SafetyIssueFact,
    TaskCompletionFact,
)
from app.domain.policies import assess_safety_stop_policy, is_actionable_fact


@dataclass
class RoutedFacts:
    actionable_tasks: list[TaskCompletionFact]
    actionable_materials: list[MaterialQuantityFact]
    actionable_issues: list[IssueFact]
    actionable_next_focus: list[NextFocusFact]
    safety_stops: list[SafetyIssueFact]
    clarifications: list[BaseFact]
    observations: list[BaseFact]


def route_facts(fact_set: ExtractedFactSet) -> RoutedFacts:
    actionable_tasks: list[TaskCompletionFact] = []
    actionable_materials: list[MaterialQuantityFact] = []
    actionable_issues: list[IssueFact] = []
    actionable_next_focus: list[NextFocusFact] = []
    safety_stops: list[SafetyIssueFact] = []
    clarifications: list[BaseFact] = []
    observations: list[BaseFact] = []

    # Process safety issues first to see if we need a safety stop
    if assess_safety_stop_policy(fact_set.safety_issues):
        for safety_issue in fact_set.safety_issues:
            if safety_issue.severity.lower() in {"high", "critical"}:
                safety_stops.append(safety_issue)
            else:
                observations.append(safety_issue)
    else:
        for safety_issue in fact_set.safety_issues:
            observations.append(safety_issue)

    for task in fact_set.tasks:
        if is_actionable_fact(task):
            actionable_tasks.append(task)
        elif task.clarification_needed:
            clarifications.append(task)
        else:
            observations.append(task)

    for material in fact_set.materials:
        if is_actionable_fact(material):
            actionable_materials.append(material)
        elif material.clarification_needed:
            clarifications.append(material)
        else:
            observations.append(material)

    for issue_fact in fact_set.issues:
        if is_actionable_fact(issue_fact):
            actionable_issues.append(issue_fact)
        elif issue_fact.clarification_needed:
            clarifications.append(issue_fact)
        else:
            observations.append(issue_fact)

    for focus in fact_set.next_focus:
        if is_actionable_fact(focus):
            actionable_next_focus.append(focus)
        elif focus.clarification_needed:
            clarifications.append(focus)
        else:
            observations.append(focus)

    if safety_stops:
        # High or critical safety issues stop autonomous project mutations
        observations.extend(actionable_tasks)
        observations.extend(actionable_materials)
        observations.extend(actionable_issues)
        observations.extend(actionable_next_focus)
        actionable_tasks = []
        actionable_materials = []
        actionable_issues = []
        actionable_next_focus = []

    return RoutedFacts(
        actionable_tasks=actionable_tasks,
        actionable_materials=actionable_materials,
        actionable_issues=actionable_issues,
        actionable_next_focus=actionable_next_focus,
        safety_stops=safety_stops,
        clarifications=clarifications,
        observations=observations,
    )
