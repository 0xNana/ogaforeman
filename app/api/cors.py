from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def install_cors_middleware(app: FastAPI, origins: Sequence[str]) -> None:
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Correlation-ID",
            "X-Request-ID",
            "X-Trace-ID",
        ],
        expose_headers=["X-Correlation-ID", "X-Request-ID"],
        max_age=600,
    )


__all__ = ["install_cors_middleware"]
