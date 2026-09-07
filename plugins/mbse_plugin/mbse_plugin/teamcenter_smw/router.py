import json
from importlib.resources import files
from fastapi import APIRouter
from pydantic import BaseModel, Field
from .mapping import MappingConfig, preview

router = APIRouter(prefix='/teamcenter-smw', tags=['Teamcenter SMW configuration'])


class PreviewRequest(BaseModel):
    mapping: MappingConfig
    records: list[dict] = Field(max_length=2000)
    links: list[dict] = Field(default_factory=list, max_length=10000)


@router.get('/template')
def template():
    return json.loads(files(__package__).joinpath('mapping.example.json').read_text())


@router.post('/preview')
def mapping_preview(payload: PreviewRequest):
    return preview(payload.mapping, payload.records, payload.links)
