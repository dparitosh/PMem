from pydantic import BaseModel, Field, validator
from typing import Optional

class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=256, description="Session identifier")
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v.strip():
            raise ValueError('session_id cannot be empty or whitespace')
        return v.strip()
    
    @validator('message')
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
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v.strip():
            raise ValueError('session_id cannot be empty or whitespace')
        return v.strip()

class TextSearchRequest(BaseModel):
    search: str = Field(..., min_length=1, max_length=1000, description="Search query")