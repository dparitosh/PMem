"""Bounded requests shared by all Companion entry points."""
from pydantic import BaseModel, Field, StrictStr


class ChatContext(BaseModel):
    # Browser labels/node text are deliberately not evidence. Only this scope
    # identifier is used to filter server-owned graph retrieval.
    ontology: StrictStr = Field(default='', max_length=128)


class ChatRequest(BaseModel):
    message: StrictStr = Field(min_length=1, max_length=4000)
    session_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    graph_context: ChatContext | None = None
