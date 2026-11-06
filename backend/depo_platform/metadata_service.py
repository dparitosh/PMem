"""PostgreSQL metadata API adapter; legacy graph storage remains an explicit mode."""
import os
from datetime import datetime, timezone
from fastapi import HTTPException


def enabled():
    mode=os.getenv('DEPO_METADATA_STORAGE','neo4j').strip().lower()
    if mode not in {'neo4j','postgres'}: raise RuntimeError('DEPO_METADATA_STORAGE must be neo4j or postgres')
    return mode=='postgres'


def repository():
    from .metadata_repository import MetadataRepository
    return MetadataRepository()


def get(asset_id):
    value=repository().get(asset_id)
    if not value: raise HTTPException(404,'Metadata asset not found')
    return value


def save(value, actor, expected_revision, comment=''):
    from .metadata_validation import validate_asset_state
    try:
        validate_asset_state(value)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    from .metadata_repository import MetadataConflict
    try:
        result=repository().save(value['asset_id'],value,expected_revision=expected_revision,actor=actor,comment=comment)
    except MetadataConflict as exc:
        raise HTTPException(409,'Metadata changed; reload before updating') from exc
    return {**value,'revision':result['revision'],'publication_status':result['publication_status']}


def update(asset_id, updates, actor, expected_revision=None):
    old=get(asset_id)
    revision=old.pop('revision')
    old.pop('publication_status',None)
    if expected_revision is not None and expected_revision != revision:
        raise HTTPException(409,'Metadata changed; reload before updating')
    if 'lifecycle_status' in updates: raise HTTPException(400,'Use the lifecycle transition endpoint')
    return save({**old,**updates,'updated_at':datetime.now(timezone.utc).isoformat()},actor,revision)


def transition(asset_id, payload, actor):
    old=get(asset_id)
    revision=old.pop('revision')
    old.pop('publication_status',None)
    allowed={'draft':{'in_review'},'in_review':{'draft','approved'},'approved':{'in_review','deprecated'},'deprecated':{'retired'},'retired':set()}
    if payload.status not in allowed.get(old.get('lifecycle_status','draft'),set()):
        raise HTTPException(409,'Invalid metadata lifecycle transition')
    if payload.status=='approved' and not str(old.get('steward') or '').strip():
        raise HTTPException(409,'Assign a metadata steward before approval')
    value={**old,'lifecycle_status':payload.status,'updated_at':datetime.now(timezone.utc).isoformat()}
    for key in ('approval_evidence','deprecation_reason'):
        if getattr(payload,key): value[key]=getattr(payload,key)
    return save(value,actor,revision,payload.comment)
