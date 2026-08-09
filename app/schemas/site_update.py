from datetime import UTC, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class SiteUpdatePayload(BaseModel):
    update_id: str
    site_id: str = "site-001"
    raw_text: str
    voice_transcript: Optional[str] = None
    photo_urls: List[str] = Field(default_factory=list)
    reported_by: str = "Site Foreman"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProgressItem(BaseModel):
    task_id: str
    task_name: str
    completion_percentage: float
    notes: Optional[str] = None


class BlockerItem(BaseModel):
    blocker_id: str
    description: str
    severity: str  # low, medium, high, critical
    location: str
    impacted_tasks: List[str] = Field(default_factory=list)


class SiteReportSchema(BaseModel):
    report_id: str
    site_id: str
    date: str
    summary: str
    progress_updates: List[ProgressItem] = Field(default_factory=list)
    blockers: List[BlockerItem] = Field(default_factory=list)
