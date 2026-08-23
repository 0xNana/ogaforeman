import json
import logging
from io import StringIO

import pytest

from app.agents.identifiers import AdkAgentId, AdkNodeId, AdkToolId, AdkWorkflowId
from app.agents.telemetry import run_adk_stage
from app.observability.logging import configure_logging


@pytest.mark.asyncio
async def test_adk_stage_telemetry_identifies_workflow_agent_node_and_tool() -> None:
    stream = StringIO()
    configure_logging(stream=stream)

    async def execute() -> dict[str, bool]:
        return {"done": True}

    result = await run_adk_stage(
        logging.getLogger("test.adk.telemetry"),
        workflow=AdkWorkflowId.DELIVERY_DELAY,
        agent=AdkAgentId.DELIVERY_DELAY,
        node=AdkNodeId.CREATE_DELIVERY_RISK,
        tool=AdkToolId.CREATE_ISSUE,
        execute=execute,
    )

    payload = json.loads(stream.getvalue())
    assert result == {"done": True}
    assert payload["workflow"] == AdkWorkflowId.DELIVERY_DELAY
    assert payload["agent"] == AdkAgentId.DELIVERY_DELAY
    assert payload["node"] == AdkNodeId.CREATE_DELIVERY_RISK
    assert payload["tool"] == AdkToolId.CREATE_ISSUE
    assert payload["status"] == "completed"
