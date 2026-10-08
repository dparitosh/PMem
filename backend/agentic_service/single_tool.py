"""Run approved mutations through the existing persisted workflow executor."""
import asyncio
from datetime import datetime, timezone


def definition(source, identifier):
    parts = identifier.split(':')
    if len(parts) != 3 or parts[0] != 'single-tool': raise ValueError('Invalid single-tool workflow ID')
    _, agent_id, tool_id = parts
    agent = next((item for item in source['agents'] if item['id'] == agent_id), None)
    tool = next((item for item in source['tools'] if item['id'] == tool_id), None)
    if not agent or not tool or tool_id not in agent.get('tools', []):
        raise ValueError('Tool is not allowlisted for this agent')
    return {'id': identifier, 'name': 'Approved '+agent.get('name', agent_id)+' action',
            'steps': [{'agent_id': agent_id, 'tool_id': tool_id}]}


async def execute(payload, request):
    from fastapi import HTTPException
    from . import router as routes
    from .durable_workflows import execution_mode, enqueue
    if not isinstance(payload.get('wait_for_completion', True), bool):
        raise HTTPException(422, 'wait_for_completion must be a boolean')
    workflow_id = 'single-tool:'+payload['agent_id']+':'+payload['tool_id']
    command = {'workflow_id': workflow_id, 'inputs': payload.get('inputs', {}),
               'approved_by': payload.get('approved_by'), 'approval_token': payload.get('approval_token')}
    mode = execution_mode()
    if mode != 'worker' and payload.get('wait_for_completion', True) is False:
        raise HTTPException(422, 'wait_for_completion=false requires AGENTIC_EXECUTION_MODE=worker')
    if mode == 'worker':
        try: result = await enqueue(command, request)
        except ValueError as exc: raise HTTPException(422, str(exc)) from exc
        if payload.get('wait_for_completion', True) is not True:
            return {**result, 'workflow_run_id': result['run_id'], 'execution_kind': 'workflow',
                    'agent_id': payload['agent_id'], 'tool_id': payload['tool_id']}
        deadline = datetime.fromisoformat(result['deadline_at'])
        while True:
            record = await routes._agent_io(routes.workflow_store.get, result['run_id'])
            if record and record.get('status') not in {'running', 'queued'}:
                result = record
                break
            if datetime.now(timezone.utc) >= deadline:
                raise HTTPException(504, 'Workflow remains incomplete; inspect its retained state before retrying',
                    headers={'X-DEPO-Run-ID': result['run_id'], 'X-DEPO-Run-Kind': 'workflow'})
            await asyncio.sleep(.25)
    else:
        try:
            result = await routes._keep_workflow_running(routes._execute_workflow(command, request))
        except HTTPException as exc:
            exc.headers = {**(exc.headers or {}), 'X-DEPO-Run-Kind': 'workflow'}
            raise
    if result.get('status') != 'completed':
        raise HTTPException(409, 'Workflow did not complete; inspect retained write intent before retrying',
            headers={'X-DEPO-Run-ID': result['run_id'], 'X-DEPO-Run-Kind': 'workflow'})
    return {'agent_id': payload['agent_id'], 'tool_id': payload['tool_id'], 'result': result['traces'][0]['result'],
            'run_id': result['run_id'], 'workflow_run_id': result['run_id'], 'execution_kind': 'workflow',
            'status': 'completed', 'execution_mode': mode, 'telemetry_run_id': result.get('telemetry_run_id')}
