from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.conversation import IntentRoutingService
from app.agents.conversation_execution import (
    AdkConversationExecutor,
    AgenticConversationHandlers,
)
from app.api.dependencies import configured_project_access, require_idempotency_key
from app.api.errors import ApiError
from app.domain.authorization import ProjectAccessContext, ProjectPermission
from app.domain.enums import SiteUpdateInputType
from app.domain.conversation import (
    ContextQuery,
    ConversationContext,
    ConversationalProjectContext,
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
    TaskActionBatchInterpretation,
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
from app.config.settings import get_settings

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
    route: IntentRoute | None = None
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

        if memory.active_clarification.kind is ClarificationKind.TASK_BATCH:
            action_json = memory.active_clarification.action_json
            if not action_json:
                memory_service.clear_active_clarification(access)
                return ConversationMessageResponse(
                    kind="clarification",
                    text="That task update expired. Please restate both task changes.",
                    intent=IntentType.CLARIFICATION_RESPONSE.value,
                )
            try:
                pending_batch = TaskActionBatchInterpretation.model_validate_json(action_json)
            except ValueError as exc:
                memory_service.clear_active_clarification(access)
                raise ApiError(
                    "INVALID_CLARIFICATION",
                    "That task clarification is no longer valid. Please restate both task changes.",
                    status_code=400,
                ) from exc
            if memory.active_clarification.entity_reference != "task batch":
                resolution = ConversationEntityResolver(runtime.store).resolve(
                    access, EntityKind.TASK, payload.message
                )
                if (
                    resolution.status is not EntityResolutionStatus.RESOLVED
                    or resolution.entity_id is None
                ):
                    return ConversationMessageResponse(
                        kind="clarification",
                        text=memory.pending_clarification or "Which specific task do you mean?",
                        intent=IntentType.CLARIFICATION_RESPONSE.value,
                    )
                reference = memory.active_clarification.entity_reference.casefold()
                actions = tuple(
                    action.model_copy(
                        update={
                            "task_reference": resolution.display_name or payload.message,
                            "ambiguous": False,
                        }
                    )
                    if (action.task_reference or "").casefold() == reference
                    else action
                    for action in pending_batch.actions
                )
                pending_batch = TaskActionBatchInterpretation(actions=actions)
            clarification_interpretation = pending_batch
            memory_service.clear_active_clarification(access)
            route = IntentRoute(
                decision=IntentDecision(
                    intent=IntentType.PROJECT_MUTATION,
                    confidence=1.0,
                    reason_code="task_batch_clarification_resolution",
                ),
                destination=IntentDestination.PROJECT_ACTION,
            )
        else:
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

    context_service = ProjectContextService(
        runtime.store,
        runtime.projects,
        member_names=getattr(runtime, "project_member_names", None),
    )
    snapshot: ConversationalProjectContext | None = None

    async def classify_intent() -> str:
        nonlocal route
        if route is None:
            route = await IntentRoutingService(classifier).route(
                payload.message,
                context=ConversationContext(
                    has_active_project=True,
                    has_pending_clarification=memory.pending_clarification is not None,
                    has_pending_confirmation=False,
                ),
            )
        return route.destination.value

    async def retrieve_authorized_context() -> dict[str, object]:
        nonlocal snapshot
        if route is None:
            raise RuntimeError("conversation classification did not complete")
        if route.destination is IntentDestination.PROJECT_ADVICE:
            query = plan_advice_query(payload.message)
        elif route.destination is IntentDestination.PROJECT_ACTION:
            query = plan_context_query(payload.message)
        else:
            query = _query_with_recent_reference(payload.message, memory_service, access)
        snapshot = context_service.retrieve(access, query)
        return {
            "project_id": snapshot.project_id,
            "task_count": len(snapshot.tasks),
            "issue_count": len(snapshot.issues),
            "material_count": len(snapshot.materials),
        }

    async def resolve_entities() -> dict[str, object]:
        if snapshot is None:
            raise RuntimeError("conversation context retrieval did not complete")
        canonical_resolutions: list[dict[str, object]] = []
        reference = " ".join(snapshot.query.search_terms).strip()
        if reference:
            resolver = ConversationEntityResolver(runtime.store)
            for kind in (EntityKind.TASK, EntityKind.MATERIAL, EntityKind.ISSUE):
                resolution = resolver.resolve(access, kind, reference)
                if resolution.status is EntityResolutionStatus.RESOLVED:
                    canonical_resolutions.append(
                        {
                            "kind": kind.value,
                            "entity_id": resolution.entity_id,
                            "match_method": resolution.match_method,
                        }
                    )
        resolved_ids = tuple(
            dict.fromkeys(
                item.id
                for collection in (
                    snapshot.tasks,
                    snapshot.issues,
                    snapshot.materials,
                    snapshot.material_requests,
                )
                for item in collection
            )
        )
        return {
            "canonical_resolutions": canonical_resolutions,
            "candidate_record_ids": list(resolved_ids[:20]),
        }

    async def reason_over_context() -> dict[str, object]:
        if route is None:
            raise RuntimeError("conversation classification did not complete")
        if route.destination is IntentDestination.CLARIFICATION:
            reply = ConversationResponseService().respond(route)
            response = ConversationMessageResponse(
                kind=reply.kind.value,
                text=reply.text,
                intent=route.decision.intent.value,
            )
        elif route.destination in {
            IntentDestination.CASUAL_RESPONSE,
            IntentDestination.PRODUCT_HELP,
        }:
            reply = (
                ConversationResponseService().help(payload.message)
                if route.destination is IntentDestination.PRODUCT_HELP
                else ConversationResponseService().respond(route)
            )
            response = ConversationMessageResponse(
                kind=reply.kind.value,
                text=reply.text,
                intent=route.decision.intent.value,
            )
        else:
            if snapshot is None:
                raise RuntimeError("conversation context retrieval did not complete")
            conversation_agent = getattr(request.app.state, "conversation_agent", None)
            settings = getattr(request.app.state, "settings", None) or get_settings()
            if conversation_agent is None or not hasattr(conversation_agent, "respond"):
                if not settings.use_fake_model:
                    raise ApiError(
                        "DEPENDENCY_UNAVAILABLE",
                        "OG project conversation is temporarily unavailable.",
                        status_code=503,
                    )
                if is_project_setup_question(payload.message):
                    fallback = ConversationResponseService().project_setup(
                        ProjectSetupService(runtime.store, runtime.projects).retrieve(access)
                    )
                elif route.destination is IntentDestination.PROJECT_ADVICE:
                    fallback = ConversationAdviceService().advise(payload.message, snapshot)
                else:
                    fallback = ConversationResponseService().project(snapshot)
                response = ConversationMessageResponse(
                    kind=(
                        "advice"
                        if route.destination is IntentDestination.PROJECT_ADVICE
                        else "project"
                    ),
                    text=fallback.text,
                    cited_record_ids=fallback.cited_record_ids,
                    recommendation=getattr(fallback, "recommendation", None),
                    intent=route.decision.intent.value,
                )
            else:
                answer = await conversation_agent.respond(
                    payload.message,
                    intent=route.decision.intent,
                    context=snapshot,
                )
                response = ConversationMessageResponse(
                    kind=(
                        "advice"
                        if route.destination is IntentDestination.PROJECT_ADVICE
                        else "project"
                    ),
                    text=answer.text,
                    cited_record_ids=answer.cited_record_ids,
                    recommendation=answer.recommendation,
                    intent=route.decision.intent.value,
                )
            _remember_citations(memory_service, access, response.cited_record_ids)
        return {"_conversation_result": True, **response.model_dump(mode="json")}

    async def invoke_typed_tools() -> dict[str, object]:
        if route is None:
            raise RuntimeError("conversation classification did not complete")
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
            response = ConversationMessageResponse(
                kind="workflow",
                text="Got it. I saved the update and started the site workflow.",
                workflow_run_id=result.agent_run_id,
                site_update_id=result.site_update_id,
                event_id=result.event_id,
            )
            return {"_conversation_result": True, **response.model_dump(mode="json")}
        if route.destination is not IntentDestination.PROJECT_ACTION:
            response = ConversationMessageResponse(
                kind="clarification",
                text="Please clarify the project change you want OG to make.",
            )
            return {"_conversation_result": True, **response.model_dump(mode="json")}

        if clarification_interpretation is None:
            quantity_unit_material = ambiguous_material_quantity_phrase(payload.message)
            if quantity_unit_material is not None:
                parsed_quantity, parsed_unit, material = quantity_unit_material
                clarification_text = (
                    f"Do you mean {parsed_quantity} {parsed_unit} arrived on site, or you want me "
                    f"to prepare a request for {parsed_quantity} {parsed_unit}?"
                )
                memory_service.remember_pending(
                    access,
                    active_clarification=PendingClarification(
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
                    ),
                    clarification=clarification_text,
                )
                response = ConversationMessageResponse(
                    kind="clarification",
                    text=clarification_text,
                    intent=route.decision.intent.value,
                )
                return {"_conversation_result": True, **response.model_dump(mode="json")}

        operate_access = configured_project_access(
            request, project_id, ProjectPermission.OPERATE
        )
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
            operate_access,
            payload.message,
            idempotency_key=key,
            clarification_interpretation=clarification_interpretation,
        )
        response = ConversationMessageResponse(
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
        return {"_conversation_result": True, **response.model_dump(mode="json")}

    settings = getattr(request.app.state, "settings", None) or get_settings()
    invocation_id = request.headers.get("Idempotency-Key") or str(uuid4())
    result = await AdkConversationExecutor(runtime.store, settings).execute_agentic(
        session_id=f"conversation-{access.actor.user_id}",
        invocation_id=invocation_id,
        message=payload.message,
        handlers=AgenticConversationHandlers(
            classify_intent=classify_intent,
            retrieve_authorized_context=retrieve_authorized_context,
            resolve_entities=resolve_entities,
            reason_over_context=reason_over_context,
            invoke_typed_tools=invoke_typed_tools,
        ),
    )
    result.pop("_conversation_result", None)
    return ConversationMessageResponse.model_validate(result)


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
