from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional

class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Session identifier. If omitted, the backend creates one for external clients.",
    )
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    graph_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional compact graph context from the UI (visible nodes/relationships, active view, selection hints)",
    )

    @field_validator('graph_context', mode='before')
    @classmethod
    def validate_graph_context(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError('graph_context must be an object')

        def inspect(item: Any, depth: int = 0) -> int:
            if depth > 6:
                raise ValueError('graph_context nesting exceeds 6 levels')
            if isinstance(item, dict):
                if len(item) > 100:
                    raise ValueError('graph_context object has too many fields')
                return sum(len(str(key)) + inspect(child, depth + 1) for key, child in item.items())
            if isinstance(item, list):
                if len(item) > 100:
                    raise ValueError('graph_context list exceeds 100 items')
                return sum(inspect(child, depth + 1) for child in item)
            if isinstance(item, str):
                if len(item) > 4000:
                    raise ValueError('graph_context text value exceeds 4000 characters')
                return len(item)
            return len(str(item))

        if inspect(value) > 128_000:
            raise ValueError('graph_context exceeds 128 KB')
        return value
    
    @field_validator('session_id', mode='before')
    def validate_session_id(cls, v):
        if v is None:
            return None
        value = str(v).strip()
        if not value:
            return None
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
