"""Bounded requests shared by all Companion entry points."""
from typing import Literal
from pydantic import BaseModel, Field, StrictStr


class ChatContext(BaseModel):
    # Browser labels/node text are deliberately not evidence. Only this scope
    # identifier is used to filter server-owned graph retrieval.
    ontology: StrictStr = Field(default='', max_length=128)
    ontology_prefix: StrictStr = Field(default='', max_length=128)
    page: Literal['','home','import','data-flow','ontology','catalog','data-products','registry','graph','code-audit','modeling','requirements','qif','whereused','data-quality','quality','reports','admin'] = ''


class ChatRequest(BaseModel):
    message: StrictStr = Field(min_length=1, max_length=4000)
    session_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    graph_context: ChatContext | None = None
