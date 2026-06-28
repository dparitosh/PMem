from typing import Any

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    workflow_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
