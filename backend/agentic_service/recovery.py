"""Pure recovery rules: never replay an uncertain write or extend a deadline."""
import copy
import hashlib
import json
from datetime import datetime, timezone


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def execution_payload(payload):
    def clean(value):
        if isinstance(value, dict):
            for key in value:
                name = key.lower()
                if name not in {'approval_token', 'api_key', 'authorization', 'access_token', 'password'} and (name in {'headers', 'credentials', 'token', 'secret'} or name.endswith(('_token', '_api_key', '_password', '_secret'))):
                    raise ValueError('Workflow inputs cannot contain credentials or arbitrary headers')
            return {key: clean(item) for key, item in value.items()
                    if key.lower() not in {'approval_token', 'api_key', 'authorization', 'access_token', 'password'}}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean({key: payload[key] for key in ('workflow_id', 'inputs', 'step_inputs') if key in payload})


def prepare_recovery(record, workflow, activity_at=None):
    if record.get('compensations'):
        raise ValueError('A compensated workflow cannot resume using its previous step outputs')
    if record.get('status') == 'running':
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(activity_at or record['updated_at'])).total_seconds()
        if age < 60:
            raise ValueError('Execution has recent activity; recovery is blocked')
    elif record.get('status') not in {'failed', 'interrupted', 'recoverable'}:
        raise ValueError('Only an interrupted or failed execution can be recovered')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(record['deadline_at']):
        raise ValueError('The original workflow deadline has expired')
    if record.get('reconciliation_required') or (record.get('pending_step') or {}).get('mutates'):
        raise ValueError('Reconcile the uncertain write before recovery')
    if record.get('workflow_digest') != fingerprint(workflow):
        raise ValueError('Workflow definition changed; recovery is blocked')
    if not record.get('execution_payload'):
        raise ValueError('This older run has no retained execution inputs')
    result = copy.deepcopy(record)
    result['traces'] = [row for row in result['traces'] if row['status'] == 'completed']
    if [row['sequence'] for row in result['traces']] != list(range(1, len(result['traces']) + 1)):
        raise ValueError('Completed traces must form a contiguous workflow prefix')
    result.update(status='recovering', pending_step=None)
    return result


def reconcile(record, outcome, evidence, actor, result=None, executor_stopped=False, activity_at=None):
    if record.get('status') == 'running':
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(activity_at or record['updated_at'])).total_seconds()
        if executor_stopped is not True or age < 60:
            raise ValueError('Verify that the stale executor has stopped before reconciling its write')
    elif record.get('status') not in {'failed', 'interrupted', 'timed_out'}:
        raise ValueError('Only a stopped run may be reconciled')
    pending = record.get('pending_step')
    if not pending or not pending.get('mutates'):
        raise ValueError('No uncertain mutation is retained')
    if outcome not in {'completed', 'not_applied'} or not isinstance(evidence, str) or not evidence.strip():
        raise ValueError('Supply completed/not_applied and verified downstream receipt evidence')
    if len(evidence) > 4000:
        raise ValueError('Reconciliation evidence exceeds 4000 characters')
    if outcome == 'completed' and not isinstance(result, dict):
        raise ValueError('A completed write requires its downstream result object')
    updated = copy.deepcopy(record)
    from uuid import uuid4
    updated['execution_id'] = uuid4().hex  # Fence any old executor after supervisor reconciliation.
    updated['traces'] = [row for row in updated['traces'] if row['status'] == 'completed']
    if outcome == 'completed':
        updated['traces'].append({**pending, 'status': 'completed', 'result': result, 'reconciled': True})
    updated.setdefault('reconciliations', []).append(dict(outcome=outcome, evidence=evidence,
        actor=actor, sequence=pending['sequence'], recorded_at=datetime.now(timezone.utc).isoformat()))
    updated.update(pending_step=None, reconciliation_required=False, status='recoverable')
    steps = (record.get('workflow_definition') or {}).get('steps',[])
    if outcome == 'completed' and steps and len(updated['traces']) == len(steps):
        updated.update(status='completed',finished_at=datetime.now(timezone.utc).isoformat())
    return updated
