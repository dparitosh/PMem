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
              'node_id', 'import_task_id', 'source_ontology_ids', 'ontology_path', 'qif_ontology_id', 'ap242_ontology_id',
              'run_id', 'product_id', 'product_version', 'artifact_id'}
PLAN = {'id': 'goal.plan', 'description': 'Decompose or revise the goal into evidence-gathering subtasks.',
        'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['subtasks'], 'properties': {
            'subtasks': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 400}}}}}
COMPLETE = {'id': 'goal.complete', 'description': 'Report a model-assisted conclusion supported by completed observation IDs. When citing ontology.consistency.check or ontology.semantic.evidence, supply semantic_conclusion equal to its exact status (unknown for mixed or not_checked statuses). The controller renders the semantic verdict; consistency is not engineering approval.',
            'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['summary', 'evidence_steps'], 'properties': {
                'summary': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
                'semantic_conclusion': {'type': 'string', 'enum': ['consistent', 'inconsistent', 'unknown', 'unsupported']},
                'evidence_steps': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'uniqueItems': True,
                                   'items': {'type': 'string', 'maxLength': 40}}}}}
NEEDS_INPUT = {'id': 'goal.needs_input', 'description': 'Stop and request missing required read inputs; never request credentials or approval.',
    'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['missing_fields'], 'properties': {
        'missing_fields': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'uniqueItems': True,
                           'items': {'type': 'string', 'minLength': 1, 'maxLength': 80}}}}}


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


def verify_read_identity(tool_id, inputs, result, scope=None):
    """Reject a successful HTTP read that returned a different selected record."""
    field = {'pipeline.run.evidence': 'run_id', 'data.catalog.product': 'product_id', 'learning.lessons':'ontology_id'}.get(tool_id)
    if field and (not isinstance(result, dict) or result.get(field) != inputs.get(field)):
        raise ValueError('Owning-service response changed selected record identity')
    if tool_id == 'learning.lessons' and (result.get('import_task_id') != inputs.get('import_task_id') or result.get('advisory_only') is not True):
        raise ValueError('Learning hints changed selected source or evidence role')
    version = (scope or {}).get('product_version')
    if tool_id == 'data.catalog.product' and version:
        versions = result.get('versions')
        matches = [row for row in versions if isinstance(row, dict) and row.get('version') == version] if isinstance(versions, list) else []
        if len(matches) != 1 or matches[0].get('product_id') != inputs.get('product_id'):
            raise ValueError('Owning-service response lacks the selected product version')
        return matches[0]
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
    if isinstance(safe, dict) and 'consistency_verified' in safe and 'artifact_sha256' in safe:
        # Preserve the full verdict and its bindings; classification rows are optional detail.
        keys = ('ontology_id', 'artifact_sha256', 'evidence_id', 'status', 'reason', 'checked_at',
                'consistency_verified', 'deductive_reasoner_executed', 'modeling_coherent',
                'unsatisfiable_class_count', 'unsatisfiable_classes_complete', 'target_checks', 'foundation', 'engine', 'engine_version')
        compact = {key: safe[key] for key in keys if key in safe}
        compact.update(truncated=True, detail_truncated=True, verdict_complete=True,
                       limitation='Classification details omitted; this verdict concerns the retained model only.')
        if len(json.dumps(compact, ensure_ascii=False).encode('utf-8')) <= limit:
            return compact
    # A partial observation is explicitly marked; never pretend it is complete JSON.
    result = {'truncated': True, 'excerpt': '', 'limitation': 'Narrow the read before drawing conclusions.'}
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        result['excerpt'] = text[:middle]
        if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) <= limit: low = middle
        else: high = middle - 1
    result['excerpt'] = text[:low]
    return result


class MissingGoalInput(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__('Required source inputs are missing')


def scratchpad(record, limit=120000):
    """Budget results newest first; never replace durable state with an excerpt."""
    state = {key: protect(record.get(key)) for key in ('goal', 'scope', 'plans', 'decisions', 'max_decisions')}
    state['context'] = bounded(record.get('context', {}), 20000)
    state['observations'] = []
    for item in record['observations']:
        meta = {key: protect(item[key]) for key in ('id', 'tool_id', 'status', 'error_code') if key in item}
        if item.get('message'): meta['message'] = protect(str(item['message'])[:1000])
        if 'inputs' in item: meta['inputs'] = bounded(item['inputs'], 2000)
        if 'result' in item: meta['result'] = {'truncated': True, 'limitation': 'Older evidence omitted from this decision.'}
        state['observations'].append(meta)
    state['omitted_observation_results'] = []
    for index in reversed(range(len(record['observations']))):
        item = record['observations'][index]
        if 'result' not in item: continue
        remaining = limit - len(json.dumps(state, ensure_ascii=False, default=str).encode('utf-8')) - 512
        if remaining < 256:
            state['omitted_observation_results'].append(item['id'])
            continue
        state['observations'][index]['result'] = bounded(item['result'], min(32000, remaining))
        projected = state['observations'][index]['result']
        if isinstance(projected, dict) and projected.get('truncated'):
            state['omitted_observation_results'].append(item['id'])
    return state


def validate_action(record, proposal, tools):
    tool_id, inputs = proposal.get('tool_id'), proposal.get('inputs')
    selected = next((tool for tool in [*tools, PLAN, COMPLETE, NEEDS_INPUT] if tool['id'] == tool_id), None)
    if selected is None or not isinstance(inputs, dict):
        raise ValueError('Goal selected an unavailable read action')
    from .input_contracts import validate
    from .prompt_security import secret_key
    if not tool_id.startswith('goal.'):
        missing = [field for field in selected['input_schema'].get('required', []) if field not in inputs
                   and not record['scope'].get(field) and not record.get('context', {}).get(field) and not secret_key(field)]
        if missing:
            raise MissingGoalInput(missing[:8])
    validate(inputs, selected['input_schema'], selected['input_schema'])
    execution_payload({'inputs': inputs})
    if tool_id == NEEDS_INPUT['id']:
        required = {field for tool in tools for field in tool.get('input_schema', {}).get('required', [])}
        from .prompt_security import secret_key
        if any(field not in required or secret_key(field) or record['scope'].get(field) or record.get('context', {}).get(field)
               for field in inputs['missing_fields']):
            raise ValueError('Request only missing required read fields, never credentials or supplied scope')
        return tool_id, inputs
    if not record.get('plans') and tool_id != PLAN['id']:
        raise ValueError('Decompose the goal before executing a tool')
    ontology_ids = {value for key, value in record['scope'].items()
                    if key in {'ontology_id', 'source_ontology_id', 'target_ontology_id', 'qif_ontology_id', 'ap242_ontology_id'}
                    and isinstance(value, str)}
    ontology_ids.update(value for value in record['scope'].get('source_ontology_ids', []) if isinstance(value, str))
    if tool_id in {'ontology.consistency.check', 'ontology.semantic.evidence'} and not ontology_ids:
        raise MissingGoalInput(['ontology_id'])
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
    from .recommendation_goals import validate_read, completion_evidence
    validate_read(record.get('context', {}), tool_id, inputs)
    if tool_id == PLAN['id'] and len(record['plans']) >= 3:
        raise ValueError('Plan revision limit reached')
    if tool_id == COMPLETE['id']:
        evidence = {item['id'] for item in record['observations'] if item['status'] == 'completed'
                    and item.get('result') and not (isinstance(item['result'], dict) and item['result'].get('truncated')
                        and not item['result'].get('verdict_complete'))}
        if not set(inputs['evidence_steps']).issubset(evidence):
            raise ValueError('Completion must cite completed, untruncated observations')
        completion_evidence(record.get('context', {}), record['observations'], inputs['evidence_steps'])
        cited = [item for item in record['observations'] if item['id'] in inputs['evidence_steps']]
        if cited and all(item['tool_id'] == 'learning.lessons' for item in cited):
            raise ValueError('Advisory lessons alone cannot establish a business conclusion; read current source evidence')
        semantic_completion(record, inputs)
    return tool_id, inputs


def semantic_completion(record, inputs):
    from backend.depo_platform.semantic_support import assessment
    rows = []
    for item in record['observations']:
        if item.get('id') not in inputs['evidence_steps'] or item.get('tool_id') not in {'ontology.consistency.check', 'ontology.semantic.evidence'}:
            continue
        if not isinstance(item.get('result'), dict):
            raise ValueError('Invalid semantic evidence contract')
        if item.get('inputs', {}).get('ontology_id') and item['result'].get('ontology_id') != item['inputs']['ontology_id']:
            raise ValueError('Semantic evidence changed the selected ontology')
        rows.append(assessment(item['result']))
    if not rows: return {}
    statuses = {row.get('status') if row.get('status') in {'consistent', 'inconsistent', 'unsupported'} else 'unknown' for row in rows}
    conclusion = next(iter(statuses)) if len(statuses) == 1 else 'unknown'
    if inputs.get('semantic_conclusion') != conclusion:
        raise ValueError('Report the exact semantic evidence disposition, including unknown or conflicting results')
    # Never let free-form model prose overwrite the typed disposition.
    return {'semantic_assessments': rows, 'summary': '\n'.join(
        f"{row.get('ontology_id', 'Selected model')}: {row.get('status', 'unknown')}. {row['business_summary']}" for row in rows)}


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
                available = [PLAN, NEEDS_INPUT] if not record['plans'] else [*tools, COMPLETE, NEEDS_INPUT] + ([PLAN] if len(record['plans']) < 3 else [])
                proposal = await propose(available, scratchpad(record))
                try:
                    tool_id, inputs = validate_action(record, proposal, tools)
                except MissingGoalInput as exc:
                    record.update(status='needs_input', missing_fields=exc.fields,
                                  message='Select or supply the missing source fields, then start a new investigation.', completed_at=now())
                    await persist()
                    return record
                except ValueError:
                    record['observations'].append({'id': f"observation-{record['decisions']}", 'status': 'held',
                        'error_code': 'invalid_plan_action', 'message': 'Choose a valid action, preserve scope, and do not repeat attempted reads.'})
                    await persist()
                    continue
                if tool_id == PLAN['id']:
                    record['plans'].append({'revision': len(record['plans']) + 1, 'subtasks': inputs['subtasks'], 'created_at': now()})
                    await persist()
                    continue
                if tool_id == NEEDS_INPUT['id']:
                    record.update(status='needs_input', missing_fields=inputs['missing_fields'],
                                  message='Select or supply the missing source fields, then start a new investigation.', completed_at=now())
                    await persist()
                    return record
                if tool_id == COMPLETE['id']:
                    from .recommendation_goals import completion_evidence
                    binding = completion_evidence(record.get('context', {}), record['observations'], inputs['evidence_steps'])
                    record.update(status='completed', result={**inputs, **(binding or {}), **semantic_completion(record, inputs),
                        'semantic_entailment_verified': False, 'interpretation': 'model_assisted_advisory'}, completed_at=now())
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
                    result = verify_read_identity(tool_id, inputs, result, record.get('scope'))
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
        if failure_status(exc) == 'context_budget_exceeded':
            record['message'] = 'Narrow the evidence or tool selection to fit the verified model context. Retained results remain available.'
    await persist()
    return record
