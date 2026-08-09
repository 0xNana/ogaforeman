"""Liveness, readiness, and metrics HTTP contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from .metrics import MetricRegistry, metrics


HealthCallable = Callable[[], bool | tuple[bool, str]]


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    check: HealthCallable
    critical: bool = True


class HealthRegistry:
    def __init__(self, checks: tuple[HealthCheck, ...] = ()) -> None:
        self._checks = checks

    def add(self, check: HealthCheck) -> None:
        self._checks = (*self._checks, check)

    def liveness(self) -> dict[str, object]:
        return {"status": "ok", "timestamp": _now()}

    def readiness(self) -> tuple[dict[str, object], int]:
        results: dict[str, object] = {}
        ready = True
        for item in self._checks:
            try:
                value = item.check()
                ok, detail = value if isinstance(value, tuple) else (value, None)
            except Exception as exc:  # dependency diagnostics must not crash the endpoint
                ok, detail = False, type(exc).__name__
            result: dict[str, object] = {"status": "ok" if ok else "failed"}
            if detail:
                result["detail"] = str(detail)[:256]
            results[item.name] = result
            if item.critical and not ok:
                ready = False
        payload: dict[str, object] = {
            "status": "ready" if ready else "not_ready",
            "checks": results,
            "timestamp": _now(),
        }
        return payload, status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE


def create_health_router(
    *,
    registry: HealthRegistry | None = None,
    metric_registry: MetricRegistry | None = None,
) -> APIRouter:
    health_registry = registry or HealthRegistry()
    metric_store = metric_registry or metrics
    router = APIRouter(tags=["health"])

    @router.get("/health/live", include_in_schema=True)
    async def health_live() -> dict[str, object]:
        return health_registry.liveness()

    @router.get("/health/ready", include_in_schema=True)
    async def health_ready() -> Response:
        payload, code = health_registry.readiness()
        return JSONResponse(status_code=code, content=payload)

    @router.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> PlainTextResponse:
        return PlainTextResponse(
            metric_store.prometheus_text(), media_type="text/plain; version=0.0.4"
        )

    return router


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["HealthCheck", "HealthRegistry", "create_health_router"]
