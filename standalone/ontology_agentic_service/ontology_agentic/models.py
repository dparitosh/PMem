from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool


class AgentRunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    workflow_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class Owlready2Request(BaseModel):
    path: str
    run_reasoner: StrictBool = False
    reasoner: Literal["hermit", "pellet"] = "hermit"
    infer_property_values: StrictBool = False
