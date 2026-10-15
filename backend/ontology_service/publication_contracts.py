"""Published response contract for durable publication submissions."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict


class PublicationJobResponse(BaseModel):
    model_config = ConfigDict(extra='allow')
    job_id: str
    ontology_id: str
    artifact_sha256: str
    approved_by: str
    status: Literal['queued', 'running', 'reconciliation_required', 'published', 'failed', 'cancelled', 'timed_out']
    created_at: str
    updated_at: str
    deadline_at: str | None = None
    queue_deadline_at: str | None = None
    next_attempt_at: str | None = None
    attempt: int = 0
    reconciliation_required: bool = False
    recovery_action: str | None = None
    result: dict[str, Any] | None = None
