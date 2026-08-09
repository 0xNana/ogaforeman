from app.domain.facts import ConfidenceLevel, ExtractedFactSet, SafetyIssueFact, TaskCompletionFact
from app.services.fact_router import route_facts


def test_safety_stop_halts_mutations() -> None:
    fact_set = ExtractedFactSet(
        tasks=[
            TaskCompletionFact(
                evidence="Finished plastering",
                confidence=ConfidenceLevel.HIGH,
                task_name="plastering",
                is_completed=True,
            )
        ],
        safety_issues=[
            SafetyIssueFact(
                evidence="Wall is crumbling",
                confidence=ConfidenceLevel.HIGH,
                description="Wall is crumbling",
                severity="CRITICAL",
            )
        ],
    )
    routed = route_facts(fact_set)
    assert len(routed.actionable_tasks) == 0
    assert len(routed.safety_stops) == 1
    assert len(routed.observations) == 1  # task moved to observation
