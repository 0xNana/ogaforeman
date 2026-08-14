from datetime import UTC, datetime
from decimal import Decimal

from app.domain.conversation import (
    ContextDomain,
    ContextQuery,
    ConversationalProjectContext,
    IssueContextItem,
    MaterialContextItem,
    TaskContextItem,
)
from app.services.conversation_advice import ConversationAdviceService, plan_advice_query


NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def test_advice_query_loads_schedule_dependencies_materials_and_open_risks() -> None:
    query = plan_advice_query("wdyt about plastering tomorrow?")

    assert set(query.domains) == {
        ContextDomain.TASKS,
        ContextDomain.SCHEDULE,
        ContextDomain.ISSUES,
        ContextDomain.MATERIALS,
        ContextDomain.MATERIAL_REQUESTS,
        ContextDomain.APPROVALS,
    }
    assert query.search_terms == ("plastering",)


def test_grounded_advice_recommends_holding_without_mutating_state() -> None:
    context = ConversationalProjectContext(
        project_id="prj_advice123",
        retrieved_at=NOW,
        query=ContextQuery(
            domains=(
                ContextDomain.TASKS,
                ContextDomain.SCHEDULE,
                ContextDomain.ISSUES,
                ContextDomain.MATERIALS,
            )
        ),
        tasks=(
            TaskContextItem(
                id="tsk_plaster123",
                title="Plastering",
                status="planned",
                priority="high",
                dependency_ids=("tsk_electrical123",),
            ),
        ),
        issues=(
            IssueContextItem(
                id="iss_electrical123",
                type="blocker",
                severity="high",
                description="Electrical rough-in remains blocked",
                status="open",
                task_ids=("tsk_electrical123",),
            ),
        ),
        materials=(
            MaterialContextItem(
                id="mat_cement123",
                name="Cement",
                unit="bags",
                available_quantity=Decimal("10"),
                reserved_quantity=Decimal("0"),
                minimum_required_quantity=Decimal("40"),
                upcoming_requirement_quantity=Decimal("40"),
            ),
        ),
    )

    reply = ConversationAdviceService().advise("wdyt about plastering tomorrow?", context)

    assert reply.recommendation == "hold"
    assert "Cement" in reply.text
    assert "Electrical" in reply.text
    assert set(reply.cited_record_ids) == {"tsk_plaster123", "iss_electrical123", "mat_cement123"}
