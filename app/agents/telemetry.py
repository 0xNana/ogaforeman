"""Allowlisted stage telemetry for ADK-owned workflows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from time import monotonic
from typing import TypeVar

from app.observability.logging import log_event


ResultT = TypeVar("ResultT")


async def run_adk_stage(
    logger: logging.Logger,
    *,
    workflow: str,
    agent: str,
    node: str,
    execute: Callable[[], Awaitable[ResultT]],
    tool: str | None = None,
) -> ResultT:
    started = monotonic()
    try:
        result = await execute()
    except Exception:
        log_event(
            logger,
            logging.ERROR,
            "adk_stage_failed",
            "ADK workflow stage failed",
            workflow=workflow,
            agent=agent,
            node=node,
            step=node,
            tool=tool,
            status="failed",
            duration_ms=round((monotonic() - started) * 1_000),
        )
        raise
    log_event(
        logger,
        logging.INFO,
        "adk_stage_completed",
        "ADK workflow stage completed",
        workflow=workflow,
        agent=agent,
        node=node,
        step=node,
        tool=tool,
        status="completed",
        duration_ms=round((monotonic() - started) * 1_000),
    )
    return result


__all__ = ["run_adk_stage"]
