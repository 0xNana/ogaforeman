import logging
from datetime import UTC, datetime
from hashlib import sha256

from app.domain.activity import ActivitySpec, MutationContext, WorkflowActivityAction
from app.domain.enums import ActorType, ApprovalActionType, MaterialRequestStatus
from app.domain.events import EventType, ProjectEvent
from app.domain.models import AgentRun, Approval, MaterialRequest, OutboxMessage, OutboxStatus
from app.domain.policies import ensure_material_request_transition
from app.repositories.interfaces import RepositorySession, RepositoryStore
from app.infrastructure.supplier_simulator import SupplierSimulator
from app.services.activity import ActivityService
from app.services.workflow_audit import WorkflowAuditService
from app.services.outbox import OutboxService

logger = logging.getLogger(__name__)


class ExternalActionService:
    _SUPPLIER_SUBMISSION = "supplier:submit_material_request"

    def __init__(self, store: RepositoryStore) -> None:
        self._store = store
        self._outbox = OutboxService(store)
        self._activities = ActivityService(store)
        self._simulator = SupplierSimulator(store)

    def continue_approved_purchase(self, event: ProjectEvent) -> ProjectEvent | None:
        if event.event_type is not EventType.APPROVAL_GRANTED:
            raise ValueError("supplier continuation requires APPROVAL_GRANTED")
        digest = sha256(event.idempotency_key.encode("utf-8")).hexdigest()
        message = self._outbox.queue(
            project_id=event.project_id,
            message_type=self._SUPPLIER_SUBMISSION,
            payload=event.model_dump(mode="json"),
            deduplication_key=f"supplier-action:{digest}",
        )
        return self.process_outbox_message(event.project_id, message.id)

    def process_outbox_message(
        self,
        project_id: str,
        message_id: str,
    ) -> ProjectEvent | None:
        request_id: str | None = None

        def _handler(message: OutboxMessage) -> None:
            nonlocal request_id
            if message.message_type in {
                EventType.APPROVAL_GRANTED.value,
                self._SUPPLIER_SUBMISSION,
            }:
                payload = message.payload
                approval_id = payload.get("approval_id")
                event = None
                if approval_id is None and payload.get("event_type") == EventType.APPROVAL_GRANTED:
                    event = ProjectEvent.model_validate(payload)
                    approval_id = event.payload.get("approval_id")
                if not approval_id:
                    raise ValueError("supplier action is missing approval_id")

                # Fetch approval to check if it's for purchase
                def _get_approval_and_request(session):
                    approval = session.repository(Approval).get(project_id, approval_id)
                    request = None
                    if approval and approval.action_type == ApprovalActionType.PURCHASE:
                        requests = session.repository(MaterialRequest).list(project_id)
                        for r in requests:
                            if r.approval_id == approval_id:
                                request = r
                                break
                    return approval, request

                approval, request = self._store.run_transaction(_get_approval_and_request)

                if approval and request:
                    request_id = request.id
                    run_id = self._run_id_for_request(project_id, request)
                    submitted = self._mark_submitted(
                        project_id,
                        request,
                        message,
                        event,
                        run_id=run_id,
                    )
                    occurred_at = event.occurred_at if event is not None else datetime.now(UTC)
                    delay_event = self._simulator.submit_order(
                        submitted,
                        occurred_at=occurred_at,
                    )
                    if run_id is not None:
                        source_event_id = event.event_id if event is not None else message.id
                        WorkflowAuditService(self._store).record(
                            MutationContext(
                                project_id=project_id,
                                actor_type=ActorType.SYSTEM,
                                source_event_id=source_event_id,
                                agent_run_id=run_id,
                                idempotency_key=(
                                    "workflow-audit:external-action:"
                                    + sha256(message.id.encode("utf-8")).hexdigest()[:32]
                                ),
                                occurred_at=occurred_at,
                            ),
                            action=WorkflowActivityAction.EXTERNAL_ACTION_EXECUTED,
                            entity_type="material_request",
                            entity_id=submitted.id,
                            summary="Executed the approved supplier simulator action.",
                            metadata={
                                "status": "executed",
                                "adapter": "supplier_simulator",
                                "external_status": submitted.status.value,
                                "outcome": (
                                    "delivery_delay_reported"
                                    if delay_event is not None
                                    else "accepted"
                                ),
                                "approval_id": submitted.approval_id,
                                "material_request_id": submitted.id,
                                "outbox_message_id": message.id,
                                "delivery_event_id": (
                                    delay_event.event_id if delay_event is not None else None
                                ),
                            },
                        )
                    if delay_event:
                        self._outbox.queue(
                            project_id=project_id,
                            message_type=EventType.DELIVERY_DELAYED.value,
                            payload=delay_event.model_dump(mode="json"),
                            deduplication_key=delay_event.idempotency_key,
                        )
                else:
                    raise RuntimeError("approved purchase has no linked material request")

        processed = self._outbox.process(project_id, message_id, _handler)
        if processed.status is not OutboxStatus.COMPLETED:
            raise RuntimeError(processed.last_error or "supplier action failed")
        if request_id is None:
            request_id = self._request_id_for_message(processed)
        if request_id is None:
            return None
        return self._delivery_delay_for_request(project_id, request_id)

    def _request_id_for_message(self, message: OutboxMessage) -> str | None:
        payload = message.payload
        approval_id = payload.get("approval_id")
        if approval_id is None and payload.get("event_type") == EventType.APPROVAL_GRANTED:
            approval_id = ProjectEvent.model_validate(payload).payload.get("approval_id")
        if approval_id is None:
            return None
        return self._store.run_transaction(
            lambda session: next(
                (
                    request.id
                    for request in session.repository(MaterialRequest).list(message.project_id)
                    if request.approval_id == approval_id
                ),
                None,
            )
        )

    def _delivery_delay_for_request(
        self,
        project_id: str,
        request_id: str,
    ) -> ProjectEvent | None:
        messages = self._store.repository(OutboxMessage).list(project_id)
        for message in messages:
            if message.message_type != EventType.DELIVERY_DELAYED.value:
                continue
            event = ProjectEvent.model_validate(message.payload)
            if event.payload.get("request_id") == request_id:
                return event
        return None

    def _mark_submitted(
        self,
        project_id: str,
        request: MaterialRequest,
        message: OutboxMessage,
        event: ProjectEvent | None,
        *,
        run_id: str | None,
    ) -> MaterialRequest:
        occurred_at = event.occurred_at if event is not None else datetime.now(UTC)
        source_event_id = event.event_id if event is not None else message.id
        key_digest = sha256(
            f"{message.deduplication_key}\x00supplier-submit".encode("utf-8")
        ).hexdigest()[:32]
        context = MutationContext(
            project_id=project_id,
            actor_type=ActorType.SYSTEM,
            source_event_id=source_event_id,
            agent_run_id=run_id,
            idempotency_key=f"supplier-submit:{key_digest}",
            occurred_at=occurred_at,
        )
        result = self._activities.mutate(
            context,
            ActivitySpec(
                action="material_request.submitted",
                entity_type="material_request",
                entity_id=request.id,
                summary="Submitted an approved material request to the supplier simulator.",
                metadata={"approval_id": request.approval_id},
            ),
            lambda session: self._submit_request(
                session,
                project_id,
                request.id,
                occurred_at,
            ),
            replay=lambda session, _activity: session.repository(MaterialRequest).require(
                project_id,
                request.id,
            ),
        )
        if result.value is None:
            raise RuntimeError("supplier submission did not resolve the material request")
        return result.value

    def _run_id_for_request(
        self,
        project_id: str,
        request: MaterialRequest,
    ) -> str | None:
        matches = [
            run.id
            for run in self._store.repository(AgentRun).list(project_id)
            if run.trigger_event_id == request.source_event_id
        ]
        if len(matches) > 1:
            raise RuntimeError("material request source is linked to more than one agent run")
        return matches[0] if matches else None

    @staticmethod
    def _submit_request(
        session: RepositorySession,
        project_id: str,
        request_id: str,
        occurred_at: datetime,
    ) -> MaterialRequest:
        repository = session.repository(MaterialRequest)
        request = repository.require(project_id, request_id)
        ensure_material_request_transition(request.status, MaterialRequestStatus.SUBMITTED)
        return repository.save(
            request.model_copy(
                update={
                    "status": MaterialRequestStatus.SUBMITTED,
                    "updated_at": occurred_at,
                }
            ),
            expected_version=repository.version_of(project_id, request_id),
        )
