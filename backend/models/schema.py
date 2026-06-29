from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional
from uuid import uuid4

class ChatRequest(BaseModel):
    session_id: str = Field(
        default_factory=lambda: f"chat-{uuid4()}",
        min_length=1,
        max_length=256,
        description="Session identifier. If omitted, the backend creates one for external clients.",
    )
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    graph_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional compact graph context from the UI (visible nodes/relationships, active view, selection hints)",
    )
    
    @field_validator('session_id', mode='before')
    def validate_session_id(cls, v):
        if v is None:
            return f"chat-{uuid4()}"
        value = str(v).strip()
        if not value:
            return f"chat-{uuid4()}"
        return value[:256]

    @field_validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError('message cannot be empty or whitespace')
        return v.strip()

class ChatResponse(BaseModel):
    session_id: str
    response: str

class ChatWithCypherResponse(BaseModel):
    session_id: str
    response: str
    raw_results: Optional[str] = None

class ResetRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=256)
    
    @field_validator('session_id')
    def validate_session_id(cls, v):
        if not v.strip():
            raise ValueError('session_id cannot be empty or whitespace')
        return v.strip()

class TextSearchRequest(BaseModel):
    search: str = Field(..., min_length=1, max_length=1000, description="Search query")
