"""PostgreSQL-backed workflow execution; persist grants, never caller credentials."""
import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from .recovery import execution_payload, fingerprint, prepare_recovery


def execution_mode():
    value = os.getenv('AGENTIC_EXECUTION_MODE', 'process').strip().lower()
    if value not in {'process', 'worker'}:
        raise ValueError('AGENTIC_EXECUTION_MODE must be process or worker')
    return value


def credential_snapshot():
    # Only fingerprints are persisted; worker obtains current keys from its environment.
    names = ('GRAPH_READ_TOKEN', 'AGENTIC_APPROVAL_TOKEN', 'ONTOLOGY_APPROVAL_TOKEN',
             'INGESTION_WRITE_TOKEN', 'DATA_PRODUCT_APPROVAL_TOKEN', 'DATA_JOB_EXECUTION_TOKEN', 'GRAPH_PUBLICATION_TOKEN')
    return {name: hashlib.sha256(os.environ[name].strip().encode()).hexdigest()
            for name in names if os.getenv(name, '').strip()}


def transport_snapshot():
    names = ('AUTH_MODE','AGENTIC_SERVICE_URL','GRAPH_SERVICE_URL','ONTOLOGY_SERVICE_URL',
             'INGESTION_SERVICE_URL','OSLC_SERVICE_URL','QIF_SERVICE_URL','DATA_CATALOG_URL',
             'DATA_PRODUCT_SERVICE_URL','CEIM_SERVICE_URL','DATA_PIPELINE_SERVICE_URL','DEPO_API_GATEWAY_URL')
    return fingerprint({name:os.getenv(name,'').strip() for name in names})


def clean_command(payload):
    command = execution_payload(payload)
    def check(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower().endswith(('_token', '_api_key', '_password', '_secret')) or key.lower() in {'headers', 'credentials'}:
                    raise ValueError('Durable workflow inputs cannot contain credentials or arbitrary headers')
                check(item)
        elif isinstance(value, list):
            for item in value: check(item)
    check(command)
    return command


async def enqueue(payload, request, recovery=None):
    from fastapi import HTTPException
    from backend.depo_platform.authorization import approval_identity, graph_read_identity
    from backend.depo_platform.network import bounded_timeout_seconds
    from . import router as routes, sessions
    if os.getenv('AUTH_MODE', 'token').lower() != 'token':
        raise HTTPException(503, 'Durable worker mode requires token service identities; Entra delegation is not persisted')
    plan = routes.workflow_plan(payload)
    actor = approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN') if any(step['requires_approval'] for step in plan['steps']) else graph_read_identity(request)
    workflow = routes.catalog.item('workflows', payload['workflow_id'])
    command = clean_command(payload)
    requested = command.get('step_inputs')
    if requested is not None and (not isinstance(requested,list) or len(requested) != len(workflow['steps']) or any(not isinstance(item,dict) for item in requested)):
        raise ValueError('step_inputs must contain one object for each workflow step')
    if not isinstance(command.get('inputs',{}),dict): raise ValueError('inputs must be an object')
    commands = [{**step,'inputs':{**(requested[index] if requested is not None else command.get('inputs',{})),**step.get('input_bindings',{})}} for index,step in enumerate(workflow['steps'])]
    await routes._preflight_tools(commands, request, deferred=True)
    credentials = credential_snapshot()
    if 'GRAPH_READ_TOKEN' not in credentials or (any(step['requires_approval'] for step in plan['steps']) and 'AGENTIC_APPROVAL_TOKEN' not in credentials):
        raise HTTPException(503,'Configure current server read and approval profiles before queueing workflows')
    now = datetime.now(timezone.utc)
    definition = {'workflow':workflow,'steps':plan['steps']}
    record = {**(recovery or {}), 'run_id': recovery['run_id'] if recovery else 'run-'+str(uuid4()),
              'owner': recovery['owner'] if recovery else sessions.owner(request,actor),
              'workflow_id':workflow['id'],'status':'queued','execution_mode':'worker',
              'execution_id':uuid4().hex,'execution_payload':command,'workflow_definition':definition,
              'workflow_digest':fingerprint(definition),'approved_actor':actor,'credential_fingerprints':credentials,
              'transport_fingerprint':transport_snapshot(),
              'started_at': recovery['started_at'] if recovery else now.isoformat(), 'updated_at':now.isoformat(),
              'deadline_at':recovery['deadline_at'] if recovery else (now+timedelta(seconds=bounded_timeout_seconds('AGENTIC_RUN_TIMEOUT_SECONDS',default=300))).isoformat(),
              'traces': recovery['traces'] if recovery else []}
    record.pop('_expected_record',None)
    if recovery:
        if not await routes._agent_io(routes.workflow_store.compare_and_put,record['run_id'],recovery['_expected_record'],record):
            raise HTTPException(409,'Recovery was claimed by another executor')
    else:
        await routes._agent_io(routes.workflow_store.create,record['run_id'],record)
    return {'run_id':record['run_id'],'status':'queued','execution_mode':'worker','deadline_at':record['deadline_at']}


async def execute_candidate(record):
    from starlette.requests import Request
    from backend.depo_platform.authorization import require_active_token
    from backend.depo_platform.credentials import uses_postgres, verify_key
    from . import router as routes
    from .workflow_control import last_activity
    run_id = record['run_id']
    if record.get('execution_mode') != 'worker' or record.get('status') not in {'queued','running','interrupted'}: return
    if record.get('reconciliation_required') or (record.get('pending_step') or {}).get('mutates') or record.get('compensations'): return
    if datetime.now(timezone.utc) >= datetime.fromisoformat(record['deadline_at']):
        await routes._agent_io(routes.workflow_store.compare_and_put,run_id,record,{**record,'status':'timed_out','error_type':'QueueDeadlineElapsed','updated_at':datetime.now(timezone.utc).isoformat()})
        return
    try:
        definition = {'workflow':routes.catalog.item('workflows',record['workflow_id']), 'steps':routes.workflow_plan({'workflow_id':record['workflow_id']})['steps']}
    except (KeyError,ValueError):
        await routes._agent_io(routes.workflow_store.compare_and_put,run_id,record,{**record,'status':'failed','error_type':'WorkerDefinitionChanged'})
        return
    if record['status'] in {'running','interrupted'}:
        heartbeat = await routes._agent_io(routes.workflow_heartbeats.get,f"{run_id}:{record.get('execution_id','')}")
        try: recovery = prepare_recovery(record,definition,activity_at=last_activity(record,heartbeat))
        except ValueError: return  # Active, expired or uncertain mutations are never replayed.
    else: recovery = dict(record)
    try:
        if record.get('credential_fingerprints') != credential_snapshot() or record.get('workflow_digest') != fingerprint(definition) or record.get('transport_fingerprint') != transport_snapshot():
            raise ValueError('Authorization or tool contracts changed')
        for name in record['credential_fingerprints']:
            require_active_token(name)
            if uses_postgres(): verify_key(name,os.environ[name].strip())
    except Exception:
        await routes._agent_io(routes.workflow_store.compare_and_put,run_id,record,{**record,'status':'failed','error_type':'WorkerAuthorizationChanged'})
        return
    claimed = {**record,'status':'running','execution_id':uuid4().hex,'updated_at':datetime.now(timezone.utc).isoformat()}
    if not await routes._agent_io(routes.workflow_store.compare_and_put,run_id,record,claimed): return
    recovery.update(_expected_record=claimed,execution_id=claimed['execution_id'])
    request = Request({'type':'http','method':'POST','path':'/api/v1/workflow-runs','headers':[(b'authorization',('Bearer '+os.environ['GRAPH_READ_TOKEN'].strip()).encode())],'client':('127.0.0.1',0)})
    request.state.request_id = record.get('request_id','')
    payload = {**record['execution_payload'],'approved_by':record['approved_actor'],'approval_token':os.getenv('AGENTIC_APPROVAL_TOKEN','')}
    await routes._execute_workflow(payload,request,recovery=recovery)


async def worker_loop():
    import logging
    from backend.mesh_store import PostgresRegistry
    from . import router as routes
    from .workflow_control import execution_heartbeat
    status_store = PostgresRegistry('agentic_workflow_workers')
    async with execution_heartbeat(status_store,'workflow-worker-'+uuid4().hex,{'execution_mode':execution_mode()}):
        await _worker_loop(routes,logging)


async def _worker_loop(routes, logging):
    capacity = int(os.getenv('AGENTIC_WORKER_CONCURRENCY','4'))
    if not 1 <= capacity <= 16: raise ValueError('AGENTIC_WORKER_CONCURRENCY must be between 1 and 16')
    active = {}
    try:
        while True:
            for run_id, task in list(active.items()):
                if task.done():
                    active.pop(run_id)
                    if not task.cancelled() and task.exception(): logging.getLogger(__name__).warning('Workflow worker execution failed: %s',type(task.exception()).__name__)
            try:
                if execution_mode() == 'worker' and len(active) < capacity:
                    stale = (datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
                    candidates = await routes._agent_io(routes.workflow_store.execution_candidates,capacity-len(active),stale,'agentic_workflow_heartbeats')
                    for record in candidates:
                        if record['run_id'] not in active:
                            active[record['run_id']] = asyncio.create_task(execute_candidate(record))
            except asyncio.CancelledError: raise
            except Exception as failure: logging.getLogger(__name__).warning('Workflow worker database unavailable: %s',type(failure).__name__)
            await asyncio.sleep(2)
    finally:
        for task in active.values(): task.cancel()
        await asyncio.gather(*active.values(),return_exceptions=True)
