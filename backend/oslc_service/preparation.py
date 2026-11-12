"""Existing worker handoff: retain reviewed OSLC records, never publish a graph."""
import json
from backend.artifact_store import ArtifactStore
from backend.depo_platform.execution_guard import ensure_execution_allowed
from .sync import OSLCSyncStore
from .access import authorize


def execute(runner,payload,*,correlation_id):
    ensure_execution_allowed()
    snapshot=OSLCSyncStore().get(payload.get('snapshot_id',''))
    if not snapshot or not snapshot.get('complete') or snapshot.get('status')!='staged':
        raise ValueError('Select a complete retained OSLC snapshot')
    if not snapshot.get('content_sha256') or not snapshot.get('provider_url') or not snapshot.get('requested_by'):
        raise ValueError('Legacy OSLC snapshot lacks verified provenance; acquire it again')
    if payload.get('content_sha256') and payload['content_sha256']!=snapshot['content_sha256']:
        raise ValueError('Snapshot content differs from the retained preparation intent')
    authorize(str(payload.get('execution_actor') or ''),'syncs',snapshot['sync_id'])
    records=snapshot['resources']
    if len(records)>1000 or any(not isinstance(row,dict) for row in records):
        raise ValueError('Select a snapshot of at most 1000 object records for reviewed field mapping')
    content=json.dumps(records,ensure_ascii=False).encode()
    if len(content)>8*1024*1024:raise ValueError('OSLC preparation exceeds the 8 MiB mapping limit')
    artifact=ArtifactStore().ingest_bytes(content,filename='oslc-records.json',kind='connector-records',media_type='application/json',
        provenance={key:snapshot[key] for key in ('sync_id','provider_url','requested_by','content_sha256')})
    return {'status':'completed','counts':{'records':len(records)},'partition_artifacts':{'source':artifact['artifact_id']},
            'source_id':'oslc:'+snapshot['sync_id'],'semantic_validation':'not_assessed','publication':'not_attempted'}


def submit(definition,payload,actor,correlation_id):
    import hashlib,re,uuid
    from fastapi import HTTPException
    from backend.mesh_store import PostgresRegistry
    from backend.data_pipeline_service import run_records
    key=payload.get('idempotency_key','')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',key):
        raise HTTPException(422,'A retained submission reference is required')
    snapshot=OSLCSyncStore().get(payload.get('snapshot_id',''))
    if not snapshot or not snapshot.get('complete') or not snapshot.get('content_sha256'):
        raise HTTPException(422,'Select a complete snapshot with retained provenance')
    intent={'actor':actor,'snapshot_id':snapshot['sync_id'],'content_sha256':snapshot['content_sha256'],
            'job_id':definition['job_id'],'version':definition['version']}
    receipts=PostgresRegistry('oslc_preparation_submissions')
    receipt_key=hashlib.sha256(key.encode()).hexdigest()
    with receipts.advisory_lock(receipt_key) as acquired:
        if not acquired:raise HTTPException(409,'Preparation submission is active; retry the same reference')
        previous=receipts.get(receipt_key)
        if previous and previous['intent']!=intent:raise HTTPException(409,'Submission reference belongs to another preparation')
        run_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'nexus:oslc-preparation:'+receipt_key))
        if not previous:receipts.create(receipt_key,{'intent':intent,'run_id':run_id})
        run=run_records.get(run_id)
        if not run:
            run=run_records.enqueue(definition,{'snapshot_id':snapshot['sync_id'],
                'content_sha256':snapshot['content_sha256'],'execution_actor':actor},correlation_id=correlation_id,run_id=run_id)
        return {'status':run['status'],'run':run,'run_manifest':run,'submission_id':key}
