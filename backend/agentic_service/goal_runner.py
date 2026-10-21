"""Persisted, bounded read-only planning over registered tools.

The model proposes; the controller validates scope, executes and retains each
observation before asking for a revised action. Writes remain workflow-owned.
"""
import asyncio
import copy
import hashlib
import json
import httpx
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from .prompt_security import protect
from .recovery import execution_payload, fingerprint

SCOPE_KEYS = {'ontology_id', 'ontology_prefix', 'source_ontology_id', 'target_ontology_id',
              'import_task_id', 'source_ontology_ids', 'ontology_path', 'qif_ontology_id', 'ap242_ontology_id'}
PLAN = {'id': 'goal.plan', 'description': 'Decompose or revise the goal into evidence-gathering subtasks.',
        'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['subtasks'], 'properties': {
            'subtasks': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 400}}}}}
COMPLETE = {'id': 'goal.complete', 'description': 'Report a model-assisted conclusion supported by completed observation IDs.',
            'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['summary', 'evidence_steps'], 'properties': {
                'summary': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
                'evidence_steps': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'uniqueItems': True,
                                   'items': {'type': 'string', 'maxLength': 40}}}}}


def now():
    return datetime.now(timezone.utc).isoformat()


def selected_scope(context):
    result = {}
    for key in SCOPE_KEYS:
        value = context.get(key)
        if value is None or value == '':
            continue
        if key == 'source_ontology_ids':
            if not isinstance(value, list) or not 1 <= len(value) <= 10 or any(not isinstance(item, str) or not 1 <= len(item) <= 256 for item in value):
                raise ValueError('Invalid selected ontology IDs')
        elif not isinstance(value, str) or len(value) > 2048:
            raise ValueError('Invalid selected source scope')
        result[key] = value
    return result


def read_tools(agent, tools, plan):
    return [copy.deepcopy(tool) for tool in tools if tool['id'] in agent.get('tools', [])
            and not tool['id'].startswith('goal.') and tool.get('mutates') is False and tool.get('input_kind') != 'multipart'
            and not plan({'agent_id': agent['id'], 'tool_id': tool['id']})['requires_approval']]


def contract(agent, tools):
    return fingerprint({'agent': agent, 'tools': tools,
                        'controller': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def bounded(value, limit=32000):
    safe = protect(value)
    text = json.dumps(safe, default=str, ensure_ascii=False)
    if len(text.encode('utf-8')) <= limit:
        return safe
    # A partial observation is explicitly marked; never pretend it is complete JSON.
    return {'truncated': True, 'excerpt': text.encode('utf-8')[:limit].decode('utf-8', errors='ignore'),
            'limitation': 'Result exceeds the goal evidence budget. Narrow the read before drawing conclusions.'}


def validate_action(record, proposal, tools):
    tool_id, inputs = proposal.get('tool_id'), proposal.get('inputs')
    selected = next((tool for tool in [*tools, PLAN, COMPLETE] if tool['id'] == tool_id), None)
    if selected is None or not isinstance(inputs, dict):
        raise ValueError('Goal selected an unavailable read action')
    from .input_contracts import validate
    validate(inputs, selected['input_schema'], selected['input_schema'])
    execution_payload({'inputs': inputs})
    if not record.get('plans') and tool_id != PLAN['id']:
        raise ValueError('Decompose the goal before executing a tool')
    ontology_ids = {value for key, value in record['scope'].items()
                    if key in {'ontology_id', 'source_ontology_id', 'target_ontology_id', 'qif_ontology_id', 'ap242_ontology_id'}
                    and isinstance(value, str)}
    ontology_ids.update(value for value in record['scope'].get('source_ontology_ids', []) if isinstance(value, str))
    def scope(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in record['scope'] and child != record['scope'][key]:
                    raise ValueError('Goal action changed the selected source scope')
                if ontology_ids and key in {'ontology_id', 'source_ontology_id', 'target_ontology_id', 'qif_ontology_id', 'ap242_ontology_id'} and (not isinstance(child, str) or child not in ontology_ids):
                    raise ValueError('Goal action selected an ontology outside the supplied sources')
                scope(child)
        elif isinstance(value, list):
            for child in value: scope(child)
    scope(inputs)
    if tool_id not in {PLAN['id'], COMPLETE['id']}:
        # Every pinned scope field required/supported by this operation must remain explicit.
        for key, value in record['scope'].items():
            if key in selected.get('input_schema', {}).get('properties', {}) and inputs.get(key) != value:
                raise ValueError('Goal action omitted the selected source scope')
        if ontology_ids and 'ontology_id' in selected.get('input_schema', {}).get('properties', {}) and inputs.get('ontology_id') not in ontology_ids:
            raise ValueError('Goal action requires an explicitly selected ontology')
        action_key = fingerprint({'tool_id': tool_id, 'inputs': protect(inputs)})
        if any(item.get('action_key') == action_key for item in record['observations']):
            raise ValueError('This exact read was already attempted; revise the plan or inputs')
    if tool_id == PLAN['id'] and len(record['plans']) >= 3:
        raise ValueError('Plan revision limit reached')
    if tool_id == COMPLETE['id']:
        evidence = {item['id'] for item in record['observations'] if item['status'] == 'completed'
                    and item.get('result') and not (isinstance(item['result'], dict) and item['result'].get('truncated'))}
        if not set(inputs['evidence_steps']).issubset(evidence):
            raise ValueError('Completion must cite completed, untruncated observations')
    return tool_id, inputs


async def drive(record, *, propose, dispatch, save, tools):
    """Callbacks keep persistence/transport outside the independently testable loop."""
    async def persist():
        record['updated_at'] = now()
        await save(copy.deepcopy(record))

    remaining = (datetime.fromisoformat(record['deadline_at']) - datetime.now(timezone.utc)).total_seconds()
    try:
        if remaining <= 0:
            raise TimeoutError()
        async with asyncio.timeout(remaining):
            while record['decisions'] < record['max_decisions']:
                record['decisions'] += 1
                await persist()
                available = [PLAN] if not record['plans'] else [*tools, COMPLETE] + ([PLAN] if len(record['plans']) < 3 else [])
                proposal = await propose(available, bounded({k: record[k] for k in
                    ('goal', 'context', 'plans', 'observations', 'decisions', 'max_decisions')}, limit=120000))
                try:
                    tool_id, inputs = validate_action(record, proposal, tools)
                except ValueError:
                    record['observations'].append({'id': f"observation-{record['decisions']}", 'status': 'held',
                        'error_code': 'invalid_plan_action', 'message': 'Choose a valid action, preserve scope, and do not repeat attempted reads.'})
                    await persist()
                    continue
                if tool_id == PLAN['id']:
                    record['plans'].append({'revision': len(record['plans']) + 1, 'subtasks': inputs['subtasks'], 'created_at': now()})
                    await persist()
                    continue
                if tool_id == COMPLETE['id']:
                    record.update(status='completed', result=inputs, completed_at=now())
                    await persist()
                    return record
                observation = {'id': f"observation-{record['decisions']}", 'tool_id': tool_id,
                               'action_key': fingerprint({'tool_id': tool_id, 'inputs': protect(inputs)}),
                               'inputs': protect(inputs), 'status': 'dispatching', 'started_at': now()}
                record['observations'].append(observation)
                # Persist write-ahead observation even though all dispatched tools are read-only.
                await persist()
                try:
                    result = await dispatch(tool_id, inputs)
                    if isinstance(result, dict) and result.get('status') in {'failed', 'error', 'timed_out', 'cancelled'}:
                        observation.update(status='failed', error_code='read_result_failed', result=bounded(result), finished_at=now())
                    else:
                        observation.update(status='completed', result=bounded(result), finished_at=now())
                except HTTPException as exc:
                    from .workflow_errors import workflow_error
                    observation.update(status='failed', **workflow_error(exc, tool_id), finished_at=now())
                    if exc.status_code in {401, 403}:
                        record.update(status='blocked', error_code='access_rejected')
                        await persist()
                        return record
                except (TimeoutError, httpx.HTTPError):
                    observation.update(status='failed', error_code='read_transport_unavailable',
                                       message='The read timed out or its connection failed. Choose a compatible read or revise its inputs.',
                                       finished_at=now())
                await persist()
            record.update(status='budget_exhausted', error_code='goal_decision_limit')
    except asyncio.CancelledError:
        record.update(status='interrupted', error_code='executor_stopped')
        await persist()
        raise
    except TimeoutError:
        record.update(status='timed_out', error_code='goal_deadline_elapsed')
    except Exception as exc:
        from .local_llm import failure_status
        record.update(status='failed', error_code='goal_' + failure_status(exc))
    await persist()
    return record
