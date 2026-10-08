"""Cooperative workflow controls. They never interrupt or undo an in-flight tool."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone


@asynccontextmanager
async def execution_heartbeat(store, key, metadata=None):
    async def pulse():
        while True:
            try:
                await asyncio.to_thread(store.put, key, {**(metadata or {}), 'updated_at': datetime.now(timezone.utc).isoformat()})
            except Exception:
                logging.getLogger(__name__).warning('Workflow heartbeat persistence failed')
            await asyncio.sleep(10)
    task = asyncio.create_task(pulse())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def last_activity(record, heartbeat):
    return max(record['updated_at'], (heartbeat or {}).get('updated_at', record['updated_at']))


class WorkflowCancelled(Exception):
    pass


async def checkpoint(store, run_id):
    while True:
        control = await asyncio.to_thread(store.get, run_id) or {}
        action = control.get("action", "resume")
        if control and not control.get('acknowledged_at'):
            acknowledged = {**control, 'acknowledged_at': datetime.now(timezone.utc).isoformat(), 'effective_action': action}
            if not await asyncio.to_thread(store.compare_and_put, run_id, control, acknowledged):
                continue  # A newer control request must be read before dispatch.
        if action == "cancel":
            raise WorkflowCancelled("Workflow cancelled at a tool boundary")
        if action != "pause":
            return
        await asyncio.sleep(0.5)


def workflow_snapshot(record, control=None, heartbeat=None):
    """One public state projection for UI control eligibility and heartbeat age."""
    control = control or {}
    now = datetime.now(timezone.utc)
    deadline_open = now < datetime.fromisoformat(record['deadline_at'])
    activity = last_activity(record, heartbeat)
    stale = (now - datetime.fromisoformat(activity)).total_seconds() >= 60
    mutates = bool((record.get('pending_step') or {}).get('mutates'))
    status = record.get('status')
    if status == 'running' and (not deadline_open or stale):
        status = 'interrupted'
    if status == 'queued' and not deadline_open: status = 'timed_out'
    action = control.get('action', 'resume')
    actions = []
    if status in {'running','queued'} and deadline_open and action != 'cancel':
        actions = ['resume', 'cancel'] if action == 'pause' else ['pause', 'cancel']
    state = status
    if status in {'running','queued'}:
        if control.get('acknowledged_at') and control.get('effective_action') == 'pause' and action == 'pause':
            state = 'paused'
        elif action in {'pause', 'cancel'}:
            state = action + '_requested'
    reconciliation_required = bool(record.get('reconciliation_required')) or (status == 'interrupted' and mutates)
    return {**{key: value for key, value in record.items() if key not in {'owner', 'execution_payload', 'execution_id', 'credential_fingerprints'}},
            'status': status, 'execution_state': state, 'control': control,
            'last_activity_at': activity, 'executor_active': record.get('status') == 'running' and not stale,
            'allowed_actions': actions, 'reconciliation_required': reconciliation_required,
            'reconcile_allowed': mutates and (record.get('status') in {'failed', 'interrupted', 'timed_out'} or (record.get('status') == 'running' and stale)),
            'executor_stop_verification_required': record.get('status') == 'running',
            'recover_allowed': deadline_open and status in {'failed', 'interrupted', 'recoverable'} and not mutates and not reconciliation_required and not record.get('compensations'),
            'execution_mode': record.get('execution_mode','process-task'), 'restart_recovery': 'automatic-read-only; uncertain-writes-require-reconciliation' if record.get('execution_mode') == 'worker' else 'supervised', 'completed_writes': 'retained'}
