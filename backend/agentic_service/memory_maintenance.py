"""Bounded operational receipts for existing memory maintenance operations."""
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool


async def run_steps(store, operations):
    def now():
        return datetime.now(timezone.utc).isoformat()

    record = {'started_at': now(), 'status': 'running', 'steps': []}
    # The latest receipt is operational state, not a replacement for retained
    # business audit records. Stop if receipt persistence is unavailable.
    await run_in_threadpool(store.put, 'latest', record)
    for name, callback, args in operations:
        step = {'operation': name, 'status': 'running'}
        record['steps'].append(step)
        await run_in_threadpool(store.put, 'latest', record)
        try:
            result = await run_in_threadpool(callback, *args)
            step['status'] = 'completed'
            if type(result) is int:
                step['affected_records'] = result
            elif isinstance(result, dict) and result.get('status'):
                step['status'] = result['status']
        except Exception as exc:
            step.update(status='failed', error_type=type(exc).__name__)
        await run_in_threadpool(store.put, 'latest', record)
    record['status'] = 'completed' if all(s['status'] == 'completed' for s in record['steps']) else 'partial'
    record['finished_at'] = now()
    await run_in_threadpool(store.put, 'latest', record)
    return record


def prune_graph(memory):
    if not memory.enabled():
        return {'status': 'disabled'}
    deleted = memory.prune_expired_sessions()
    if deleted is None:
        return {'status': 'unavailable'}
    return deleted
