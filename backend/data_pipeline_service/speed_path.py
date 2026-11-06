"""Governed low-latency event path with the same CEIM contract as batch."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.artifact_store import ArtifactStore
from backend.ceim.contract import contract
from backend.mesh_store import PostgresRegistry


class SpeedConflict(ValueError):
    """A retained identity or reconciliation is owned by another intent."""


_ID = re.compile(r"[a-z][a-z0-9-]{2,62}$")
sources = PostgresRegistry("speed_path_sources")
events = PostgresRegistry("speed_path_events")
reconciliations = PostgresRegistry("speed_path_reconciliations")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def register_source(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    source_id = str(payload.get("source_id") or "").strip().lower()
    standards = sorted({str(item).strip().lower() for item in payload.get("allowed_standards", []) if str(item).strip()})
    if not _ID.fullmatch(source_id) or not standards:
        raise ValueError("source_id must be lowercase kebab-case and allowed_standards must be non-empty")
    if sources.get(source_id):
        raise FileExistsError("Speed-path source already exists")
    retraction_policy = str(payload.get("retraction_policy") or "review").lower()
    if retraction_policy not in {"review", "tombstone"}:
        raise ValueError("retraction_policy must be review or tombstone")
    return sources.create(source_id, {
        "source_id": source_id, "name": str(payload.get("name") or source_id), "owner": str(payload.get("owner") or actor),
        "allowed_standards": standards, "max_lateness_seconds": max(0, min(int(payload.get("max_lateness_seconds", 300)), 86_400)), "retraction_policy": retraction_policy,
        "lifecycle_state": "draft", "enabled": False, "created_at": _now(), "created_by": actor,
    })


def approve_source(source_id: str, actor: str) -> dict[str, Any]:
    record = sources.get(source_id)
    if not record:
        raise LookupError("Speed-path source was not found")
    return sources.put(source_id, {**record, "lifecycle_state": "approved", "enabled": True, "approved_at": _now(), "approved_by": actor})


def list_sources() -> list[dict[str, Any]]:
    return sorted(sources.all().values(), key=lambda item: item["source_id"])


def _same_event(existing,payload,digest):
    if existing.get('payload_digest')==digest:return True
    # Pre-upgrade envelopes could contain transport approval fields. Preserve
    # their immutable receipt while comparing only the business envelope.
    try:
        _,path=ArtifactStore().resolve(existing['artifact_id'])
        if path.stat().st_size>1_048_576:return False
        content=path.read_bytes()
        if 'sha256:'+hashlib.sha256(content).hexdigest()!=existing['artifact_id']:
            raise ValueError('Retained event integrity mismatch')
        retained=json.loads(content)
        if not isinstance(retained,dict):return False
        canonical={key:value for key,value in retained.items() if key not in {'approval_token','approved_by'}}
        return _digest(canonical)==digest
    except (OSError,ValueError,KeyError) as exc:
        raise RuntimeError('Retained event could not be verified; no source intent was replaced') from exc


def capture_event(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    event_id, source_id = str(payload.get("event_id") or "").strip(), str(payload.get("source_id") or "").strip().lower()
    standard = str(payload.get("standard") or "").strip().lower()
    occurred_at = str(payload.get("occurred_at") or "").strip()
    if len(json.dumps(payload, default=str).encode("utf-8")) > 1_048_576:
        raise ValueError("Speed-path event exceeds the 1 MiB bounded envelope limit")
    source = sources.get(source_id)
    event_type = str(payload.get("event_type") or "modification").lower()
    if event_type not in {"creation", "modification", "deletion"}:
        raise ValueError("event_type must be creation, modification or deletion")
    if not event_id or not source_id or not standard or not occurred_at or not isinstance(payload.get("records"), dict):
        raise ValueError("event_id, source_id, standard, occurred_at and records object are required")
    if event_type == "deletion" and not str(payload.get("resource_id") or "").strip():
        raise ValueError("Deletion events require resource_id for retraction review")
    if not source or source.get("lifecycle_state") != "approved" or not source.get("enabled"):
        raise ValueError("Speed-path source is not approved and enabled")
    if standard not in source["allowed_standards"]:
        raise ValueError("Event standard is not allowed for this source")
    try:
        timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None: raise ValueError
    except ValueError as exc:
        raise ValueError("occurred_at must be an ISO-8601 timestamp with timezone") from exc
    # Authorization belongs to request handling, never retained source evidence.
    payload={key:value for key,value in payload.items() if key not in {'approval_token','approved_by'}}
    digest = _digest(payload)
    existing = events.get(event_id)
    if existing:
        if not _same_event(existing,payload,digest): raise SpeedConflict("event_id was reused with a different payload")
        return {**existing, "idempotent": True}
    age_seconds = max(0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())
    late = age_seconds > int(source["max_lateness_seconds"])
    artifact = ArtifactStore().ingest_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(), filename=f"{event_id}.json", kind="speed-event-envelope", media_type="application/json", provenance={"source_id": source_id, "event_id": event_id, "captured_by": actor})
    record = {"event_id": event_id, "source_id": source_id, "standard": standard, "event_type": event_type, "occurred_at": occurred_at, "captured_at": _now(), "captured_by": actor, "payload_digest": digest, "artifact_id": artifact["artifact_id"], "status": "retraction_pending_review" if event_type == "deletion" else "late" if late else "accepted", "quality": {"event_id_unique": True, "provenance_present": True, "lateness_seconds": round(age_seconds, 3), "late": late, "retraction_policy": source["retraction_policy"]}, "reconciliation_id": None}
    try:
        return events.create(event_id, record)
    except FileExistsError:
        retained = events.get(event_id)
        if not retained or not _same_event(retained,payload,digest):
            raise SpeedConflict('event_id was reused with a different payload') from None
        return {**retained, 'idempotent': True}


def list_events(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    return events.page(limit=max(1,min(limit,1000)),offset=offset,order_field='captured_at')[1]


def reconcile(event_ids: list[str], actor: str) -> dict[str, Any]:
    if (not isinstance(event_ids,list) or not 1 <= len(event_ids) <= 500 or
        any(not isinstance(value,str) or not 1 <= len(value) <= 256 for value in event_ids)):
        raise ValueError('Select between 1 and 500 retained event identities')
    ids=sorted(set(event_ids))
    # One bounded owner serializes the current small event gateway. A database
    # advisory lock works across API processes; it is released on process loss.
    with reconciliations.advisory_lock('speed-reconciliation') as acquired:
        if not acquired:raise SpeedConflict('Reconciliation is busy; retry the same event selection')
        return _reconcile(ids,actor)


def _reconcile(ids,actor):
    selected=[events.get(key) for key in ids]
    if any(row is None for row in selected):raise LookupError('One or more speed-path events were not found')
    intent={'event_ids':ids,'payload_digests':[row['payload_digest'] for row in selected],'actor':actor}
    identity='reconcile-'+_digest(intent).split(':',1)[1]
    existing=reconciliations.get(identity)
    # Recover an interrupted legacy transition only for its exact retained set.
    prior={row.get('reconciliation_id') for row in selected if row.get('reconciliation_id')}
    if not existing and len(prior)==1:
        legacy=reconciliations.get(next(iter(prior)))
        if legacy and sorted(set(legacy.get('event_ids',[])))==ids and legacy.get('created_by')==actor:
            identity=legacy['reconciliation_id'];existing=legacy
    for row in selected:
        if row['status'] not in {'accepted','late'} and not (
            row['status'] in {'reconciled','quarantined'} and row.get('reconciliation_id')==identity):
            raise SpeedConflict('An event is held, deleted or belongs to another reconciliation')
    standards={row['standard'] for row in selected}
    if len(standards)!=1:raise ValueError('A reconciliation batch must contain one source standard')
    standard=next(iter(standards))
    if not existing:
        existing=reconciliations.create(identity,{'reconciliation_id':identity,'status':'preparing',
            'event_ids':ids,'intent':intent,'created_by':actor,'created_at':_now()})
    if existing.get('status')=='preparing':
        entities=[];relationships=[]
        for row in selected:
            _,path=ArtifactStore().resolve(row['artifact_id'])
            content=path.read_bytes()
            if 'sha256:'+hashlib.sha256(content).hexdigest()!=row['artifact_id']:
                raise ValueError('Retained event artifact integrity check failed')
            payload=json.loads(content);records=payload['records']
            entities.extend(records.get('entities') or []);relationships.extend(records.get('relationships') or [])
        if not entities and not relationships:raise ValueError('Events contain no CEIM source records')
        normalized=[contract.normalize_entity(standard=standard,record=dict(row)) for row in entities]
        links=[contract.normalize_relationship(standard=standard,record=dict(row)) for row in relationships]
        validation=contract.validate_projection(entities=normalized,relationships=links)
        batch={'contract':'normalized-ceim-batch-v1','representation':'normalized-ceim-v1','standard':standard,
            'ceim_version':contract.version,'mapping_digest':contract.mapping_pack(standard)['digest'],
            'entities':normalized,'relationships':links,'source_event_ids':ids,'provisional':True}
        artifact=ArtifactStore().ingest_bytes(json.dumps(batch,sort_keys=True,separators=(',',':')).encode(),
            filename=identity+'.json',kind='accepted-semantic-partition' if validation.get('conforms') else 'rejected-semantic-partition',
            media_type='application/json',provenance={'producer':'speed-path','reconciled_by':actor})
        existing=reconciliations.put(identity,{**existing,'status':'reconciling','standard':standard,
            'ceim_version':contract.version,'mapping_digest':batch['mapping_digest'],
            'partition_artifact_id':artifact['artifact_id'],'validation':validation,
            'counts':{'events':len(ids),'entities':len(normalized),'relationships':len(links)},
            'publication':'not_attempted; canonical CEIM approval is required'})
    conforms=existing.get('validation',{}).get('conforms',False)
    target='reconciled' if conforms else 'quarantined'
    terminal=existing.get('status') in {'published','ready_for_approved_publication','quarantined'}
    result=existing if terminal else {**existing,'status':'ready_for_approved_publication' if conforms else 'quarantined'}
    expected={row['event_id']:row for row in selected}
    updated={key:{**row,'status':target,'reconciliation_id':identity} for key,row in expected.items()}
    if terminal and expected==updated:return existing
    if not reconciliations.transition_bundle(identity,result,related_store=events,expected_rows=expected,updated_rows=updated,expected_value=existing):
        raise SpeedConflict('Event state changed; recheck the retained reconciliation')
    return result


def review_context(identity):
    row=reconciliations.get(identity)
    if not row:raise LookupError('Reconciliation was not found')
    # Bounded operational evidence, never raw source rows, model prose or secrets.
    return {key:row[key] for key in ('reconciliation_id','status','standard','created_at','created_by',
        'ceim_version','mapping_digest','partition_artifact_id','counts') if key in row} | {
        'name':str(row.get('standard') or 'Incoming').upper()+' event review',
        'description':'Retained incoming business changes; review semantic checks and publication evidence separately.',
        'event_ids':row.get('event_ids',[])[:20],
        'event_count':len(row.get('event_ids',[])),
        'event_ids_truncated':len(row.get('event_ids',[]))>20,
        'record_digest':_digest(row),
        'owl_dl_checked':False,
        'semantic_conforms':row.get('validation',{}).get('conforms'),
        'publication_verified':row.get('status')=='published',
        'advisory_only':True,'business_correctness_established':False}
