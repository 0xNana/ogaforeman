from __future__ import annotations

from hashlib import sha256
import re
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.agents.conversation import IntentRoutingService
from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.activity import MutationContext
from app.domain.conversation import (
    ContextQuery,
    ConversationContext,
    EntityKind,
    EntityResolutionStatus,
    IntentDestination,
    SiteUpdateRouteCommand,
)
from app.domain.enums import ActorType
from app.services.activity import ActivityService
from app.services.conversation_audit import ConversationAuditService
from app.services.conversation_advice import ConversationAdviceService, plan_advice_query
from app.services.conversation_context import ProjectContextService, plan_context_query
from app.services.conversation_responses import ConversationResponseService
from app.services.conversation_site_update_routing import ConversationSiteUpdateRouter
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService

from .projects import auth_runtime


router = APIRouter()


class ConversationMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=20_000)


class ConversationMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    text: str
    cited_record_ids: tuple[str, ...] = ()
    recommendation: str | None = None
    mutation_performed: bool = False
    workflow_run_id: str | None = None
    proposed_action: str | None = None


@router.post("/messages", response_model=ConversationMessageResponse)
async def send_message(
    project_id: str,
    payload: ConversationMessageRequest,
    request: Request,
) -> ConversationMessageResponse:
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    runtime = auth_runtime(request)
    memory_service = ConversationMemoryService(
        runtime.store, ConversationEntityResolver(runtime.store)
    )
    memory = memory_service.load(access)
    classifier = getattr(request.app.state, "intent_classifier", None)
    if classifier is None or not hasattr(classifier, "classify"):
        raise ApiError(
            "DEPENDENCY_UNAVAILABLE", "OG conversation is temporarily unavailable.", status_code=503
        )
    route = await IntentRoutingService(classifier).route(
        payload.message,
        context=ConversationContext(
            has_active_project=True,
            has_pending_clarification=memory.pending_clarification is not None,
            # Legacy raw confirmation text is never executable server state.
            has_pending_confirmation=False,
        ),
    )
    if (
        route.destination is IntentDestination.CASUAL_RESPONSE
        or route.destination is IntentDestination.CLARIFICATION
    ):
        reply = ConversationResponseService().respond(route)
        return ConversationMessageResponse(kind=reply.kind.value, text=reply.text)

    context_service = ProjectContextService(
        runtime.store,
        runtime.projects,
        member_names=getattr(runtime, "project_member_names", None),
    )
    if route.destination is IntentDestination.PROJECT_CONTEXT:
        snapshot = context_service.retrieve(
            access, _query_with_recent_reference(payload.message, memory_service, access)
        )
        reply = ConversationResponseService().project(snapshot)
        _remember_citations(memory_service, access, reply.cited_record_ids)
        return ConversationMessageResponse(
            kind=reply.kind.value, text=reply.text, cited_record_ids=reply.cited_record_ids
        )
    if route.destination is IntentDestination.PROJECT_ADVICE:
        snapshot = context_service.retrieve(access, plan_advice_query(payload.message))
        advice_reply = ConversationAdviceService().advise(payload.message, snapshot)
        _remember_citations(memory_service, access, advice_reply.cited_record_ids)
        return ConversationMessageResponse(
            kind="advice",
            text=advice_reply.text,
            cited_record_ids=advice_reply.cited_record_ids,
            recommendation=advice_reply.recommendation,
        )
    if route.destination is IntentDestination.GOLDEN_SITE_UPDATE:
        intake = getattr(request.app.state, "site_update_intake", None)
        if intake is None:
            raise ApiError(
                "DEPENDENCY_UNAVAILABLE",
                "Site updates are temporarily unavailable.",
                status_code=503,
            )
        result = ConversationSiteUpdateRouter(intake).submit(
            access,
            SiteUpdateRouteCommand(
                project_id=project_id,
                text=payload.message,
                idempotency_key=require_idempotency_key(request),
            ),
        )
        return ConversationMessageResponse(
            kind="workflow",
            text="Got it. I saved the update and started the site workflow.",
            workflow_run_id=result.agent_run_id,
        )
    if route.destination is IntentDestination.PROJECT_ACTION:
        access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
        key = require_idempotency_key(request)
        audit = ConversationAuditService(ActivityService(runtime.store))
        base = MutationContext(
            project_id=project_id,
            actor_type=ActorType.USER,
            actor_id=access.actor.user_id,
            idempotency_key=_audit_key(key, "requested"),
        )
        audit.record(
            base,
            action="conversation.mutation_requested",
            entity_type="project",
            entity_id=project_id,
            summary="Project change requested through OG.",
            reason_code=route.decision.reason_code,
        )
        audit.record(
            base.model_copy(update={"idempotency_key": _audit_key(key, "confirmation")}),
            action="conversation.confirmation_requested",
            entity_type="project",
            entity_id=project_id,
            summary="OG requested confirmation before applying a project change.",
            reason_code="confirmation_required",
        )
        proposed = route.decision.requested_action or payload.message
        # Raw model text is display-only. It is not an executable confirmation token.
        memory_service.remember_pending(access, proposed_action=proposed)
        return ConversationMessageResponse(
            kind="proposed_change",
            text="I understood the requested project change. Review and confirm the exact record change before I apply it.",
            proposed_action=proposed,
        )
    return ConversationMessageResponse(
        kind="clarification", text="Please clarify the project change you want OG to make."
    )


def _audit_key(request_key: str, transition: str) -> str:
    digest = sha256(request_key.encode()).hexdigest()[:32]
    return f"conversation:{digest}:{transition}"


def _query_with_recent_reference(
    message: str,
    memory_service: ConversationMemoryService,
    access: ProjectAccessContext,
) -> ContextQuery:
    query = plan_context_query(message)
    words = set(re.findall(r"[a-z0-9]+", message.casefold()))
    if not words.intersection({"it", "that", "this", "them"}):
        return query
    resolution = memory_service.resolve_recent(access, EntityKind.TASK)
    if resolution.status is EntityResolutionStatus.RESOLVED and resolution.display_name is not None:
        return query.model_copy(
            update={"search_terms": tuple(resolution.display_name.casefold().split())}
        )
    return query


def _remember_citations(
    memory_service: ConversationMemoryService,
    access: ProjectAccessContext,
    record_ids: tuple[str, ...],
) -> None:
    prefixes = {
        "tsk_": EntityKind.TASK,
        "iss_": EntityKind.ISSUE,
        "mat_": EntityKind.MATERIAL,
        "mreq_": EntityKind.MATERIAL_REQUEST,
        "rpt_": EntityKind.DAILY_LOG,
    }
    remembered = 0
    for record_id in record_ids:
        kind = next(
            (value for prefix, value in prefixes.items() if record_id.startswith(prefix)), None
        )
        if kind is None:
            continue
        memory_service.remember_reference(access, kind, record_id)
        remembered += 1
        if remembered == 4:
            return


__all__ = ["ConversationMessageRequest", "ConversationMessageResponse", "router"]
