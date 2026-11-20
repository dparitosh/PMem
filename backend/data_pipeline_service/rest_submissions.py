"""Reconcile initial source acquisition submissions across reconnects and tabs."""
import hashlib
import json
import re
import uuid
from fastapi import HTTPException
from backend.mesh_store import PostgresRegistry
from . import run_records, rest_sources

store = PostgresRegistry('rest_source_submissions')


def _receipt_intent(receipt):
    intent = receipt.get('intent') if isinstance(receipt, dict) else None
    if (not isinstance(intent, dict) or
            any(not isinstance(intent.get(field), str) or not intent[field].strip()
                for field in ('actor', 'source_id', 'job_id', 'version')) or
            not isinstance(receipt.get('run_id'), str) or not receipt['run_id'].strip()):
        raise HTTPException(409, 'Retained submission is inconsistent; operator review is required')
    return intent


def _verify_run(run, run_id, intent):
    if (not isinstance(run, dict) or run.get('run_id') != run_id or
            not isinstance(run.get('status'), str) or not run['status'].strip() or
            run.get('executed_by') != intent['actor'] or
            run.get('job_id') != intent['job_id'] or
            run.get('job_version') != intent['version'] or
            run.get('source_system') != intent['source_id']):
        raise HTTPException(409, 'Retained run does not match the submission intent')

def retained(key, actor, *, receipt_store=None):
    receipts = receipt_store if receipt_store is not None else store
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        raise HTTPException(422, 'Invalid submission reference')
    receipt = receipts.get('request:' + hashlib.sha256(key.encode()).hexdigest())
    if receipt is None: raise HTTPException(404, 'Submission reference has not been retained yet')
    intent = _receipt_intent(receipt)
    if intent['actor'] != actor:
        raise HTTPException(409, 'Submission reference belongs to a different identity')
    run = run_records.get(receipt['run_id'])
    if run is None:
        return {'status': 'pending_enqueue', 'submission_id': key}
    _verify_run(run, receipt['run_id'], intent)
    return {'status': run['status'], 'run_manifest': run, 'submission_id': key}


def submit(definition, payload, actor, correlation_id, *, source_store=None, receipt_store=None, kind='rest'):
    receipts = receipt_store if receipt_store is not None else store
    sources = source_store if source_store is not None else rest_sources.store
    key = payload.get('idempotency_key')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        raise ValueError('Source acquisition requires a retained idempotency key')
    source_id = payload.get('source_id')
    if not isinstance(source_id, str) or not sources.get(source_id):
        raise ValueError('Registered source was not found')
    intent = {'actor': actor, 'source_id': source_id, 'job_id': definition['job_id'], 'version': definition['version']}
    digest = hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()
    request_key = 'request:' + hashlib.sha256(key.encode()).hexdigest()
    intent_key = 'intent:' + digest
    # Request identity is global so changing authenticated actor cannot silently
    # replay an unresolved operation as a different person's new acquisition.
    with receipts.advisory_lock(request_key) as acquired:
        if not acquired: raise HTTPException(409, 'Submission is being reconciled; retry the same reference')
        with receipts.advisory_lock(intent_key) as acquired:
            if not acquired: raise HTTPException(409, 'Source acquisition is being submitted; retry the same reference')
            receipt = receipts.get(request_key)
            if receipt is not None and _receipt_intent(receipt) != intent:
                raise HTTPException(409, 'Submission reference belongs to a different source, job or identity')
            if receipt is not None:
                run_id = receipt['run_id']
            else:
                prior = receipts.get(intent_key)
                if prior is not None and (not isinstance(prior, dict) or not isinstance(prior.get('run_id'), str) or not prior['run_id'].strip()):
                    raise HTTPException(409, 'Retained submission is inconsistent; operator review is required')
                active = run_records.get(prior['run_id']) if prior is not None else None
                if active is not None:
                    _verify_run(active, prior['run_id'], intent)
                if prior is not None and (active is None or active['status'] in {'queued', 'running'}):
                    run_id = prior['run_id']
                else:
                    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'depo:' + kind + ':' + key))
                    # Persist the intent before queueing. A failure between these
                    # writes leaves a recoverable pending reference, not a window
                    # where another tab can enqueue a different run.
                    receipts.put(intent_key, {'run_id': run_id})
                receipts.create(request_key, {'run_id': run_id, 'intent': intent})
            run = run_records.get(run_id)
            if run is not None:
                _verify_run(run, run_id, intent)
            else:
                run = run_records.enqueue(definition, {'source_id': source_id, 'source_system': source_id,
                    'execution_actor': actor}, correlation_id=correlation_id, run_id=run_id)
            return {'status': run['status'], 'run': run, 'run_manifest': run, 'submission_id': key}
