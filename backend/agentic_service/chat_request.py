"""Bounded requests shared by all Companion entry points."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class ChatContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Browser labels/node text are deliberately not evidence. Only this scope
    # identifier is used to filter server-owned graph retrieval.
    ontology: StrictStr = Field(default='', max_length=128)
    ontology_prefix: StrictStr = Field(default='', max_length=128)
    node_id: StrictStr = Field(default='', max_length=256)
    run_id: StrictStr = Field(default='', max_length=256)
    reconciliation_id: StrictStr = Field(default='', max_length=256)
    product_id: StrictStr = Field(default='', max_length=256)
    product_version: StrictStr = Field(default='', max_length=256)
    page: Literal['','home','import','data-flow','ontology','catalog','data-products','registry','graph','code-audit','modeling','requirements','qif','whereused','recommendations','change-control','data-quality','quality','reports','admin'] = ''

    @model_validator(mode='after')
    def operational_selection(self):
        if sum(bool(value) for value in (self.run_id,self.product_id,self.reconciliation_id)) > 1:
            raise ValueError('Select one run, product or event review')
        if self.product_version and not self.product_id:
            raise ValueError('Product version requires its product identity')
        return self


class ChatRequest(BaseModel):
    message: StrictStr = Field(min_length=1, max_length=4000)
    session_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    graph_context: ChatContext | None = None
