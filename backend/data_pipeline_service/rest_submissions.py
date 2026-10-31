"""Reconcile initial REST acquisition submissions across reconnects and tabs."""
import hashlib
import json
import re
import uuid
from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry
from . import run_records, rest_sources

store = PostgresRegistry('rest_source_submissions')


def retained(key, actor):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        raise HTTPException(422, 'Invalid submission reference')
    receipt = store.get('request:' + hashlib.sha256(key.encode()).hexdigest())
    if not receipt: raise HTTPException(404, 'Submission reference has not been retained yet')
    if receipt['intent']['actor'] != actor:
        raise HTTPException(409, 'Submission reference belongs to a different identity')
    run = run_records.get(receipt['run_id'])
    if not run:
        return {'status': 'pending_enqueue', 'submission_id': key}
    return {'status': run['status'], 'run_manifest': run, 'submission_id': key}


def submit(definition, payload, actor, correlation_id):
    key = payload.get('idempotency_key')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        raise ValueError('REST acquisition requires a retained idempotency key')
    source_id = payload.get('source_id')
    if not isinstance(source_id, str) or not rest_sources.store.get(source_id):
        raise ValueError('Registered REST source was not found')
    intent = {'actor': actor, 'source_id': source_id, 'job_id': definition['job_id'], 'version': definition['version']}
    digest = hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()
    request_key = 'request:' + hashlib.sha256(key.encode()).hexdigest()
    intent_key = 'intent:' + digest
    # Request identity is global so changing authenticated actor cannot silently
    # replay an unresolved operation as a different person's new acquisition.
    with store.advisory_lock(request_key) as acquired:
        if not acquired: raise HTTPException(409, 'Submission is being reconciled; retry the same reference')
        with store.advisory_lock(intent_key) as acquired:
            if not acquired: raise HTTPException(409, 'Source acquisition is being submitted; retry the same reference')
            receipt = store.get(request_key)
            if receipt and receipt['intent'] != intent:
                raise HTTPException(409, 'Submission reference belongs to a different source, job or identity')
            if receipt:
                run_id = receipt['run_id']
            else:
                prior = store.get(intent_key)
                active = run_records.get(prior['run_id']) if prior else None
                if prior and (not active or active['status'] in {'queued', 'running'}):
                    run_id = prior['run_id']
                else:
                    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'depo:rest:' + key))
                    # Persist the intent before queueing. A failure between these
                    # writes leaves a recoverable pending reference, not a window
                    # where another tab can enqueue a different run.
                    store.put(intent_key, {'run_id': run_id})
                store.create(request_key, {'run_id': run_id, 'intent': intent})
            run = run_records.get(run_id)
            if run:
                if (run.get('executed_by') != actor or run.get('job_id') != definition['job_id'] or
                        run.get('job_version') != definition['version'] or run.get('source_system') != source_id):
                    raise HTTPException(409, 'Retained run does not match the submission intent')
            else:
                run = run_records.enqueue(definition, {'source_id': source_id, 'source_system': source_id,
                    'execution_actor': actor}, correlation_id=correlation_id, run_id=run_id)
            return {'status': run['status'], 'run': run, 'run_manifest': run, 'submission_id': key}
