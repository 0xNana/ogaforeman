import logging
from datetime import datetime, timedelta
import hashlib

from app.domain.events import EventType, ProjectEvent, EventSource, EventActor, EventActorType
from app.domain.models import MaterialRequest
from app.repositories.interfaces import RepositoryStore

logger = logging.getLogger(__name__)


class SupplierSimulator:
    def __init__(self, store: RepositoryStore) -> None:
        self._store = store

    def submit_order(
        self,
        request: MaterialRequest,
        *,
        occurred_at: datetime,
    ) -> ProjectEvent | None:
        """
        Simulate submitting an order to an external supplier.
        May return a DELIVERY_DELAYED event to simulate supplier pushback.
        """
        logger.info("Simulating supplier order for material request %s", request.id)

        # We simulate a delay if quantity is specifically > 100 or if supplier ends with 'delayed'
        simulate_delay = False
        if request.quantity > 100:
            simulate_delay = True
        if request.supplier and "delay" in request.supplier.lower():
            simulate_delay = True

        if simulate_delay:
            logger.warning("Simulating delivery delay for material request %s", request.id)

            # Generate a canonical event id
            hash_suffix = hashlib.sha256(f"delay_{request.id}".encode()).hexdigest()[:16]
            event_id = f"evt_delay_{hash_suffix}"

            return ProjectEvent(
                event_id=event_id,
                project_id=request.project_id,
                event_type=EventType.DELIVERY_DELAYED,
                source=EventSource.SUPPLIER,
                occurred_at=occurred_at,
                received_at=occurred_at,
                actor=EventActor(type=EventActorType.INTEGRATION, id="int_supplier"),
                idempotency_key=f"delay_{request.id}_{hash_suffix}",
                correlation_id=request.source_event_id,
                payload={
                    "request_id": request.id,
                    "new_date": (occurred_at + timedelta(days=5)).date().isoformat(),
                    "reason": "Supplier inventory low, shipment delayed.",
                },
            )

        return None
