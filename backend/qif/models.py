"""Typed OpenAPI contracts for the QIF workflow service."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class QifHealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    reference_available: bool


class QifCatalogFile(BaseModel):
    name: str
    area: str


class QifCatalogResponse(BaseModel):
    standard: str
    file_count: int
    files: list[QifCatalogFile]


class QifAgentResponse(BaseModel):
    name: str
    description: str = ""
    tools: list[str] = []


class QifAgentsResponse(BaseModel):
    agents: list[QifAgentResponse]
    count: int


class QifTaskEvent(BaseModel):
    at: str
    stage: str
    level: str
    message: str


class QifArtifact(BaseModel):
    name: str
    path: str
    kind: str


class QifTaskResponse(BaseModel):
    task_id: str
    source: str
    standard_id: str = "qif-3"
    ontology_name: str
    prefix: str
    description: str = ""
    status: str
    stage: str
    progress: int = Field(ge=0, le=100)
    created_at: str
    updated_at: str
    source_files: list[str]
    events: list[QifTaskEvent]
    validation: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    artifacts: list[QifArtifact] = []
    graph_sync: dict[str, Any] = {}
    ontology_id: str | None = None
    agent: str | None = None


class QifTaskListResponse(BaseModel):
    tasks: list[QifTaskResponse]


class QifTaskPreviewResponse(BaseModel):
    task_id: str
    status: str
    validation: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    artifacts: list[QifArtifact] = []
    events: list[QifTaskEvent] = []


class QifActionResponse(BaseModel):
    task_id: str
    status: str
