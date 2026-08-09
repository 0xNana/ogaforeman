from app.domain.facts import ConfidenceLevel, ExtractedFactSet, TaskCompletionFact
from app.services.fact_router import route_facts


def test_fact_router_routes_positive_facts() -> None:
    fact_set = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                evidence="Finished plastering",
                confidence=ConfidenceLevel.HIGH,
                task_name="plastering",
                is_completed=True,
            )
        ]
    )
    routed = route_facts(fact_set)
    assert len(routed.actionable_tasks) == 1
    assert len(routed.clarifications) == 0
    assert len(routed.observations) == 0
    assert len(routed.safety_stops) == 0


def test_fact_router_blocks_negated_and_ambiguous_facts() -> None:
    fact_set = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                evidence="Electrician did not come",
                confidence=ConfidenceLevel.HIGH,
                is_negated=True,
                task_name="electrical",
                is_completed=False,
            ),
            TaskCompletionFact(
                evidence="Finished some work",
                confidence=ConfidenceLevel.MEDIUM,
                clarification_needed="Which work?",
                task_name="some work",
                is_completed=True,
            ),
        ]
    )
    routed = route_facts(fact_set)
    assert len(routed.actionable_tasks) == 0
    assert len(routed.clarifications) == 1
    assert len(routed.observations) == 1
