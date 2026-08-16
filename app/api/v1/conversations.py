from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.conversation import IntentRoutingService
from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.enums import SiteUpdateInputType
from app.domain.conversation import (
    ContextQuery,
    ConversationContext,
    EntityKind,
    EntityResolutionStatus,
    IntentDecision,
    IntentDestination,
    IntentRoute,
    IntentType,
    MaterialOperation,
    PendingConversationCommand,
    ProjectSetupStatus,
    SiteUpdateRouteCommand,
)
from app.domain.clarification import (
    ClarificationKind,
    ClarificationResolutionType,
    ClarificationStatus,
    PendingClarification,
)
from app.services.conversation_action_composer import (
    ActionInterpretation,
    MaterialActionInterpretation,
    PurchaseActionInterpretation,
    ambiguous_material_quantity_phrase,
)
from app.services.conversation_action_execution import ConversationActionExecutionService
from app.services.conversation_advice import ConversationAdviceService, plan_advice_query
from app.services.conversation_context import ProjectContextService, plan_context_query
from app.services.conversation_confirmation import ConversationConfirmationService
from app.services.conversation_responses import ConversationResponseService
from app.services.conversation_site_update_routing import ConversationSiteUpdateRouter
from app.services.conversation_entity_resolution import ConversationEntityResolver
from app.services.conversation_memory import ConversationMemoryService
from app.services.site_update_intake import SiteUpdateAttachmentError, SiteUpdatePublishError
from app.services.product_knowledge import is_product_help_question
from app.services.project_setup import ProjectSetupService, is_project_setup_question
from app.repositories.interfaces import VersionConflictError

from .projects import auth_runtime


router = APIRouter()
user_router = APIRouter()


def _proposal_signing_key(request: Request) -> bytes:
    key = getattr(request.app.state, "conversation_proposal_signing_key", None)
    if not isinstance(key, bytes):
        raise ApiError(
            "DEPENDENCY_UNAVAILABLE",
            "Conversation proposals are temporarily unavailable.",
            status_code=503,
        )
    return key


class ConversationMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="", max_length=20_000)
    attachment_ids: tuple[str, ...] = Field(default=(), max_length=32)
    input_type: SiteUpdateInputType | None = None

    @model_validator(mode="after")
    def require_input(self) -> "ConversationMessageRequest":
        if not self.message.strip() and not self.attachment_ids:
            raise ValueError("conversation input requires text or attachments")
        if len(self.attachment_ids) != len(set(self.attachment_ids)):
            raise ValueError("attachment_ids cannot contain duplicates")
        return self


class ConversationMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    text: str
    cited_record_ids: tuple[str, ...] = ()
    recommendation: str | None = None
    mutation_performed: bool = False
    workflow_run_id: str | None = None
    proposed_action: str | None = None
    proposal_id: str | None = None
    memory_version: int | None = None
    activity_id: str | None = None
    approval_id: str | None = None
    material_request_id: str | None = None
    site_update_id: str | None = None
    event_id: str | None = None
    proposal: PendingConversationCommand | None = None
    assistant_name: str = "OG"
    intent: str | None = None


class ConversationProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: PendingConversationCommand
    memory_version: int = Field(ge=0)


class PendingConversationProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: PendingConversationCommand | None = None
    memory_version: int = Field(ge=0)


class ConversationConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_memory_version: int = Field(ge=0)


def _product_help_response(message: str) -> ConversationMessageResponse:
    reply = ConversationResponseService().help(message)
    return ConversationMessageResponse(kind=reply.kind.value, text=reply.text, intent="help")


@user_router.post("/messages", response_model=ConversationMessageResponse)
def send_user_scoped_message(
    payload: ConversationMessageRequest,
    request: Request,
) -> ConversationMessageResponse:
    runtime = auth_runtime(request)
    actor = runtime.authenticate(request)
    if is_product_help_question(payload.message):
        return _product_help_response(payload.message)
    if not is_project_setup_question(payload.message):
        return ConversationMessageResponse(
            kind="clarification",
            text="Open a project for project questions or changes, or ask me how OG works.",
        )
    projects = tuple(runtime.projects.list_for_user(actor))
    if not projects:
        reply = ConversationResponseService().project_setup(
            ProjectSetupStatus(project_exists=False)
        )
        return ConversationMessageResponse(
            kind=reply.kind.value, text=reply.text, intent="project_query"
        )
    if len(projects) != 1:
        return ConversationMessageResponse(
            kind="clarification",
            text="Open the project you want me to check, then ask whether it's set up.",
        )
    access = configured_project_access(request, projects[0].id, ProjectPermission.READ)
    reply = ConversationResponseService().project_setup(
        ProjectSetupService(runtime.store, runtime.projects).retrieve(access)
    )
    return ConversationMessageResponse(
        kind=reply.kind.value,
        text=reply.text,
        cited_record_ids=reply.cited_record_ids,
        intent="project_query",
    )


@router.get(
    "/proposals/pending",
    response_model=PendingConversationProposalResponse,
)
def get_pending_proposal(
    project_id: str,
    request: Request,
) -> PendingConversationProposalResponse:
    access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
    runtime = auth_runtime(request)
    memory_service = ConversationMemoryService(
        runtime.store,
        ConversationEntityResolver(runtime.store),
        proposal_signing_key=_proposal_signing_key(request),
    )
    memory = memory_service.load(access)
    if memory.pending_command is None:
        return PendingConversationProposalResponse(memory_version=memory.version)
    try:
        proposal = memory_service.require_command(
            access, memory.pending_command.proposal_id, memory.version
        )
    except (ValueError, PermissionError) as exc:
        raise ApiError(
            "PROPOSAL_CONFLICT",
            "The saved proposal is stale or expired. Send the request again to refresh it.",
            status_code=409,
        ) from exc
    return PendingConversationProposalResponse(proposal=proposal, memory_version=memory.version)


@router.get(
    "/proposals/{proposal_id}",
    response_model=ConversationProposalResponse,
)
def get_proposal(
    project_id: str,
    proposal_id: str,
    memory_version: int,
    request: Request,
) -> ConversationProposalResponse:
    access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
    runtime = auth_runtime(request)
    memory = ConversationMemoryService(
        runtime.store,
        ConversationEntityResolver(runtime.store),
        proposal_signing_key=_proposal_signing_key(request),
    )
    try:
        proposal = memory.require_command(access, proposal_id, memory_version)
    except (ValueError, PermissionError) as exc:
        raise ApiError(
            "PROPOSAL_CONFLICT",
            "The proposal is stale, expired, or no longer available. Reload the conversation.",
            status_code=409,
        ) from exc
    return ConversationProposalResponse(proposal=proposal, memory_version=memory_version)


@router.delete(
    "/proposals/{proposal_id}",
    response_model=ConversationMessageResponse,
)
def cancel_proposal(
    project_id: str,
    proposal_id: str,
    memory_version: int,
    request: Request,
) -> ConversationMessageResponse:
    access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
    runtime = auth_runtime(request)
    memory_service = ConversationMemoryService(
        runtime.store,
        ConversationEntityResolver(runtime.store),
        proposal_signing_key=_proposal_signing_key(request),
    )
    consumed = memory_service.claim(access, proposal_id)
    if consumed is not None and consumed.outcome != "cancelled":
        raise ApiError(
            "PROPOSAL_CONFLICT",
            "The proposal was already consumed and cannot be cancelled.",
            status_code=409,
        )
    try:
        memory = memory_service.clear_command(access, proposal_id, memory_version)
    except (ValueError, PermissionError) as exc:
        raise ApiError(
            "PROPOSAL_CONFLICT",
            "The proposal changed or is no longer available. Reload the conversation.",
            status_code=409,
        ) from exc
    return ConversationMessageResponse(
        kind="proposal_cancelled",
        text="The proposal was cancelled. No project change was applied.",
        memory_version=memory.version,
    )


@router.post(
    "/proposals/{proposal_id}/confirm",
    response_model=ConversationMessageResponse,
)
def confirm_proposal(
    project_id: str,
    proposal_id: str,
    payload: ConversationConfirmationRequest,
    request: Request,
) -> ConversationMessageResponse:
    access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
    runtime = auth_runtime(request)
    try:
        result = ConversationConfirmationService(
            runtime.store,
            schedules=getattr(request.app.state, "conversation_schedule_service", None),
            proposal_signing_key=_proposal_signing_key(request),
        ).confirm(access, proposal_id, payload.observed_memory_version)
    except (ValueError, VersionConflictError, PermissionError) as exc:
        raise ApiError(
            "STALE_PROPOSAL",
            "The project changed since I proposed that. I've refreshed the plan.",
            status_code=409,
        ) from exc
    except RuntimeError as exc:
        raise ApiError(
            "DEPENDENCY_UNAVAILABLE",
            "Proposal confirmation is temporarily unavailable.",
            status_code=503,
        ) from exc
    return ConversationMessageResponse(
        kind="done",
        text=(
            "That proposal was already confirmed; no new mutation was applied."
            if result.duplicate
            else result.reply
        ),
        mutation_performed=not result.duplicate,
        proposal_id=proposal_id,
        activity_id=result.activity_id,
    )


@router.post("/messages", response_model=ConversationMessageResponse)
async def send_message(
    project_id: str,
    payload: ConversationMessageRequest,
    request: Request,
) -> ConversationMessageResponse:
    if not payload.attachment_ids and is_product_help_question(payload.message):
        runtime = auth_runtime(request)
        runtime.authenticate(request)
        return _product_help_response(payload.message)
    access = configured_project_access(request, project_id, ProjectPermission.READ)
    runtime = auth_runtime(request)
    if payload.attachment_ids:
        access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
        intake = getattr(request.app.state, "site_update_intake", None)
        if intake is None:
            raise ApiError(
                "DEPENDENCY_UNAVAILABLE",
                "Site updates are temporarily unavailable.",
                status_code=503,
            )
        try:
            result = ConversationSiteUpdateRouter(intake).submit(
                access,
                SiteUpdateRouteCommand(
                    project_id=project_id,
                    text=payload.message.strip() or None,
                    attachment_ids=payload.attachment_ids,
                    input_type=payload.input_type,
                    idempotency_key=require_idempotency_key(request),
                ),
            )
        except SiteUpdatePublishError as exc:
            raise ApiError(
                "SITE_UPDATE_SAVED_NOT_QUEUED",
                "Your update was saved, but OG could not queue it yet. Retry safely.",
                status_code=503,
            ) from exc
        except SiteUpdateAttachmentError as exc:
            raise ApiError(exc.code, str(exc), status_code=422) from exc
        return ConversationMessageResponse(
            kind="workflow",
            text="Got it. I saved the update and started the site workflow.",
            workflow_run_id=result.agent_run_id,
            site_update_id=result.site_update_id,
            event_id=result.event_id,
        )
    memory_service = ConversationMemoryService(
        runtime.store, ConversationEntityResolver(runtime.store)
    )
    memory = memory_service.load(access)

    clarification_interpretation: ActionInterpretation | None = None
    if (
        memory.active_clarification is not None
        and memory.active_clarification.status == ClarificationStatus.PENDING
    ):
        if (
            memory.active_clarification.expires_at
            and memory.active_clarification.expires_at <= datetime.now(UTC)
        ):
            memory_service.clear_active_clarification(access)
            return ConversationMessageResponse(
                kind="clarification",
                text="That question expired. Please restate what you want me to do.",
                intent=IntentType.CLARIFICATION_RESPONSE.value,
            )

        resolver = getattr(request.app.state, "clarification_resolver", None)
        if resolver is None or not hasattr(resolver, "resolve"):
            raise ApiError(
                "DEPENDENCY_UNAVAILABLE",
                "OG conversation is temporarily unavailable.",
                status_code=503,
            )

        clarification_record = memory.active_clarification
        decision = await resolver.resolve(payload.message, clarification=clarification_record)
        if decision.resolution == ClarificationResolutionType.AMBIGUOUS:
            return ConversationMessageResponse(
                kind="clarification",
                text=memory.pending_clarification or "Could you clarify what you mean?",
                intent=IntentType.CLARIFICATION_RESPONSE.value,
            )

        quantity = clarification_record.quantity
        unit = clarification_record.unit
        if quantity is None or unit is None:
            raise ApiError(
                "INVALID_CLARIFICATION",
                "The clarification is missing a quantity or unit. Please restate the request.",
                status_code=400,
            )

        if decision.resolution == ClarificationResolutionType.INVENTORY_INCREMENT:
            clarification_interpretation = MaterialActionInterpretation(
                operation=MaterialOperation.ADJUST_ON_SITE,
                material_reference=clarification_record.entity_reference,
                quantity_delta=quantity,
                unit=unit,
            )
        else:
            clarification_interpretation = PurchaseActionInterpretation(
                material_reference=clarification_record.entity_reference,
                quantity=quantity,
                unit=unit,
                reason="Requested via conversation clarification",
            )

        memory_service.clear_active_clarification(access)

        route = IntentRoute(
            decision=IntentDecision(
                intent=IntentType.PROJECT_MUTATION,
                confidence=1.0,
                reason_code="clarification_resolution",
            ),
            destination=IntentDestination.PROJECT_ACTION,
        )
    else:
        classifier = getattr(request.app.state, "intent_classifier", None)
        if classifier is None or not hasattr(classifier, "classify"):
            raise ApiError(
                "DEPENDENCY_UNAVAILABLE",
                "OG conversation is temporarily unavailable.",
                status_code=503,
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
        or route.destination is IntentDestination.PRODUCT_HELP
        or route.destination is IntentDestination.CLARIFICATION
    ):
        reply = (
            ConversationResponseService().help(payload.message)
            if route.destination is IntentDestination.PRODUCT_HELP
            else ConversationResponseService().respond(route)
        )
        return ConversationMessageResponse(
            kind=reply.kind.value, text=reply.text, intent=route.decision.intent.value
        )

    context_service = ProjectContextService(
        runtime.store,
        runtime.projects,
        member_names=getattr(runtime, "project_member_names", None),
    )
    if route.destination is IntentDestination.PROJECT_CONTEXT:
        if is_project_setup_question(payload.message):
            reply = ConversationResponseService().project_setup(
                ProjectSetupService(runtime.store, runtime.projects).retrieve(access)
            )
            return ConversationMessageResponse(
                kind=reply.kind.value,
                text=reply.text,
                cited_record_ids=reply.cited_record_ids,
                intent=route.decision.intent.value,
            )
        snapshot = context_service.retrieve(
            access, _query_with_recent_reference(payload.message, memory_service, access)
        )
        reply = ConversationResponseService().project(snapshot)
        _remember_citations(memory_service, access, reply.cited_record_ids)
        return ConversationMessageResponse(
            kind=reply.kind.value,
            text=reply.text,
            cited_record_ids=reply.cited_record_ids,
            intent=route.decision.intent.value,
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
            site_update_id=result.site_update_id,
            event_id=result.event_id,
        )
    if route.destination is IntentDestination.PROJECT_ACTION:
        if clarification_interpretation is None:
            quantity_unit_material = ambiguous_material_quantity_phrase(payload.message)
            if quantity_unit_material is not None:
                parsed_quantity, parsed_unit, material = quantity_unit_material
                clarification_text = (
                    f"Do you mean {parsed_quantity} {parsed_unit} arrived on site, or you want me to prepare a "
                    f"request for {parsed_quantity} {parsed_unit}?"
                )
                pending_clarif = PendingClarification(
                    kind=ClarificationKind.MATERIAL_OPERATION,
                    entity_reference=material,
                    quantity=Decimal(parsed_quantity),
                    unit=parsed_unit,
                    allowed_resolutions=(
                        ClarificationResolutionType.INVENTORY_INCREMENT,
                        ClarificationResolutionType.MATERIAL_REQUEST,
                    ),
                    created_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(minutes=15),
                )
                memory_service.remember_pending(
                    access,
                    active_clarification=pending_clarif,
                    clarification=clarification_text,
                )
                return ConversationMessageResponse(
                    kind="clarification",
                    text=clarification_text,
                    intent=route.decision.intent.value,
                )
        access = configured_project_access(request, project_id, ProjectPermission.OPERATE)
        key = require_idempotency_key(request)
        interpreter = getattr(request.app.state, "action_interpreter", None)
        if interpreter is None or not hasattr(interpreter, "interpret"):
            raise ApiError(
                "DEPENDENCY_UNAVAILABLE",
                "OG project actions are temporarily unavailable.",
                status_code=503,
            )
        outcome = await ConversationActionExecutionService(
            runtime.store,
            runtime.projects,
            interpreter,
            member_names=getattr(runtime, "project_member_names", None),
            schedules=getattr(request.app.state, "conversation_schedule_service", None),
            proposal_signing_key=_proposal_signing_key(request),
        ).execute(
            access,
            payload.message,
            idempotency_key=key,
            clarification_interpretation=clarification_interpretation,
        )
        return ConversationMessageResponse(
            kind=outcome.kind,
            text=outcome.text,
            mutation_performed=outcome.mutation_performed,
            proposed_action=outcome.proposed_action,
            proposal_id=outcome.proposal_id,
            memory_version=outcome.memory_version,
            activity_id=outcome.activity_id,
            approval_id=outcome.approval_id,
            material_request_id=outcome.material_request_id,
            workflow_run_id=outcome.agent_run_id,
            proposal=outcome.proposal,
        )
    return ConversationMessageResponse(
        kind="clarification", text="Please clarify the project change you want OG to make."
    )


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


__all__ = ["ConversationMessageRequest", "ConversationMessageResponse", "router", "user_router"]
