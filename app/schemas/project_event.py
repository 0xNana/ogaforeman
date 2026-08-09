from pydantic import BaseModel

from app.domain.events import EventType, ProjectEvent as ProjectEvent


EventCategory = EventType


class ApprovalGateDecision(BaseModel):
    request_id: str
    site_id: str = "site-001"
    approved_by: str
    approved: bool
    notes: str | None = None
