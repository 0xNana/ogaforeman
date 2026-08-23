from typing import Any

from app.agents.adk_runtime import build_site_update_workflow
from app.agents.conversation_execution import (
    AgenticConversationHandlers,
    build_agentic_conversation_workflow,
)
from app.agents.event_execution import (
    build_delivery_delay_workflow,
    build_project_event_workflow,
)
from app.agents.identifiers import AdkAgentId, AdkNodeId, AdkWorkflowId


async def _stage() -> dict[str, Any]:
    return {}


async def _classify() -> str:
    return "casual_response"


def test_declared_production_agents_are_exactly_the_runner_workflow_roots() -> None:
    delivery_handlers = {
        node: _stage
        for node in (
            AdkNodeId.RECEIVE_DELIVERY_DELAY,
            AdkNodeId.RETRIEVE_REQUEST_CONTEXT,
            AdkNodeId.ASSESS_DELIVERY_IMPACT,
            AdkNodeId.MARK_REQUEST_DELAYED,
            AdkNodeId.CREATE_DELIVERY_RISK,
            AdkNodeId.CREATE_DELIVERY_FOLLOW_UP,
            AdkNodeId.DELIVER_DELIVERY_NOTIFICATION,
            AdkNodeId.COMPLETE_DELIVERY_DELAY,
        )
    }
    conversation_handlers = AgenticConversationHandlers(
        classify_intent=_classify,
        retrieve_authorized_context=_stage,
        resolve_entities=_stage,
        reason_over_context=_stage,
        invoke_typed_tools=_stage,
    )
    roots = {
        build_site_update_workflow(_stage, timeout_seconds=5).name,
        build_delivery_delay_workflow(delivery_handlers, 5).name,
        build_agentic_conversation_workflow(conversation_handlers, 5).name,
        build_project_event_workflow(_stage, 5).name,
    }

    assert roots == {workflow.value for workflow in AdkWorkflowId}
    assert roots == {agent.value for agent in AdkAgentId}
