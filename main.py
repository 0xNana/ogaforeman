"""Oga Foreman API service and local command entrypoint."""

from __future__ import annotations

import argparse

from fastapi import FastAPI

from app.api.cors import install_cors_middleware
from app.api.dead_letters import router as dead_letter_router
from app.api.errors import install_error_handlers, install_request_id_middleware
from app.api.events import router as event_router
from app.api.health import create_runtime_health_router
from app.api.runtime_auth import ConfiguredAuthRuntime
from app.api.uploads import router as upload_router
from app.api.v1.router import api_router
from app.config import get_settings
from app.infrastructure.pubsub import PubSubClient
from app.infrastructure.storage import create_storage_adapter
from app.infrastructure.gemini import GeminiActionInterpreter, GeminiIntentClassifier
from app.services.attachments import AttachmentService
from app.observability.logging import configure_logging
from app.observability.tracing import cloud_trace_exporter
from app.services.site_update_intake import SiteUpdateIntakeService
from app.services.conversation_mutation_policy import MutationPolicyService
from app.services.conversation_schedule_operations import ConversationScheduleService


settings = get_settings()
configure_logging()

app = FastAPI(
    title="Oga Foreman API",
    description="Tell Oga what happened. Oga handles the follow-through.",
    version="0.1.0",
)
app.state.settings = settings
if settings.auth_audience:
    app.state.auth_runtime = ConfiguredAuthRuntime(settings)
    app.state.current_user_provider = app.state.auth_runtime.authenticate
    app.state.project_access_provider = app.state.auth_runtime.project_access
    app.state.site_update_intake = SiteUpdateIntakeService(
        app.state.auth_runtime.store,
        PubSubClient(settings),
    )
    if not settings.use_fake_model:
        app.state.intent_classifier = GeminiIntentClassifier(settings)
        app.state.action_interpreter = GeminiActionInterpreter(settings)
        if settings.conversation_proposal_signing_key is not None:
            app.state.conversation_schedule_service = ConversationScheduleService(
                app.state.auth_runtime.store,
                MutationPolicyService(),
                proposal_signing_key=settings.conversation_proposal_signing_key.get_secret_value().encode(),
            )
    if settings.media_bucket:
        app.state.attachment_service = AttachmentService(
            app.state.auth_runtime.store,
            create_storage_adapter(settings),
            settings,
        )
trace_exporter = (
    cloud_trace_exporter(settings.google_cloud_project)
    if settings.google_cloud_project
    and settings.oga_env.value in {"preview", "staging", "production"}
    else None
)
install_request_id_middleware(app, trace_exporter=trace_exporter)
install_cors_middleware(app, settings.cors_allowed_origins)
install_error_handlers(app)
app.include_router(create_runtime_health_router(settings))
app.include_router(api_router, prefix="/api/v1")
app.include_router(upload_router)
app.include_router(dead_letter_router, prefix="/api/v1")
app.include_router(event_router, prefix="/api/v1/internal")


@app.get("/", tags=["service"])
async def service_root() -> dict[str, str]:
    return {
        "service": "Oga Foreman API",
        "status": "ok",
        "health": "/health/live",
        "readiness": "/health/ready",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Oga Foreman command runner")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the deterministic local demo rehearsal in dry-run mode.",
    )
    args = parser.parse_args()
    if args.demo:
        from scripts.run_demo import run_local_demo

        result = run_local_demo()
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
