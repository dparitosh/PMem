"""Catalog and bounded execution for independently extensible agents/tools."""
from __future__ import annotations

from backend.depo_platform.request_bodies import ApprovalBody, CompensationBody, DtManifestBody, DtRunBody, ToolRunBody, ToolSuggestionBody, WorkflowRunBody

from backend.depo_platform.request_bodies import AgentPlanBody, OntologyAgentBody, OslcRetrievalBody, ReconcileWorkflowBody, SemanticWorkflowBody, WorkflowControlBody, WorkflowPlanBody
import asyncio, base64, binascii, json, os, time
import logging
from string import Formatter
from urllib.parse import quote
from datetime import timedelta
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request, Depends
from .workflow_errors import workflow_error
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from backend.mesh_store import PostgresRegistry
from .workflow_control import checkpoint as workflow_checkpoint, WorkflowCancelled, execution_heartbeat, last_activity
from backend.depo_platform.network import bounded_timeout_seconds
from .companion import companion
from .chat_request import ChatRequest
from .stream_errors import stream_failure
from .transport_auth import APPROVAL_TOKENS, downstream_headers, downstream_inputs, tool_retry_allowed
from .oslc_graph_rag import oslc_graph_rag
from .dt_requirements_adapter import assess_manifest
from .dt_gateway import execute_current_plan
from .dt_bindings import extend_catalog, capabilities as dt_capabilities
from .telemetry import telemetry
from . import sessions
from .response_limits import read_bounded_response
from .recommendations import recommendations
from backend.Services.agent_memory_service import AgentMemoryService

logger = logging.getLogger(__name__)


def _finish_observation(*args, **kwargs):
    try:
        return telemetry.finish(*args, **kwargs)
    except Exception:
        logger.exception('Unable to persist terminal agent telemetry')


def _tool_span(*args, **kwargs):
    try:
        return telemetry.tool_span(*args, **kwargs)
    except Exception:
        logger.exception('Unable to persist agent tool span')

async def _agent_io(callback, /, *args, **kwargs):
    """Offload blocking work without consuming the callback's keyword arguments."""
    return await asyncio.to_thread(callback, *args, **kwargs)


router = APIRouter(prefix="/api/v1", tags=["agentic-control-plane"])

class Catalog:
    def __init__(self) -> None:
        configured = os.getenv("AGENTIC_CATALOG_PATH", "")
        self.path = Path(configured) if configured else Path(__file__).with_name("catalog.json")
    def read(self) -> dict[str, Any]:
        from .catalog_loader import load_catalog
        return load_catalog(self.path)
    def item(self, kind: str, identifier: str) -> dict[str, Any]:
        if kind == 'workflows' and identifier.startswith('single-tool:'):
            from .single_tool import definition
            return definition(self.read(), identifier)
        for value in self.read()[kind]:
            if value.get("id") == identifier: return value
        raise ValueError(f"Unknown {kind[:-1]}: {identifier}")

catalog = Catalog()
workflow_store = PostgresRegistry("agentic_workflow_runs")
workflow_controls = PostgresRegistry("agentic_workflow_controls")
workflow_heartbeats = PostgresRegistry('agentic_workflow_heartbeats')
_active_workflow_tasks = set()


async def _keep_workflow_running(operation, accepted=None):
    """A disconnected browser must not cancel an already authorized workflow."""
    task = asyncio.create_task(operation)
    _active_workflow_tasks.add(task)
    def finished(value):
        _active_workflow_tasks.discard(value)
        if not value.cancelled():
            failure = value.exception()
            if failure is not None:
                logger.warning('Workflow task finished with %s; inspect retained run state', type(failure).__name__)
    task.add_done_callback(finished)
    if accepted is not None:
        await asyncio.wait({task, accepted}, return_when=asyncio.FIRST_COMPLETED)
        if accepted.done():
            return accepted.result()
        accepted.cancel()
    return await asyncio.shield(task)
dt_run_store = PostgresRegistry("dt_agent_runs")
companion_job_store = PostgresRegistry("agentic_companion_jobs")
_services = {"agentic": "AGENTIC_SERVICE_URL", "ontology": "ONTOLOGY_SERVICE_URL", "graph": "GRAPH_SERVICE_URL", "ingestion": "INGESTION_SERVICE_URL", "oslc": "OSLC_SERVICE_URL", "qif": "QIF_SERVICE_URL", "catalog": "DATA_CATALOG_URL", "data_products": "DATA_PRODUCT_SERVICE_URL", "ceim": "CEIM_SERVICE_URL", "data_pipeline": "DATA_PIPELINE_SERVICE_URL"}

def _base(service: str) -> str:
    key = _services.get(service)
    value = os.getenv(key or "", "").rstrip("/") if key else ""
    if not value: raise ValueError(f"Service endpoint is not configured for {service}")
    return value

def _render(path: str, values: dict[str, Any]) -> str:
    result = []
    for literal, field, spec, conversion in Formatter().parse(path):
        result.append(literal)
        if field is None:
            continue
        if spec or conversion or not field.isidentifier():
            raise ValueError('Unsupported tool path placeholder')
        if field not in values:
            raise ValueError(f'Missing path parameter: {field}')
        value = str(values[field])
        if (not value or value in {'.', '..'} or any(c in value for c in '/\\%?#')
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError(f'Invalid path parameter: {field}')
        result.append(quote(value, safe=''))
    return ''.join(result)

@router.get("/agents")
def agents() -> dict:
    from .agent_usage import describe
    return {"agents": describe(catalog.read())}


@router.get('/agent-architecture', dependencies=[Depends(graph_read_identity)])
def agent_architecture() -> dict:
    from .agent_usage import architecture
    return architecture(catalog.read())
@router.get("/tools")
def tools() -> dict: return {"tools": catalog.read()["tools"]}
@router.get("/mcp-servers")
def mcp_servers() -> dict: return {"mcp_servers": catalog.read()["mcp_servers"]}
@router.get("/workflows")
def workflows() -> dict: return {"workflows": catalog.read()["workflows"]}


@router.post("/integrations/dt-requirements-design/compatibility")
def dt_requirements_design_compatibility(payload: DtManifestBody) -> dict:
    """Check an external DT Requirements Design manifest against PMem tools."""
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=422, detail="manifest must be an object")
    return assess_manifest(manifest, catalog.read())


@router.get("/integrations/dt-requirements-design/capabilities")
def dt_capability_bindings() -> dict:
    return dt_capabilities()


@router.post("/integrations/dt-requirements-design/runs")
async def dt_run(payload: DtRunBody, request: Request) -> dict:
    actor = approval_identity(request, payload, token_env="AGENTIC_APPROVAL_TOKEN")
    if os.getenv('DT_AGENT_ENABLED', 'false').lower() != 'true':
        raise HTTPException(503, 'DT integration is disabled; configure and enable DT_AGENT_ENABLED')
    if payload.get("execution_scope") != "current_plan" or payload.get("workflow_id"):
        raise HTTPException(422, "DT supports only explicit execution_scope=current_plan, not workflow selection")
    run_id = str(uuid4())
    record = {"run_id": run_id, "status": "dispatching", "approved_by": actor,
              "execution_scope": "current_plan", "started_at": _now(),
              "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=65)).isoformat(),
              "reconciliation_required": True}
    await _agent_io(dt_run_store.put, run_id, record)
    try:
        async with asyncio.timeout(60):
            record["result"] = await execute_current_plan(
                str(payload.get("query") or ""), str(payload.get("email") or ""), run_id)
        # A returned response may request human input; it is not release approval.
        record["status"] = "response_received"
    except ValueError:
        record["status"] = "rejected"
        record["error"] = "Invalid gateway configuration, input or upstream application response"
    except httpx.HTTPError:
        record["status"] = "dispatch_uncertain"
        record["error"] = "Gateway request failed; inspect DT before retrying"
    except BaseException as exc:
        record.update(status='dispatch_uncertain', error_type=type(exc).__name__, finished_at=_now())
        try:
            await _agent_io(dt_run_store.put, run_id, record)
        except Exception:
            logger.exception('Unable to persist interrupted DT run')
        if isinstance(exc, asyncio.CancelledError) or not isinstance(exc, Exception):
            raise
        raise HTTPException(503, 'DT dispatch outcome uncertain; reconcile before retrying', headers={'X-DEPO-Run-ID': run_id}) from exc
    record["finished_at"] = _now()
    try:
        return await _agent_io(dt_run_store.put, run_id, record)
    except Exception as exc:
        raise HTTPException(503, 'DT terminal state unavailable; reconcile before retrying', headers={'X-DEPO-Run-ID': run_id}) from exc


@router.get("/integrations/dt-requirements-design/runs/{run_id}")
def dt_run_status(run_id: str, request: Request) -> dict:
    from backend.depo_platform.authorization import service_write_identity
    service_write_identity(request, token_env="AGENTIC_APPROVAL_TOKEN", default_actor="dt-agent")
    record = dt_run_store.get(run_id)
    if not record:
        raise HTTPException(404, "DT run not found")
    if record.get('status') == 'dispatching' and record.get('deadline_at') and datetime.now(timezone.utc) >= datetime.fromisoformat(record['deadline_at']):
        return {**record, 'status': 'dispatch_uncertain', 'reconciliation_required': True, 'state_source': 'deadline_projection'}
    return record


@router.post("/oslc/graph-rag", dependencies=[Depends(graph_read_identity)])
async def oslc_graph_rag_route(payload: OslcRetrievalBody) -> dict:
    """OSLC-governed, read-only retrieval for agent context."""
    if os.getenv('OSLC_REMOTE_ENABLED', 'false').lower() != 'true':
        raise HTTPException(503, 'Remote OSLC integration is disabled; configure and enable OSLC_REMOTE_ENABLED')
    try:
        return await oslc_graph_rag.retrieve(
            str(payload.get("query") or ""),
            str(payload.get("resource_type") or "resources"),
            payload.get("limit", 10),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/workflows/options")
def workflow_options() -> dict:
    """Retain the SPA's semantic-workflow picker on the control-plane API."""
    from backend.Services.workflow_registry import get_workflow_options
    return {"workflows": get_workflow_options()}


@router.post("/workflows/execute", dependencies=[Depends(graph_read_identity)])
def execute_semantic_workflow(payload: SemanticWorkflowBody) -> dict:
    """Execute a governed semantic workflow without routing through the legacy monolith."""
    workflow_id = str(payload.get("workflow_id") or "").strip()
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id is required")
    try:
        from backend.Services.semantic_workflow_service import SemanticWorkflowService
        return SemanticWorkflowService.execute(workflow_id, dict(payload.get("payload") or {}))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail='Semantic workflow dependency is unavailable; check ontology catalog and service logs') from exc


@router.post("/ontology-agents/orchestrate", dependencies=[Depends(graph_read_identity)])
def orchestrate_ontology_agents(payload: OntologyAgentBody) -> dict:
    """Run read-only ontology intake/review/Bridge planning agents."""
    from .ontology_orchestrator import orchestrate
    return _ontology_agent_call(orchestrate, payload)


def _ontology_agent_call(operation, payload: dict[str, Any]) -> dict:
    observation, started = telemetry.start(operation='ontology_agent:' + operation.__name__)
    try:
        result = operation(payload)
        _finish_observation(observation, started, status='completed')
        return {**result, 'run_id': observation['run_id'], 'telemetry_run_id': observation['run_id']}
    except ValueError as exc:
        _finish_observation(observation, started, status='failed', error_type=type(exc).__name__)
        raise HTTPException(status_code=422, detail=str(exc), headers={'X-DEPO-Run-ID': observation['run_id']}) from exc
    except Exception as exc:
        _finish_observation(observation, started, status='failed', error_type=type(exc).__name__)
        raise HTTPException(status_code=503, detail="Ontology agent dependency failed; inspect service logs using the run ID", headers={'X-DEPO-Run-ID': observation['run_id']}) from exc


@router.post("/ontology-agents/intake", dependencies=[Depends(graph_read_identity)])
def ontology_agent_intake(payload: OntologyAgentBody) -> dict:
    from .ontology_orchestrator import intake
    return _ontology_agent_call(intake, payload)


@router.post("/ontology-agents/review", dependencies=[Depends(graph_read_identity)])
def ontology_agent_review(payload: OntologyAgentBody) -> dict:
    from .ontology_orchestrator import structure_review
    return _ontology_agent_call(structure_review, payload)


@router.post("/ontology-agents/bridge-plan", dependencies=[Depends(graph_read_identity)])
def ontology_agent_bridge_plan(payload: OntologyAgentBody) -> dict:
    from .ontology_orchestrator import bridge_plan
    return _ontology_agent_call(bridge_plan, payload)


_COMPANION_PROMPTS = [
    "Find ontology resources matching product",
    "Find ontology resources matching requirement",
    "Find ontology resources matching measurement",
]


@router.get("/chat/sample-queries")
def companion_sample_queries() -> dict:
    return {"queries": _COMPANION_PROMPTS, "data_available": None, "mode": "ontology-search"}


@router.post("/chat/validate", dependencies=[Depends(graph_read_identity)])
def companion_validate(payload: ChatRequest) -> dict:
    from .prompt_security import protect
    payload = protect(payload.model_dump())
    message = " ".join(str(payload.get("message") or "").split())
    if not message:
        raise HTTPException(status_code=422, detail="message is required")
    return {"status": "ok", "valid": True, "session_id": payload.get("session_id"), "graph_context_present": bool(payload.get("graph_context"))}


@router.post("/chat", dependencies=[Depends(graph_read_identity)])
async def companion_chat(payload: ChatRequest, request: Request) -> dict:
    return await _companion_chat(payload, request)


def _session_turns(session, limit=20):
    """Bounded PostgreSQL history; never return another principal's turns."""
    _, items = companion_job_store.page(limit=limit, field='session_id', value=session['session_id'], order_field='finished_at')
    return [item for item in items if item.get('owner') == session['owner'] and item.get('status') == 'completed']


@router.get('/chat/sessions/{session_id}/history', dependencies=[Depends(graph_read_identity)])
async def companion_history(session_id: str, request: Request):
    actor = graph_read_identity(request)
    session = await run_in_threadpool(sessions.open_session, request, actor, session_id)
    turns = await run_in_threadpool(_session_turns, session)
    return {'session_id': session_id, 'turns': [
        {key: item.get(key) for key in ('job_id', 'user_request', 'response', 'evidence', 'sources', 'generation', 'finished_at')}
        for item in reversed(turns)]}


async def _companion_chat(payload: ChatRequest, request: Request, on_token=None) -> dict:
    payload = payload.model_dump()
    message = " ".join(str(payload.get("message") or "").split())
    if not message:
        raise HTTPException(status_code=422, detail="message is required")
    actor = graph_read_identity(request)
    session = await run_in_threadpool(sessions.open_session, request, actor, payload.get('session_id'))
    observation, observed_at = await _agent_io(telemetry.start,
        operation="knowledge_companion",
        request_id=getattr(request.state, "request_id", ""),
        session_id=session['session_id'],
    )
    try:
        headers = downstream_headers(request, companion._graph_root(), graph_read=True)
        memory_key = sessions.memory_id(session)
        context = await run_in_threadpool(AgentMemoryService.recent_context, memory_key, 6)
        if not context.get('messages'):
            turns = await run_in_threadpool(_session_turns, session, 6)
            context = {'messages': [{'role': 'user', 'text': turn.get('user_request', '')} for turn in turns]}
        # History supports follow-up retrieval only; graph evidence remains the
        # answer authority and memory text cannot authorize tools or writes.
        query = message
        if len(message.split()) <= 4:
            prior = next((item['text'] for item in context.get('messages', []) if item.get('role') == 'user'), '')
            if prior:
                query = f'{str(prior)[:1000]} {message}'
        generation_budget = 0
        if os.getenv('COMPANION_LLM_ENABLED', 'false').lower() == 'true':
            from .local_llm import settings
            generation_budget = settings()[3]
        async with asyncio.timeout(bounded_timeout_seconds('COMPANION_RETRIEVAL_TIMEOUT_SECONDS', default=15, maximum=120) + generation_budget + 5):
            kwargs = {'headers': headers, 'ontology_id': (payload.get('graph_context') or {}).get('ontology', '')}
            if (payload.get('graph_context') or {}).get('ontology_prefix'):
                kwargs['ontology_prefix'] = payload['graph_context']['ontology_prefix']
            if on_token:
                kwargs['on_token'] = on_token
            result = await companion.ask(query, **kwargs)
        if (not isinstance(result, dict) or not isinstance(result.get('response'), str)
                or not isinstance(result.get('evidence'), list) or not isinstance(result.get('sources'), list)
                or not isinstance(result.get('answerable'), bool)):
            raise RuntimeError('Knowledge companion returned an invalid evidence response')
        await run_in_threadpool(AgentMemoryService.record_chat_turn, session_id=memory_key,
            user_message=message, assistant_response=result['response'], generation=result.get('generation'))
        retained_id = 'companion-turn-' + observation['run_id']
        await _agent_io(companion_job_store.put, retained_id, {
            'job_id': retained_id, 'status': 'completed', 'session_id': session['session_id'],
            'owner': sessions.owner(request, graph_read_identity(request)),
            'user_request': message, 'response': result['response'], 'generation': result.get('generation'),
            'evidence': result['evidence'], 'sources': result['sources'], 'answerable': result['answerable'], 'finished_at': _now()})
        await _agent_io(_finish_observation,
            observation,
            observed_at,
            status="completed",
            evidence_count=len(result.get("evidence") or []),
        )
        return {**result, 'retained_prompt_job_id': retained_id, 'run_id': observation['run_id'], 'telemetry_run_id': observation['run_id'], 'session_id': session['session_id'], 'session_expires_at': session['expires_at'],
                'session_idle_seconds': int(bounded_timeout_seconds('AGENT_SESSION_IDLE_SECONDS', default=1800, maximum=86400)), 'mode': 'evidence-grounded'}
    except BaseException as exc:
        status = 'interrupted' if isinstance(exc, asyncio.CancelledError) else 'timed_out' if isinstance(exc, TimeoutError) else 'failed'
        await _agent_io(_finish_observation, observation, observed_at, status=status, error_type=type(exc).__name__)
        if isinstance(exc, (asyncio.CancelledError, HTTPException)) or not isinstance(exc, Exception):
            raise
        if isinstance(exc, RuntimeError):
            raise HTTPException(503, str(exc), headers={'X-DEPO-Run-ID': observation['run_id']}) from exc
        raise HTTPException(504 if isinstance(exc, TimeoutError) else 503, 'Knowledge companion request failed; no answer was generated', headers={'X-DEPO-Run-ID': observation['run_id']}) from exc


@router.post("/chat/jobs", dependencies=[Depends(graph_read_identity)])
async def companion_job(payload: ChatRequest, request: Request) -> dict:
    created_at = _now()
    response = await companion_chat(payload, request)
    job_id = f"companion-{uuid4()}"
    record = {"job_id": job_id, "status": "completed", "session_id": response["session_id"], "response": response["response"], "answerable": response["answerable"], "evidence": response["evidence"], "sources": response["sources"], "created_at": created_at, "finished_at": _now()}
    record['owner'] = sessions.owner(request, graph_read_identity(request))
    record['generation'] = response.get('generation')
    await _agent_io(companion_job_store.put, job_id, record)
    return {"status": "completed", "execution_mode": 'synchronous', "job_id": job_id, "poll_endpoint": f"/api/v1/chat/jobs/{job_id}", "session_id": response["session_id"]}


@router.get("/chat/jobs/{job_id}", dependencies=[Depends(graph_read_identity)])
def companion_job_status(job_id: str, request: Request) -> dict:
    record = companion_job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Chat job not found")
    if record.get('owner') != sessions.owner(request, graph_read_identity(request)):
        raise HTTPException(403, 'Chat job belongs to another identity')
    # Reading an owned retained result does not reopen its conversation session.
    return {key: value for key, value in record.items() if key not in {'owner', 'execution_payload', 'execution_id'}}


@router.get("/chat/health")
@router.get("/chat/status")
def companion_health() -> dict:
    return {"status": "ok", "service": "knowledge-companion", "mode": "ontology-search", "streaming": True, 'incremental_generation': False, 'generation_delivery': 'buffered-until-citations-validated', 'job_execution': 'synchronous', "fail_closed": True}


@router.get('/llm/health', dependencies=[Depends(graph_read_identity)])
async def local_llm_health() -> dict:
    from .local_llm import health
    return await health()


@router.get("/chat/capabilities")
def companion_capabilities() -> dict:
    return {"name": "knowledge-companion", "mode": "ontology-search", "operations": ["validate", "ask", "stream", "job", "sample-queries"], 'stream_mode': 'evidence-and-optional-generation-tokens', 'job_execution': 'synchronous', "evidence_required": True, 'instance_comparison': False, 'change_impact_analysis': False}


@router.post("/chat-stream", dependencies=[Depends(graph_read_identity)])
async def companion_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    actor = graph_read_identity(request)
    session = await _agent_io(sessions.open_session, request, actor, payload.session_id)
    payload = payload.model_copy(update={'session_id': session['session_id']})

    async def events():
        queue = asyncio.Queue(maxsize=32)
        async def token(text):
            await queue.put({'token': text})
        async def produce():
            try:
                result = await _companion_chat(payload, request, on_token=token)
                await queue.put({'response': result['response'], 'evidence': result['evidence'],
                    'sources': result['sources'], 'answerable': result['answerable'], 'run_id': result['run_id'],
                    'retained_prompt_job_id': result['retained_prompt_job_id'], 'generation': result.get('generation')})
                await queue.put({'done': True})
            except Exception as exc:
                await queue.put(stream_failure(exc, getattr(request.state, 'request_id', '')))
        task = asyncio.create_task(produce())
        try:
            yield 'data: {"status": "Retrieving graph evidence"}\n\n'
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ': keepalive\n\n'
                    continue
                if event is None:
                    break
                yield f'data: {json.dumps(event)}\n\n'
                if event.get('done') or event.get('error'):
                    break
        finally:
            task.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(events(), media_type='text/event-stream', headers={
        'X-Session-ID': session['session_id'], 'X-Session-Expires-At': session['expires_at'],
        'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@router.post('/agents/{agent_id}/suggest', dependencies=[Depends(graph_read_identity)])
async def suggest_agent_tool(agent_id: str, payload: ToolSuggestionBody, request: Request) -> dict:
    """Use an agent's configured prompt to propose one allowlisted tool; never execute it."""
    from .local_llm import suggest_tool, failure_status
    prompt_details = {}
    try:
        agent = catalog.item('agents', agent_id)
        selected = [catalog.item('tools', identifier) for identifier in agent.get('tools', [])]
        attachment = payload.get('attachment')
        if attachment is not None:
            try:
                if not isinstance(attachment, dict): raise ValueError('Invalid attachment')
                _multipart({'file': attachment})
            except ValueError as exc:
                raise HTTPException(422, 'Source attachment is invalid or exceeds the configured upload limit') from exc
        selected = [tool for tool in selected if tool.get('input_kind') != 'multipart' or attachment is not None]
        selected = await _proposal_tools(selected, request)
        for tool in selected:
            if tool.get('input_kind') == 'multipart':
                schema = tool['input_schema']
                schema['properties'].pop('file', None)
                schema['required'] = [key for key in schema.get('required', []) if key != 'file']
        if not selected: raise HTTPException(422, 'Attach a source file for this agent before requesting a recommendation')
        context = payload.get('context')
        if context is not None and (not isinstance(context, dict) or len(json.dumps(context)) > 16000):
            raise ValueError('Invalid page context')
        task = payload.get('task')
        attachment_metadata = {key: attachment.get(key) for key in ('filename', 'content_type')} if attachment else None
        suggestion = await suggest_tool(agent, selected, task, context=context, attachment_metadata=attachment_metadata, prompt_details=prompt_details)
        command = {'agent_id': agent_id, 'tool_id': suggestion['tool_id'], 'inputs': suggestion.get('inputs', {})}
        chosen = next((tool for tool in selected if tool['id'] == command['tool_id']), None)
        if chosen is None: raise ValueError('Tool is not allowlisted')
        if chosen.get('input_kind') == 'multipart':
            command['inputs']['file'] = attachment
        planned = plan(command)
        await _preflight_tools([command], request)
        result = {**planned, 'command': command, 'context': context, 'status': 'proposal', 'execution': 'requires_explicit_run_request', 'prompt_details': suggestion.get('prompt_details')}
        try:
            return await _agent_io(recommendations.create, result, sessions.owner(request, graph_read_identity(request)))
        except ValueError:
            raise
        except Exception as exc:
            raise HTTPException(503, 'Recommendation could not be saved; no tool was executed') from exc
    except Exception as exc:
        status = exc.status_code if isinstance(exc, HTTPException) else 422 if isinstance(exc, (ValueError, KeyError, TypeError)) else 503
        detail = 'Agent recommendation failed; no tool was executed'
        if prompt_details:
            try:
                saved = await _agent_io(recommendations.create, {
                    'status': 'failed', 'agent_id': agent_id, 'context': payload.get('context'),
                    'prompt_details': prompt_details, 'failure_status': failure_status(exc),
                    'execution': 'not_executable'}, sessions.owner(request, graph_read_identity(request)))
                detail = {'message': detail, 'recommendation_id': saved['recommendation_id']}
            except Exception:
                logger.warning('Failed recommendation prompt could not be retained')
        elif isinstance(exc, HTTPException):
            raise
        raise HTTPException(status, detail) from exc


@router.get('/agent-recommendations/{recommendation_id}', dependencies=[Depends(graph_read_identity)])
def saved_recommendation(recommendation_id: str, request: Request) -> dict:
    try:
        return recommendations.get(recommendation_id, sessions.owner(request, graph_read_identity(request)))
    except KeyError as exc:
        raise HTTPException(404, 'Saved recommendation not found') from exc
    except PermissionError as exc:
        raise HTTPException(403, 'Saved recommendation belongs to another identity') from exc
    except Exception as exc:
        raise HTTPException(503, 'Recommendation storage unavailable') from exc


@router.post("/plans")
def plan(payload: AgentPlanBody) -> dict:
    try:
        agent, tool = catalog.item("agents", str(payload["agent_id"])), catalog.item("tools", str(payload["tool_id"]))
        if tool["id"] not in agent.get("tools", []): raise ValueError("Tool is not allowlisted for this agent")
        requires_approval = bool(agent.get("approval_required") or tool.get("mutates") or tool["id"] in APPROVAL_TOKENS or payload.get("approval_required"))
        return {"valid": True, "agent": agent["id"], "tool": tool, "requires_approval": requires_approval}
    except (KeyError, ValueError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/workflow-plans")
def workflow_plan(payload: WorkflowPlanBody) -> dict:
    try:
        workflow = catalog.item("workflows", str(payload["workflow_id"]))
        steps = []
        for index, step in enumerate(workflow.get("steps", []), start=1):
            result = plan(step)
            steps.append({"sequence": index, **result, "requires_approval": bool(result["requires_approval"] or step.get("approval_required"))})
        if not steps: raise ValueError("Workflow has no steps")
        return {"valid": True, "workflow": workflow["id"], "steps": steps}
    except (KeyError, ValueError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lookup(value: Any, traces: list[dict[str, Any]]) -> Any:
    """Resolve a bounded ``$steps.N.result.field`` workflow reference."""
    if not isinstance(value, str) or not value.startswith("$steps."):
        return value
    parts = value.split(".")
    if len(parts) < 3 or parts[2] != "result":
        raise ValueError("workflow reference must use $steps.N.result[.field]")
    try:
        if not parts[1].isascii() or not parts[1].isdecimal() or not 1 <= int(parts[1]) <= len(traces):
            raise ValueError('Reference must name a completed prior step')
        trace = traces[int(parts[1]) - 1]
        if trace.get('status', 'completed') != 'completed':
            raise ValueError('Referenced step did not complete')
        current: Any = trace['result']
        for part in parts[3:]:
            if isinstance(current, list):
                if not part.isascii() or not part.isdecimal():
                    raise ValueError('List reference requires a nonnegative index')
                current = current[int(part)]
            else:
                current = current[part]
        return current
    except (IndexError, KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"workflow reference cannot be resolved: {value}") from exc


def _resolve_inputs(value: Any, traces: list[dict[str, Any]]) -> Any:
    if isinstance(value, dict): return {key: _resolve_inputs(item, traces) for key, item in value.items()}
    if isinstance(value, list): return [_resolve_inputs(item, traces) for item in value]
    return _lookup(value, traces)

def _multipart(inputs: dict[str, Any], file_field: str = 'file') -> tuple[dict[str, Any], dict[str, tuple[str, bytes, str]]]:
    upload = dict(inputs.get("file") or {})
    encoded = str(upload.get("content_base64") or "")
    if not upload.get("filename") or not encoded:
        raise ValueError("Multipart tools require inputs.file.filename and inputs.file.content_base64")
    if not isinstance(upload['filename'], str) or len(upload['filename']) > 255 or any(ord(char) < 32 for char in upload['filename']):
        raise ValueError('Attachment filename must be a valid name of at most 255 characters')
    limit = int(os.getenv('AGENTIC_MAX_UPLOAD_BYTES', str(25 * 1024 * 1024)))
    if len(encoded) > 4 * ((limit + 2) // 3):
        raise ValueError('Agent file exceeds AGENTIC_MAX_UPLOAD_BYTES')
    try: content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc: raise ValueError("file.content_base64 must be valid base64") from exc
    if len(content) > int(os.getenv("AGENTIC_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))):
        raise ValueError("Agent file exceeds AGENTIC_MAX_UPLOAD_BYTES")
    form = dict(inputs.get("form") or {})
    for key in ('approved_by', 'approval_token'):
        if key in inputs:
            form[key] = inputs[key]
    return form, {file_field: (str(upload["filename"]), content, str(upload.get("content_type") or "application/octet-stream"))}

async def _bounded_tool_request(client, method, endpoint, **kwargs):
    async with client.stream(method, endpoint, **kwargs) as response:
        response.raise_for_status()
        content = await read_bounded_response(response)
        return httpx.Response(response.status_code, headers=response.headers, content=content, request=response.request)


async def _await_pipeline_run(child_id):
    """Only poll the accepted job; the caller retains the original deadline."""
    from urllib.parse import quote
    from backend.depo_platform.network import service_bearer_headers
    endpoint = _base('data_pipeline') + '/pipeline/jobs/runs/' + quote(child_id, safe='')
    failures = 0
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        while True:
            try:
                response = await _bounded_tool_request(client, 'GET', endpoint, headers=service_bearer_headers('GRAPH_READ_TOKEN', service_name='data-job status', endpoint=endpoint))
                child = response.json()
                failures = 0
            except httpx.HTTPError as exc:
                failures += 1
                if failures >= 3 or getattr(getattr(exc, 'response', None), 'status_code', None) in {401, 403, 404}:
                    raise HTTPException(503, 'Dependent data-job status is unverified; inspect its retained run before retrying') from exc
                await asyncio.sleep(3)
                continue
            if not isinstance(child, dict) or child.get('run_id') != child_id or not isinstance(child.get('status'), str):
                raise HTTPException(502, 'Invalid data job status')
            if child['status'] not in {'queued', 'running'}:
                if child['status'] not in {'completed', 'quality_warning', 'validation_failed'}:
                    raise HTTPException(502, 'Dependent data job did not complete successfully')
                return {'status': child['status'], 'run_manifest': child}
            await asyncio.sleep(3)


async def _proposal_tools(tools, request):
    from .proposal_contracts import input_schema
    documents, result = {}, []
    async with asyncio.timeout(30), httpx.AsyncClient(timeout=10, trust_env=False) as client:
        for tool in tools:
            if tool.get('transport') != 'openapi':
                if tool.get('transport') != 'mcp': raise ValueError('Unsupported proposal tool transport')
                from .mcp_transport import invoke
                from .proposal_contracts import expand
                listed = await invoke(catalog.item('mcp_servers', tool['server_id']), 'tools/list')
                native = next((item for item in listed.get('tools', []) if isinstance(item, dict) and item.get('name') == tool.get('name')), None)
                if not native or not isinstance(native.get('inputSchema'), dict): raise ValueError('Configured MCP tool has no discoverable input schema')
                if (native.get('annotations') or {}).get('readOnlyHint') is False and not tool.get('mutates'):
                    raise ValueError('MCP mutation classification conflicts with the catalog')
                schema = native['inputSchema']
                result.append({**tool, 'input_schema': expand(schema, schema)})
                continue
            service = tool['service']
            if service not in documents:
                url = _base(service).removesuffix('/api/v1') + '/openapi.json'
                response = await _bounded_tool_request(client, 'GET', url, headers=downstream_headers(request, url, tool=tool))
                documents[service] = response.json()
            result.append({**tool, 'input_schema': input_schema(documents[service], tool)})
    return result


@router.post('/llm/probe')
async def probe_llm_capabilities(payload: ApprovalBody, request: Request):
    approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN')
    from .local_llm import probe_capabilities
    try: return await probe_capabilities()
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


async def _preflight_tools(commands, request, *, deferred=False):
    from .input_contracts import validate_operation, validate_bindings
    documents = {}
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        for index, command in enumerate(commands):
            if deferred:
                validate_bindings(command.get('inputs', {}), index)
            tool = plan(command)['tool']
            inputs = command.get('inputs', {})
            if tool.get('transport') == 'mcp':
                catalog.item('mcp_servers', tool['server_id'])
                if not tool.get('name'):
                    raise ValueError('MCP tool requires a configured native name')
                from .mcp_transport import invoke
                from .input_contracts import validate
                listed = await invoke(catalog.item('mcp_servers', tool['server_id']), 'tools/list')
                if not isinstance(listed.get('tools'), list) or any(not isinstance(row, dict) for row in listed['tools']):
                    raise ValueError('Invalid MCP tool list')
                native = next((row for row in listed['tools'] if row.get('name') == tool['name']), None)
                if native is None:
                    raise ValueError('Configured MCP tool is absent from its server')
                if (native.get('annotations') or {}).get('readOnlyHint') is False and not tool.get('mutates'):
                    raise ValueError('MCP tool mutation classification conflicts with its catalog')
                schema = native.get('inputSchema', {})
                validate(inputs, schema, schema, deferred=deferred)
                continue
            if tool.get('transport') != 'openapi':
                raise ValueError('Unsupported tool transport')
            if tool.get('input_kind') == 'multipart' and not (deferred and isinstance(inputs.get('file'), str) and inputs['file'].startswith('$steps.')):
                _multipart(inputs, 'artifact' if tool['id'] == 'ontology.register' else 'file')
            service = tool['service']
            if service not in documents:
                url = _base(service).removesuffix('/api/v1') + '/openapi.json'
                response = await _bounded_tool_request(client, 'GET', url, headers=downstream_headers(request, url, tool=tool))
                documents[service] = response.json()
            validate_operation(documents[service], tool, inputs, deferred=deferred)
    return documents


@router.get('/mcp-servers/{server_id}/tools', dependencies=[Depends(graph_read_identity)])
async def discover_mcp_tools(server_id: str, cursor: str | None = None):
    from .mcp_transport import invoke
    try:
        if cursor is not None and len(cursor) > 1024:
            raise ValueError('MCP discovery cursor exceeds 1024 characters')
        return await invoke(catalog.item('mcp_servers', server_id), 'tools/list', {'cursor': cursor} if cursor else {})
    except (ValueError, OSError, TimeoutError) as exc:
        raise HTTPException(503, 'MCP discovery failed; check the configured server installation') from exc


async def _dispatch(payload: dict[str, Any], request: Request) -> dict:
    plan_result = plan(payload)
    approved_by = None
    if plan_result["requires_approval"]:
        approved_by = approval_identity(request, payload, token_env="AGENTIC_APPROVAL_TOKEN")
    else:
        graph_read_identity(request)
    if not isinstance(payload.get('inputs', {}), dict):
        raise HTTPException(422, 'inputs must be an object')
    tool, inputs = plan_result["tool"], dict(payload.get("inputs") or {})
    if tool['id'] in {'bridge.mapping.preview', 'bridge.mapping.publish', 'bridge.mapping.evaluate', 'bridge.mapping.publish_automatic'}:
        # Reuse the durable Bridge job implementation in this service rather
        # than self-HTTP with a supervisor token on a read-authenticated route.
        from .bridge_router import jobs, PreviewInput, ApprovalInput, translate
        from pydantic import ValidationError
        try:
            if tool['id'] in {'bridge.mapping.evaluate', 'bridge.mapping.publish_automatic'}:
                if set(inputs) != {'preview_id'} or not isinstance(inputs['preview_id'], str) or not inputs['preview_id'].startswith('bridge-preview-'):
                    raise HTTPException(422, 'Select a saved bridge preview')
                action = jobs.evaluate_policy if tool['id'] == 'bridge.mapping.evaluate' else lambda key: jobs.publish_automatic(key, approved_by)
                result = await _agent_io(translate, lambda: action(inputs['preview_id']))
                return {'agent_id': plan_result['agent'], 'tool_id': tool['id'], 'approved_by': approved_by, 'result': result}
            command = PreviewInput(**inputs) if tool['id'] == 'bridge.mapping.preview' else ApprovalInput(**{key: value for key, value in inputs.items() if key != 'preview_id'})
        except ValidationError as exc:
            raise HTTPException(422, 'Invalid Bridge inputs; check source IDs and reviewed candidate selection') from exc
        if tool['id'] == 'bridge.mapping.preview':
            result = await _agent_io(translate, lambda: jobs.preview(command.ontology_id, command.import_task_id, approved_by, command.manual_mappings))
        else:
            preview_id = inputs.pop('preview_id', '')
            result = await _agent_io(translate, lambda: jobs.publish(preview_id, command.approved_candidate_ids, approved_by))
        return {'agent_id': plan_result['agent'], 'tool_id': tool['id'], 'approved_by': approved_by, 'result': result}
    if tool.get('transport') == 'mcp':
        from .mcp_transport import invoke
        # Mutating MCP tools need an explicit downstream approval contract too.
        arguments = downstream_inputs(tool, inputs, approved_by)
        try:
            await _preflight_tools([payload], request)
            result = await invoke(catalog.item('mcp_servers', tool['server_id']), 'tools/call',
                                  {'name': tool['name'], 'arguments': arguments})
            return {'agent_id': plan_result['agent'], 'tool_id': tool['id'], 'result': result}
        except (ValueError, OSError, TimeoutError) as exc:
            raise HTTPException(503, 'MCP tool failed; inspect server status before retrying') from exc
    if tool.get('transport') != 'openapi':
        raise HTTPException(422, 'Unsupported tool transport')
    try:
        await _preflight_tools([payload], request)
        path = _render(str(tool["path"]), inputs)
        endpoint = _base(tool["service"]) + path
        headers = downstream_headers(request, endpoint, tool=tool)
        inputs = downstream_inputs(tool, inputs, approved_by)
        async with httpx.AsyncClient(timeout=bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30), trust_env=False) as client:
            if tool.get("input_kind") == "multipart":
                form, files = _multipart(inputs, 'artifact' if tool['id'] == 'ontology.register' else 'file')
                response = await _bounded_tool_request(client, tool["method"], endpoint, headers=headers, data=form, files=files)
            elif tool.get("input_kind") == "form":
                response = await _bounded_tool_request(client, tool["method"], endpoint, headers=headers, data=inputs)
            else:
                response = await _bounded_tool_request(client, tool["method"], endpoint, headers=headers, params=inputs if tool["method"] == "GET" else None, json=None if tool["method"] == "GET" else inputs)
            response.raise_for_status()
        if tool["id"] == "ontology.export":
            result = {"content_base64": base64.b64encode(response.content).decode("ascii"),
                      "content_type": response.headers.get("content-type", "application/octet-stream")}
        else:
            try:
                result = response.json()
            except ValueError as exc:
                raise HTTPException(502, 'Downstream tool returned invalid JSON') from exc
        return {"agent_id": plan_result["agent"], "tool_id": tool["id"], "approved_by": approved_by, "result": result}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise HTTPException(status_code=status if 400 <= status < 600 else 502,
                            detail=f'Downstream tool rejected the request (HTTP {status})') from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail="Downstream tool request failed; inspect service status before retrying") from exc


@router.post('/runs')
async def run(payload: ToolRunBody, request: Request) -> dict:
    planned = plan(payload)
    if planned['requires_approval']:
        approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN')
    else:
        graph_read_identity(request)
    if planned['tool'].get('mutates'):
        from .single_tool import execute
        return await execute(payload, request)
    observation, started = await _agent_io(telemetry.start, operation='tool', request_id=getattr(request.state, 'request_id', ''))
    try:
        async with asyncio.timeout(bounded_timeout_seconds('AGENTIC_RUN_TIMEOUT_SECONDS', default=300)):
            result = await _dispatch(payload, request)
        await _agent_io(_tool_span, observation, tool_id=result['tool_id'], attempt=1, status='completed', duration_ms=(time.perf_counter()-started)*1000)
        await _agent_io(_finish_observation, observation, started, status='completed')
        return {**result, 'status': 'completed', 'execution_kind': 'agent',
                'run_id': observation['run_id'], 'telemetry_run_id': observation['run_id']}
    except BaseException as exc:
        status = 'interrupted' if isinstance(exc, asyncio.CancelledError) else 'timed_out' if isinstance(exc, TimeoutError) else 'failed'
        try:
            await _agent_io(_tool_span, observation, tool_id=str(payload.get('tool_id', '')), attempt=1, status=status, duration_ms=(time.perf_counter()-started)*1000, error_type=type(exc).__name__)
            await _agent_io(_finish_observation, observation, started, status=status, error_type=type(exc).__name__)
        except Exception:
            logger.exception('Unable to persist terminal tool telemetry')
        if isinstance(exc, TimeoutError):
            raise HTTPException(504, 'Tool deadline exceeded; reconcile any downstream write before retrying', headers={'X-DEPO-Run-ID': observation['run_id']}) from exc
        if isinstance(exc, Exception) and not isinstance(exc, HTTPException):
            raise HTTPException(503, 'Tool execution failed; reconcile any downstream write before retrying', headers={'X-DEPO-Run-ID': observation['run_id']}) from exc
        if isinstance(exc, HTTPException):
            exc.headers = {**(exc.headers or {}), 'X-DEPO-Run-ID': observation['run_id']}
        raise


@router.get('/runs/{run_id}', dependencies=[Depends(graph_read_identity)])
def tool_run(run_id: str) -> dict:
    record = telemetry.store.get(run_id)
    if not record:
        raise HTTPException(404, 'Agent tool run not found')
    if record.get('status') == 'running' and record.get('deadline_at') and datetime.now(timezone.utc) >= datetime.fromisoformat(record['deadline_at']):
        return {**record, 'status': 'interrupted', 'reconciliation_required': True, 'state_source': 'deadline_projection'}
    return record


@router.post('/workflow-runs')
async def run_workflow(payload: WorkflowRunBody, request: Request) -> dict:
    from .durable_workflows import execution_mode, enqueue
    if execution_mode() == 'worker':
        try: return await enqueue(payload,request)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    accepted = asyncio.get_running_loop().create_future()
    return await _keep_workflow_running(_execute_workflow(payload, request, accepted=accepted), accepted)


def _workflow_owner(request, approved_actor):
    # Use the verified reader principal for status ownership, independently of
    # the actor who authorized publication.
    try:
        actor = graph_read_identity(request)
    except HTTPException as exc:
        if exc.status_code not in {401, 403}:
            raise
        actor = approved_actor
    return sessions.owner(request, actor)


async def _persist_workflow(record):
    current = await _agent_io(workflow_store.get, record['run_id'])
    if not current or current.get('execution_id') != record['execution_id']:
        raise HTTPException(409, 'Workflow execution ownership changed')
    if not await _agent_io(workflow_store.compare_and_put, record['run_id'], current, record):
        raise HTTPException(409, 'Workflow state changed concurrently')


async def _execute_workflow(payload: dict[str, Any], request: Request, recovery=None, accepted=None) -> dict:
    """Execute a bounded workflow; uncertain writes require reconciliation."""
    record = observation = None
    dispatched_mutation = False
    active_step = None
    attempt = 0
    try:
        workflow = catalog.item('workflows', str(payload['workflow_id']))
        planned = workflow_plan(payload)
        approved_workflow = any(step['requires_approval'] for step in planned['steps'])
        if approved_workflow:
            actor = approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN')
        else:
            actor = graph_read_identity(request)
        requested = payload.get('step_inputs')
        if requested is not None and (not isinstance(requested, list) or len(requested) != len(workflow['steps']) or any(not isinstance(item, dict) for item in requested)):
            raise ValueError('step_inputs must contain one object for each workflow step')
        if not isinstance(payload.get('inputs', {}), dict):
            raise ValueError('inputs must be an object')
        commands = [{**step, 'inputs': {**(requested[index] if requested is not None else payload.get('inputs', {})), **step.get('input_bindings', {})}} for index, step in enumerate(workflow['steps'])]
        await _preflight_tools(commands, request, deferred=True)
        retries_by_step = []
        for step in workflow['steps']:
            retries = int(step.get('retries', 0))
            if not 0 <= retries <= 5:
                raise ValueError('Workflow retries must be between zero and five')
            retries_by_step.append(retries)
        timeout = bounded_timeout_seconds('AGENTIC_RUN_TIMEOUT_SECONDS', default=300)
        run_id = recovery['run_id'] if recovery else f'run-{uuid4()}'
        request_id = getattr(request.state, 'request_id', '')
        observation, observed_at = await _agent_io(telemetry.start, operation='workflow', request_id=request_id, workflow_id=workflow['id'], workflow_run_id=run_id)
        record = {'owner': _workflow_owner(request, actor), 'run_id': run_id, 'telemetry_run_id': observation['run_id'], 'workflow_id': workflow['id'], 'request_id': request_id,
                  'status': 'running', 'started_at': _now(), 'updated_at': _now(),
                  'deadline_at': (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat(), 'traces': []}
        from .recovery import execution_payload, fingerprint
        definition = {'workflow': workflow, 'steps': planned['steps']}
        record.update(execution_id=uuid4().hex, execution_payload=execution_payload(payload),
                      workflow_definition=definition, workflow_digest=fingerprint(definition))
        if recovery:
            record.update(owner=recovery.get('owner', record['owner']), traces=recovery['traces'], deadline_at=recovery['deadline_at'], started_at=recovery['started_at'],
                          execution_mode=recovery.get('execution_mode','process'), credential_fingerprints=recovery.get('credential_fingerprints',{}), approved_actor=recovery.get('approved_actor',actor),
                          transport_fingerprint=recovery.get('transport_fingerprint',''),
                          reconciliations=recovery.get('reconciliations', []),
                          recovery_history=[*recovery.get('recovery_history', []), {'actor': actor, 'request_id': request_id, 'recovered_at': _now(), 'previous_telemetry_run_id': recovery.get('telemetry_run_id')}])
            timeout = (datetime.fromisoformat(record['deadline_at']) - datetime.now(timezone.utc)).total_seconds()
            if timeout <= 0:
                raise HTTPException(409, 'The original workflow deadline has expired')
            if not await _agent_io(workflow_store.compare_and_put, run_id, recovery.get('_expected_record', recovery), record):
                raise HTTPException(409, 'Recovery was claimed by another execution')
        else:
            await _agent_io(workflow_store.create, run_id, record)
        if accepted is not None and not accepted.done():
            accepted.set_result({'run_id':run_id, 'workflow_id':workflow['id'], 'status':'running',
                                 'deadline_at':record['deadline_at']})
        async with asyncio.timeout(timeout), execution_heartbeat(workflow_heartbeats, f"{run_id}:{record['execution_id']}"):
            for index, step in enumerate(workflow['steps']):
                if index < len(record['traces']):
                    continue
                active_step, attempt = step, 0
                inputs = _resolve_inputs({**(requested[index] if requested is not None else payload.get('inputs', {})), **step.get('input_bindings', {})}, record['traces'])
                if step['tool_id'] == 'data.product.publish' and not inputs.get('idempotency_key'):
                    inputs['idempotency_key'] = f'workflow:{run_id}:{index+1}'
                command = {**step, 'approval_required': approved_workflow or step.get('approval_required', False),
                           'inputs': inputs, 'approved_by': payload.get('approved_by'), 'approval_token': payload.get('approval_token')}
                tool = planned['steps'][index]['tool']
                while True:
                    await workflow_checkpoint(workflow_controls, run_id)
                    attempt += 1
                    tool_started = time.perf_counter()
                    try:
                        dispatched_mutation = bool(tool.get('mutates'))
                        record.update(pending_step={'sequence': index+1, 'tool_id': step['tool_id'], 'attempt': attempt, 'mutates': dispatched_mutation,
                                                   'inputs': execution_payload({'inputs':inputs})['inputs']}, updated_at=_now())
                        await _persist_workflow(record)
                        result = await _dispatch(command, request)
                        if step['tool_id'] == 'pipeline.run' and isinstance(result.get('result'), dict) and result['result'].get('status') == 'queued':
                            child_id = (result['result'].get('run_manifest') or {}).get('run_id')
                            if not isinstance(child_id, str) or not child_id: raise HTTPException(502, 'Queued data job has no run identity')
                            record['pending_step']['child_run_id'] = child_id
                            await _persist_workflow(record)
                            result['result'] = await _await_pipeline_run(child_id)
                        duration = (time.perf_counter() - tool_started)*1000
                        record['traces'].append({'sequence': index+1, 'tool_id': step['tool_id'], 'attempt': attempt, 'status': 'completed', 'duration_ms': round(duration, 2), 'result': result.get('result', {})})
                        await _agent_io(_tool_span, observation, tool_id=step['tool_id'], attempt=attempt, status='completed', duration_ms=duration)
                        record.update(updated_at=_now(), pending_step=None)
                        await _persist_workflow(record)
                        dispatched_mutation = False
                        active_step = None
                        break
                    except HTTPException as exc:
                        await _agent_io(_tool_span, observation, tool_id=step['tool_id'], attempt=attempt, status='failed', duration_ms=(time.perf_counter()-tool_started)*1000, error_type=type(exc).__name__)
                        if tool_retry_allowed(tool, attempt=attempt, retries=retries_by_step[index], status_code=exc.status_code):
                            await asyncio.sleep(min(attempt, 5))
                            continue
                        raise
            await workflow_checkpoint(workflow_controls, run_id)
        record.update(status='completed', finished_at=_now(), updated_at=_now())
        await _persist_workflow(record)
        await _agent_io(_finish_observation, observation, observed_at, status='completed')
        return {key: value for key, value in record.items() if key not in {'owner', 'execution_payload', 'execution_id', 'credential_fingerprints'}}
    except BaseException as exc:
        status = 'cancelled' if isinstance(exc, WorkflowCancelled) else 'interrupted' if isinstance(exc, asyncio.CancelledError) else 'timed_out' if isinstance(exc, TimeoutError) else 'failed'
        if record is not None:
            if dispatched_mutation:
                try:
                    retained = await _agent_io(workflow_store.get, record['run_id'])
                except Exception:
                    retained = None
                    logger.exception('Unable to read retained write intent')
                if retained and retained.get('execution_id') == record['execution_id'] and retained.get('pending_step'):
                    record['pending_step'] = retained['pending_step']
                    record['traces'] = retained['traces']
            record.update(status=status, finished_at=_now(), updated_at=_now(), error_type=type(exc).__name__, reconciliation_required=dispatched_mutation)
            if active_step:
                diagnostics = workflow_error(exc, active_step['tool_id'])
                record.update(diagnostics)
                record['traces'].append({'sequence': len(record['traces'])+1, 'tool_id': active_step['tool_id'], 'attempt': attempt, 'status': status, 'error_type': type(exc).__name__, **diagnostics})
            # Persist state and telemetry independently. A DB outage must not
            # replace the original exception; deadline-based reads expose an
            # interrupted process even if final persistence could not succeed.
            try:
                await _persist_workflow(record)
            except Exception:
                logger.exception('Unable to persist terminal workflow state')
        if observation is not None:
            try:
                if active_step and attempt and not isinstance(exc, HTTPException):
                    await _agent_io(_tool_span, observation, tool_id=active_step['tool_id'], attempt=attempt,
                               status=status, duration_ms=(time.perf_counter()-tool_started)*1000, error_type=type(exc).__name__)
                await _agent_io(_finish_observation, observation, observed_at, status=status, error_type=type(exc).__name__)
            except Exception:
                logger.exception('Unable to persist terminal workflow telemetry')
        if isinstance(exc, WorkflowCancelled) and record:
            return {key: value for key, value in record.items() if key not in {'owner', 'execution_payload', 'execution_id', 'credential_fingerprints'}}
        if isinstance(exc, (KeyError, ValueError, TypeError)):
            raise HTTPException(422, str(exc), headers={'X-DEPO-Run-ID': record['run_id']} if record else None) from exc
        if isinstance(exc, TimeoutError):
            raise HTTPException(504, 'Workflow deadline exceeded; inspect run state before retrying', headers={'X-DEPO-Run-ID': record['run_id']} if record else None) from exc
        if isinstance(exc, HTTPException) and record:
            exc.headers = {**(exc.headers or {}), 'X-DEPO-Run-ID': record['run_id']}
        if isinstance(exc, (HTTPException, asyncio.CancelledError)) or not isinstance(exc, Exception):
            raise
        raise HTTPException(503, 'Workflow execution failed; inspect run state before retrying', headers={'X-DEPO-Run-ID': record['run_id']} if record else None) from exc


@router.post('/workflow-runs/{run_id}/reconcile')
async def reconcile_workflow(run_id: str, payload: ReconcileWorkflowBody, request: Request) -> dict:
    from .recovery import reconcile
    actor = approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN')
    record = await _agent_io(workflow_store.get, run_id)
    if not record:
        raise HTTPException(404, 'Workflow run not found')
    try:
        heartbeat = await _agent_io(workflow_heartbeats.get, f"{run_id}:{record.get('execution_id', '')}")
        updated = reconcile(record, payload.get('outcome'), payload.get('evidence'), actor, payload.get('result'), payload.get('executor_stopped', False), activity_at=last_activity(record, heartbeat))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not await _agent_io(workflow_store.compare_and_put, run_id, record, updated):
        raise HTTPException(409, 'Workflow changed during reconciliation')
    return {'run_id': run_id, 'status': updated['status'], 'reconciliation_required': False}


@router.post('/workflow-runs/{run_id}/reconcile-receipt')
async def reconcile_workflow_receipt(run_id: str, payload: ReconcileWorkflowBody, request: Request) -> dict:
    from .workflow_receipts import lookup
    from .recovery import reconcile
    actor = approval_identity(request,payload,token_env='AGENTIC_APPROVAL_TOKEN')
    record = await _agent_io(workflow_store.get,run_id)
    if not record: raise HTTPException(404,'Workflow run not found')
    heartbeat = await _agent_io(workflow_heartbeats.get,f"{run_id}:{record.get('execution_id','')}")
    try:
        result = await lookup(record,request)
        updated = reconcile(record,'completed','Verified downstream receipt for '+(record.get('pending_step') or {}).get('tool_id',''),actor,result,payload.get('executor_stopped',False),activity_at=last_activity(record,heartbeat))
    except (ValueError,KeyError) as exc: raise HTTPException(409,str(exc)) from exc
    except httpx.HTTPError as exc: raise HTTPException(503,'Receipt lookup failed; no workflow mutation was repeated') from exc
    if not await _agent_io(workflow_store.compare_and_put,run_id,record,updated): raise HTTPException(409,'Workflow changed during receipt verification')
    return {'run_id':run_id,'status':updated['status'],'reconciliation_required':False}


@router.get('/workflow-runs/{run_id}/compensation-plan')
def workflow_compensation_plan(run_id: str, request: Request) -> dict:
    from .workflow_receipts import compensation_plan
    workflow_run(run_id,request)  # Reuse owner/supervisor authorization.
    try: return compensation_plan(workflow_store.get(run_id))
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


@router.post('/workflow-runs/{run_id}/compensate')
async def compensate_workflow(run_id: str, payload: CompensationBody, request: Request) -> dict:
    from .workflow_receipts import compensation_plan
    actor = approval_identity(request,payload,token_env='AGENTIC_APPROVAL_TOKEN')
    reason = payload.get('reason')
    if not isinstance(reason,str) or not reason.strip() or len(reason) > 4000: raise HTTPException(422,'A compensation reason is required (maximum 4000 characters)')
    with workflow_store.advisory_lock('compensate:'+run_id) as acquired:
        if not acquired: raise HTTPException(409,'Compensation is already in progress')
        record = await _agent_io(workflow_store.get,run_id)
        if not record: raise HTTPException(404,'Workflow run not found')
        try: planned = compensation_plan(record)
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
        action = next((item for item in planned['actions'] if item['sequence'] == payload.get('sequence')),None)
        if not action: raise HTTPException(409,'No approved reversible operation exists for this step')
        key = str(action['sequence'])
        prior = (record.get('compensations') or {}).get(key)
        if prior and prior.get('status') == 'completed': return prior
        remaining = [item for item in planned['actions'] if (record.get('compensations') or {}).get(str(item['sequence']),{}).get('status') != 'completed']
        if remaining and remaining[0]['sequence'] != action['sequence']:
            raise HTTPException(409,'Compensate later completed steps before earlier dependent steps')
        if any(item['sequence'] > action['sequence'] for item in planned['unsupported']):
            raise HTTPException(409,'A later write has no approved inverse; review its downstream state before compensation')
        if prior and prior.get('reason') != reason.strip(): raise HTTPException(409,'Retry the original compensation reason and identity')
        intent = prior or {**action,'status':'pending','reason':reason.strip(),'approved_actor':actor,'request_id':f'compensate:{run_id}:{key}'}
        updated = {**record,'compensations':{**record.get('compensations',{}),key:intent}}
        if not await _agent_io(workflow_store.compare_and_put,run_id,record,updated): raise HTTPException(409,'Workflow changed before compensation')
        result = await _dispatch({'agent_id':'data-product-governor','tool_id':'data.product.revoke',
            'inputs':{'product_version':action['product_version'],'reason':intent['reason'],'idempotency_key':intent['request_id']},
            'approved_by':payload.get('approved_by'),'approval_token':payload.get('approval_token')},request)
        completed = {**intent,'status':'completed','result':result.get('result',{}),'completed_at':_now()}
        final = {**updated,'compensations':{**updated['compensations'],key:completed}}
        if not await _agent_io(workflow_store.compare_and_put,run_id,updated,final): raise HTTPException(409,'Compensation may have completed; inspect downstream receipt before retrying')
        return completed


@router.post('/workflow-runs/{run_id}/recover')
async def recover_workflow(run_id: str, payload: ApprovalBody, request: Request) -> dict:
    from .recovery import prepare_recovery
    approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN')
    record = await _agent_io(workflow_store.get, run_id)
    if not record:
        raise HTTPException(404, 'Workflow run not found')
    try:
        workflow = catalog.item('workflows', record['workflow_id'])
        definition = {'workflow': workflow, 'steps': workflow_plan({'workflow_id': record['workflow_id']})['steps']}
        heartbeat = await _agent_io(workflow_heartbeats.get, f"{run_id}:{record.get('execution_id', '')}")
        recovery = prepare_recovery(record, definition, activity_at=last_activity(record, heartbeat))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    command = {**recovery['execution_payload'], 'approved_by': payload.get('approved_by'), 'approval_token': payload.get('approval_token')}
    # Reauthorize before claiming so a rejected caller cannot strand the run.
    if any(step['requires_approval'] for step in workflow_plan(command)['steps']):
        approval_identity(request, command, token_env='AGENTIC_APPROVAL_TOKEN')
    recovery['_expected_record'] = record
    from .durable_workflows import execution_mode, enqueue
    if execution_mode() == 'worker':
        return await enqueue(command,request,recovery=recovery)
    return await _keep_workflow_running(_execute_workflow(command, request, recovery=recovery))


@router.post("/workflow-runs/{run_id}/control", summary="Pause, resume or cancel at the next tool boundary")
def control_workflow(run_id: str, payload: WorkflowControlBody, request: Request) -> dict:
    from backend.depo_platform.authorization import service_write_identity
    actor = service_write_identity(request, token_env="AGENTIC_APPROVAL_TOKEN", default_actor="agent-supervisor")
    action = payload.get("action")
    if not isinstance(action, str) or action not in {"pause", "resume", "cancel"}:
        raise HTTPException(422, "action must be pause, resume or cancel")
    record = workflow_store.get(run_id)
    if not record:
        raise HTTPException(404, "Workflow run not found")
    if record.get("status") not in {'running','queued'} or datetime.now(timezone.utc) >= datetime.fromisoformat(record["deadline_at"]):
        raise HTTPException(409, "Only an active workflow can be controlled")
    with workflow_controls.advisory_lock(run_id) as acquired:
        if not acquired:
            raise HTTPException(409, "Workflow control is being updated; retry")
        prior = workflow_controls.get(run_id) or {}
        if prior.get("action") == "cancel" and action != "cancel":
            raise HTTPException(409, "Cancellation cannot be reversed")
        workflow_controls.put(run_id, {"action": action, "actor": actor, "requested_at": _now()})
    return {"run_id": run_id, "action": action, "status": "requested",
            "scope": "next tool boundary; completed writes are retained; the original deadline still applies"}


@router.get("/workflow-runs/{run_id}")
def workflow_run(run_id: str, request: Request) -> dict:
    from backend.depo_platform.authorization import service_write_identity
    actor = None
    try:
        service_write_identity(request, token_env='AGENTIC_APPROVAL_TOKEN', default_actor='agent-supervisor')
    except HTTPException:
        actor = graph_read_identity(request)
    record = workflow_store.get(run_id)
    if not record:
        raise HTTPException(404, 'Workflow run not found')
    if actor is not None and (not record.get('owner') or record['owner'] != sessions.owner(request, actor)):
        raise HTTPException(403, 'Workflow belongs to another identity or requires supervisory access')
    heartbeat = workflow_heartbeats.get(f"{run_id}:{record.get('execution_id', '')}") if record.get('status') == 'running' else None
    control = workflow_controls.get(run_id) or {}
    from .workflow_control import workflow_snapshot
    return workflow_snapshot(record, control, heartbeat)


@router.get('/workflow-runs')
def list_workflow_runs(request: Request, limit: int = 50) -> dict:
    from backend.depo_platform.authorization import service_write_identity
    owner = None
    try:
        service_write_identity(request, token_env='AGENTIC_APPROVAL_TOKEN', default_actor='agent-supervisor')
    except HTTPException:
        owner = sessions.owner(request, graph_read_identity(request))
    bounded = max(1, min(limit, 100))
    if owner is None:
        records = workflow_store.recent(bounded)
    else:
        _, records = workflow_store.page(limit=bounded, field='owner', value=owner)
    fields = ('run_id', 'workflow_id', 'status', 'started_at', 'deadline_at')
    return {'runs': [{**{key: row.get(key) for key in fields}, 'kind': 'workflow'}
                     for row in records if owner is None or row.get('owner') == owner],
            'limit': max(1, min(limit, 100))}


@router.get("/observability/summary", dependencies=[Depends(graph_read_identity)])
def observability_summary(limit: int = 500) -> dict:
    return {"status": "ok", **telemetry.summary(limit)}


@router.get("/observability/runs", dependencies=[Depends(graph_read_identity)])
def observability_runs(limit: int = 100) -> dict:
    bounded = max(1, min(int(limit), 500))
    return {"status": "ok", "runs": telemetry.recent(bounded), "limit": bounded}


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(telemetry.prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/catalog/validate", dependencies=[Depends(graph_read_identity)])
async def validate_openapi_catalog() -> dict:
    """Compare declarative HTTP tools with their live OpenAPI operations."""
    errors: list[dict[str, str]] = []
    documents: dict[str, dict] = {}
    from backend.depo_platform.openapi_contract import contract_errors
    unavailable = set()
    try:
        from backend.depo_platform.network import gateway_subscription_headers
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            for tool in catalog.read()["tools"]:
                if tool.get("transport") != "openapi": continue
                service = str(tool["service"])
                if service in unavailable:
                    continue
                if service not in documents:
                    try:
                        endpoint = _base(service).removesuffix("/api/v1") + "/openapi.json"
                        response = await client.get(endpoint, headers=gateway_subscription_headers(endpoint))
                        response.raise_for_status()
                        document = response.json()
                        if not isinstance(document, dict):
                            raise ValueError('OpenAPI document must be an object')
                        documents[service] = document
                        errors.extend({'service': service, 'error': issue} for issue in contract_errors(documents[service]))
                    except (ValueError, httpx.HTTPError):
                        unavailable.add(service)
                        errors.append({'service': service, 'error': 'OpenAPI contract is unavailable or invalid JSON'})
                        continue
                operation = documents[service].get("paths", {}).get("/api/v1" + tool["path"], {}).get(str(tool["method"]).lower())
                if not operation: errors.append({"tool_id": tool["id"], "error": "operation is absent from live OpenAPI"})
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(503, f"Unable to validate live OpenAPI contracts: {exc}") from exc
    return {"valid": not errors, "errors": errors, "services": sorted(documents), "unavailable_services": sorted(unavailable)}


@router.get("/code-audit", dependencies=[Depends(graph_read_identity)], summary="Generate or read the bounded repository dependency graph")
async def code_audit(refresh: bool = False) -> dict:
    """Expose code-network analysis from the agentic control plane.

    The audit is read-only and is deliberately kept with the extensible tool
    catalog rather than the retired aggregate application.
    """
    try:
        from tools.code_graph_audit import OUTPUT, audit

        if refresh or not OUTPUT.exists():
            report = await run_in_threadpool(audit)
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        else:
            report = json.loads(OUTPUT.read_text(encoding="utf-8"))
        report["generated_at"] = OUTPUT.stat().st_mtime
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Code audit generation failed: {type(exc).__name__}") from exc
