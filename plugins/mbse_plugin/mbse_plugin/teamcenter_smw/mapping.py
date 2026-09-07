"""Declarative JSON mappings with explicit quality failures, no executable expressions."""
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


def read(record, path):
    for part in path.split('.'):
        if not isinstance(record, dict):
            return None
        record = record.get(part)
    return record


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip()) or value == [] or value == {}


class ObjectMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_type: Literal['Requirement', 'Resource', 'Part', 'Assembly', 'Document', 'Process', 'ProductRevision']
    fields: dict[str, str] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_fields(self):
        if len(set(self.fields.values())) != len(self.fields):
            raise ValueError('Source fields cannot share a target property')
        if any(not p.strip() or any(not s.strip() for s in p.split('.')) for p in [*self.fields, *self.fields.values(), *self.required]):
            raise ValueError('Field paths and target names must be nonblank')
        return self


class MappingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: Literal['draft'] = 'draft'
    connector_enabled: Literal[False] = False
    endpoint: str = ''
    credential_reference: str = ''
    source_namespace: str = Field(min_length=1)
    id_field: str = 'uid'
    type_field: str = 'type'
    revision_field: str = 'revision'
    identity_mode: Literal['source', 'source_revision'] = 'source'
    configuration: str = ''
    deleted_field: str = 'deleted'
    objects: dict[str, ObjectMapping]
    relationships: dict[str, Literal['HAS_PART', 'SATISFIES', 'VERIFIED_BY', 'TRACE_TO', 'REALIZES', 'DERIVED_FROM']]


def preview(config: MappingConfig, records: list[dict], links: list[dict]) -> dict:
    digest = hashlib.sha256(json.dumps(config.model_dump(), sort_keys=True).encode()).hexdigest()
    entities, relationships, errors, ids = [], [], [], {}
    for index, record in enumerate(records):
        source_id = read(record, config.id_field)
        kind = read(record, config.type_field)
        revision = read(record, config.revision_field)
        deleted = read(record, config.deleted_field)
        if deleted not in (None, False):
            errors.append({'record': index, 'rule': 'deletion_requires_live_reconciliation'})
            continue
        if not isinstance(source_id, str) or not source_id.strip() or not isinstance(kind, str) or kind not in config.objects:
            errors.append({'record': index, 'rule': 'identifier_and_declared_type'})
            continue
        if config.identity_mode == 'source_revision' and (not isinstance(revision, str) or not revision.strip()):
            errors.append({'record': index, 'rule': 'revision_required'})
            continue
        key = (source_id, revision if config.identity_mode == 'source_revision' else '')
        if key in ids:
            errors.append({'record': index, 'rule': 'duplicate_identifier'})
            continue
        mapping = config.objects[kind]
        missing = [field for field in mapping.required if blank(read(record, field))]
        if missing:
            errors.append({'record': index, 'rule': 'required_fields', 'fields': missing})
            continue
        from urllib.parse import quote
        identifier = ':'.join(quote(v, safe='') for v in (config.source_namespace, config.configuration, *key))
        ids[key] = identifier
        entities.append({'id': identifier, 'ceim_type': mapping.target_type,
            'properties': {target: read(record, source) for source, target in mapping.fields.items() if read(record, source) is not None},
            'provenance': {'source_id': source_id, 'source_type': kind, 'revision': revision, 'configuration': config.configuration, 'mapping_id': config.id, 'mapping_version': config.version, 'mapping_digest': digest}})
    for index, link in enumerate(links):
        source, target, kind = link.get('source'), link.get('target'), link.get('type')
        sr = link.get('source_revision', '') if config.identity_mode == 'source_revision' else ''
        tr = link.get('target_revision', '') if config.identity_mode == 'source_revision' else ''
        if not all(isinstance(v, str) for v in (source, target, kind, sr, tr)) or (source, sr) not in ids or (target, tr) not in ids or kind not in config.relationships:
            errors.append({'link': index, 'rule': 'declared_relationship_and_resolved_endpoints'})
            continue
        relationships.append({'source_id': ids[(source, sr)], 'target_id': ids[(target, tr)], 'relationship': config.relationships[kind]})
    return {'status': 'invalid' if errors else ('draft_preview' if records else 'empty'), 'publishable': False,
        'counts': {'input': len(records), 'accepted': len(entities), 'errors': len(errors)},
        'entities': entities, 'relationships': relationships, 'quality_errors': errors,
        'mapping_digest': digest, 'limitations': ['Live schema unverified', 'No synchronization or deletion execution']}
