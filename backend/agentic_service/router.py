"""Catalog and bounded execution for independently extensible agents/tools."""
from __future__ import annotations
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
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from backend.mesh_store import PostgresRegistry
from .companion import companion
from .chat_request import ChatRequest
from .transport_auth import APPROVAL_TOKENS, downstream_headers, downstream_inputs, tool_retry_allowed
from .oslc_graph_rag import oslc_graph_rag
from .dt_requirements_adapter import assess_manifest
from .dt_gateway import execute_current_plan
from .dt_bindings import extend_catalog, capabilities as dt_capabilities
from .telemetry import telemetry
from . import sessions
from .response_limits import read_bounded_response
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
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not all(isinstance(data.get(key), list) for key in ("agents", "tools", "mcp_servers", "workflows")):
            raise ValueError("Catalog must define agents, tools, mcp_servers, and workflows lists")
        return extend_catalog(data)
    def item(self, kind: str, identifier: str) -> dict[str, Any]:
        for value in self.read()[kind]:
            if value.get("id") == identifier: return value
        raise ValueError(f"Unknown {kind[:-1]}: {identifier}")

catalog = Catalog()
workflow_store = PostgresRegistry("agentic_workflow_runs")
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
def agents() -> dict: return {"agents": catalog.read()["agents"]}
@router.get("/tools")
def tools() -> dict: return {"tools": catalog.read()["tools"]}
@router.get("/mcp-servers")
def mcp_servers() -> dict: return {"mcp_servers": catalog.read()["mcp_servers"]}
@router.get("/workflows")
def workflows() -> dict: return {"workflows": catalog.read()["workflows"]}


@router.post("/integrations/dt-requirements-design/compatibility")
def dt_requirements_design_compatibility(payload: dict[str, Any]) -> dict:
    """Check an external DT Requirements Design manifest against PMem tools."""
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=422, detail="manifest must be an object")
    return assess_manifest(manifest, catalog.read())


@router.get("/integrations/dt-requirements-design/capabilities")
def dt_capability_bindings() -> dict:
    return dt_capabilities()


@router.post("/integrations/dt-requirements-design/runs")
async def dt_run(payload: dict[str, Any], request: Request) -> dict:
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
async def oslc_graph_rag_route(payload: dict[str, Any]) -> dict:
    """OSLC-governed, read-only retrieval for agent context."""
    if os.getenv('OSLC_REMOTE_ENABLED', 'false').lower() != 'true':
        raise HTTPException(503, 'Remote OSLC integration is disabled; configure and enable OSLC_REMOTE_ENABLED')
    try:
        return await oslc_graph_rag.retrieve(
            str(payload.get("query") or ""),
            str(payload.get("resource_type") or "resources"),
            int(payload.get("limit") or 10),
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
def execute_semantic_workflow(payload: dict[str, Any]) -> dict:
    """Execute a governed semantic workflow without routing through the legacy monolith."""
    workflow_id = str(payload.get("workflow_id") or "").strip()
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id is required")
    try:
        from backend.Services.semantic_workflow_service import SemanticWorkflowService
        return SemanticWorkflowService.execute(workflow_id, dict(payload.get("payload") or {}))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ontology-agents/orchestrate", dependencies=[Depends(graph_read_identity)])
def orchestrate_ontology_agents(payload: dict[str, Any]) -> dict:
    """Run read-only ontology intake/review/Bridge planning agents."""
    from .ontology_orchestrator import orchestrate
    return _ontology_agent_call(orchestrate, payload)


def _ontology_agent_call(operation, payload: dict[str, Any]) -> dict:
    observation, started = telemetry.start(operation='ontology_agent:' + operation.__name__)
    try:
        result = operation(payload)
        _finish_observation(observation, started, status='completed')
        return {**result, 'run_id': observation['run_id'], 'telemetry_run_id': observation['run_id']}
    except (ValueError, OSError) as exc:
        _finish_observation(observation, started, status='failed', error_type=type(exc).__name__)
        raise HTTPException(status_code=422, detail=str(exc), headers={'X-DEPO-Run-ID': observation['run_id']}) from exc
    except Exception as exc:
        _finish_observation(observation, started, status='failed', error_type=type(exc).__name__)
        raise HTTPException(status_code=422, detail="Ontology agent could not parse the supplied artifact", headers={'X-DEPO-Run-ID': observation['run_id']}) from exc


@router.post("/ontology-agents/intake", dependencies=[Depends(graph_read_identity)])
def ontology_agent_intake(payload: dict[str, Any]) -> dict:
    from .ontology_orchestrator import intake
    return _ontology_agent_call(intake, payload)


@router.post("/ontology-agents/review", dependencies=[Depends(graph_read_identity)])
def ontology_agent_review(payload: dict[str, Any]) -> dict:
    from .ontology_orchestrator import structure_review
    return _ontology_agent_call(structure_review, payload)


@router.post("/ontology-agents/bridge-plan", dependencies=[Depends(graph_read_identity)])
def ontology_agent_bridge_plan(payload: dict[str, Any]) -> dict:
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
    payload = payload.model_dump()
    message = " ".join(str(payload.get("message") or "").split())
    if not message:
        raise HTTPException(status_code=422, detail="message is required")
    return {"status": "ok", "valid": True, "session_id": payload.get("session_id"), "graph_context_present": bool(payload.get("graph_context"))}


@router.post("/chat", dependencies=[Depends(graph_read_identity)])
async def companion_chat(payload: ChatRequest, request: Request) -> dict:
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
        # History supports follow-up retrieval only; graph evidence remains the
        # answer authority and memory text cannot authorize tools or writes.
        query = message
        if len(message.split()) <= 4:
            prior = next((item['text'] for item in context.get('messages', []) if item.get('role') == 'user'), '')
            if prior:
                query = f'{str(prior)[:1000]} {message}'
        async with asyncio.timeout(float(os.getenv('COMPANION_RETRIEVAL_TIMEOUT_SECONDS', '15')) + 5):
            result = await companion.ask(query, headers=headers, ontology_id=(payload.get('graph_context') or {}).get('ontology', ''))
        if (not isinstance(result, dict) or not isinstance(result.get('response'), str)
                or not isinstance(result.get('evidence'), list) or not isinstance(result.get('sources'), list)
                or not isinstance(result.get('answerable'), bool)):
            raise RuntimeError('Knowledge companion returned an invalid evidence response')
        await run_in_threadpool(AgentMemoryService.record_chat_turn, session_id=memory_key,
            user_message=message, assistant_response=result['response'])
        await _agent_io(_finish_observation,
            observation,
            observed_at,
            status="completed",
            evidence_count=len(result.get("evidence") or []),
        )
        return {**result, 'run_id': observation['run_id'], 'telemetry_run_id': observation['run_id'], 'session_id': session['session_id'], 'session_expires_at': session['expires_at'],
                'session_idle_seconds': int(os.getenv('AGENT_SESSION_IDLE_SECONDS', '1800')), 'mode': 'evidence-grounded'}
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
    await _agent_io(companion_job_store.put, job_id, record)
    return {"status": "completed", "execution_mode": 'synchronous', "job_id": job_id, "poll_endpoint": f"/api/v1/chat/jobs/{job_id}", "session_id": response["session_id"]}


@router.get("/chat/jobs/{job_id}", dependencies=[Depends(graph_read_identity)])
def companion_job_status(job_id: str, request: Request) -> dict:
    record = companion_job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Chat job not found")
    if record.get('owner') != sessions.owner(request, graph_read_identity(request)):
        raise HTTPException(403, 'Chat job belongs to another identity')
    sessions.open_session(request, graph_read_identity(request), record['session_id'])
    return {key: value for key, value in record.items() if key != 'owner'}


@router.get("/chat/health")
@router.get("/chat/status")
def companion_health() -> dict:
    return {"status": "ok", "service": "knowledge-companion", "mode": "ontology-search", "streaming": True, 'incremental_generation': False, 'job_execution': 'synchronous', "fail_closed": True}


@router.get("/chat/capabilities")
def companion_capabilities() -> dict:
    return {"name": "knowledge-companion", "mode": "ontology-search", "operations": ["validate", "ask", "stream", "job", "sample-queries"], 'stream_mode': 'completed-response-events', 'job_execution': 'synchronous', "evidence_required": True, 'instance_comparison': False, 'change_impact_analysis': False}


@router.post("/chat-stream", dependencies=[Depends(graph_read_identity)])
async def companion_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    response = await companion_chat(payload, request)

    async def events():
        yield f"data: {json.dumps({'token': response['response']})}\n\n"
        yield f"data: {json.dumps({'evidence': response['evidence'], 'sources': response['sources'], 'answerable': response['answerable']})}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={'X-Session-ID': response['session_id'], 'X-Session-Expires-At': response['session_expires_at']})

@router.post("/plans")
def plan(payload: dict[str, Any]) -> dict:
    try:
        agent, tool = catalog.item("agents", str(payload["agent_id"])), catalog.item("tools", str(payload["tool_id"]))
        if tool["id"] not in agent.get("tools", []): raise ValueError("Tool is not allowlisted for this agent")
        requires_approval = bool(agent.get("approval_required") or tool.get("mutates") or tool["id"] in APPROVAL_TOKENS or payload.get("approval_required"))
        return {"valid": True, "agent": agent["id"], "tool": tool, "requires_approval": requires_approval}
    except (KeyError, ValueError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/workflow-plans")
def workflow_plan(payload: dict[str, Any]) -> dict:
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
    if tool.get("transport") != "openapi":
        raise HTTPException(status_code=501, detail="This transport is catalogued but not HTTP-executable")
    try:
        path = _render(str(tool["path"]), inputs)
        endpoint = _base(tool["service"]) + path
        headers = downstream_headers(request, endpoint, tool=tool)
        inputs = downstream_inputs(tool, inputs, approved_by)
        async with httpx.AsyncClient(timeout=float(os.getenv("AGENTIC_TOOL_TIMEOUT_SECONDS", "30"))) as client:
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
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail="Downstream tool request failed; inspect service status before retrying") from exc


@router.post('/runs')
async def run(payload: dict[str, Any], request: Request) -> dict:
    planned = plan(payload)
    if planned['requires_approval']:
        approval_identity(request, payload, token_env='AGENTIC_APPROVAL_TOKEN')
    else:
        graph_read_identity(request)
    observation, started = await _agent_io(telemetry.start, operation='tool', request_id=getattr(request.state, 'request_id', ''))
    try:
        async with asyncio.timeout(float(os.getenv('AGENTIC_RUN_TIMEOUT_SECONDS', '300'))):
            result = await _dispatch(payload, request)
        await _agent_io(_tool_span, observation, tool_id=result['tool_id'], attempt=1, status='completed', duration_ms=(time.perf_counter()-started)*1000)
        await _agent_io(_finish_observation, observation, started, status='completed')
        return {**result, 'run_id': observation['run_id'], 'telemetry_run_id': observation['run_id']}
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
async def run_workflow(payload: dict[str, Any], request: Request) -> dict:
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
        retries_by_step = []
        for step in workflow['steps']:
            retries = int(step.get('retries', 0))
            if not 0 <= retries <= 5:
                raise ValueError('Workflow retries must be between zero and five')
            retries_by_step.append(retries)
        timeout = float(os.getenv('AGENTIC_RUN_TIMEOUT_SECONDS', '300'))
        run_id = f'run-{uuid4()}'
        request_id = getattr(request.state, 'request_id', '')
        observation, observed_at = await _agent_io(telemetry.start, operation='workflow', request_id=request_id, workflow_id=workflow['id'], workflow_run_id=run_id)
        record = {'owner': sessions.owner(request, actor), 'run_id': run_id, 'telemetry_run_id': observation['run_id'], 'workflow_id': workflow['id'], 'request_id': request_id,
                  'status': 'running', 'started_at': _now(), 'updated_at': _now(),
                  'deadline_at': (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat(), 'traces': []}
        await _agent_io(workflow_store.put, run_id, record)
        async with asyncio.timeout(timeout):
            for index, step in enumerate(workflow['steps']):
                active_step, attempt = step, 0
                inputs = _resolve_inputs(requested[index] if requested is not None else payload.get('inputs', {}), record['traces'])
                command = {**step, 'approval_required': approved_workflow or step.get('approval_required', False),
                           'inputs': inputs, 'approved_by': payload.get('approved_by'), 'approval_token': payload.get('approval_token')}
                tool = planned['steps'][index]['tool']
                while True:
                    attempt += 1
                    tool_started = time.perf_counter()
                    try:
                        dispatched_mutation = bool(tool.get('mutates'))
                        result = await _dispatch(command, request)
                        duration = (time.perf_counter() - tool_started)*1000
                        record['traces'].append({'sequence': index+1, 'tool_id': step['tool_id'], 'attempt': attempt, 'status': 'completed', 'duration_ms': round(duration, 2), 'result': result.get('result', {})})
                        await _agent_io(_tool_span, observation, tool_id=step['tool_id'], attempt=attempt, status='completed', duration_ms=duration)
                        record['updated_at'] = _now()
                        await _agent_io(workflow_store.put, run_id, record)
                        dispatched_mutation = False
                        active_step = None
                        break
                    except HTTPException as exc:
                        await _agent_io(_tool_span, observation, tool_id=step['tool_id'], attempt=attempt, status='failed', duration_ms=(time.perf_counter()-tool_started)*1000, error_type=type(exc).__name__)
                        if tool_retry_allowed(tool, attempt=attempt, retries=retries_by_step[index], status_code=exc.status_code):
                            await asyncio.sleep(min(attempt, 5))
                            continue
                        raise
        record.update(status='completed', finished_at=_now(), updated_at=_now())
        await _agent_io(workflow_store.put, run_id, record)
        await _agent_io(_finish_observation, observation, observed_at, status='completed')
        return {key: value for key, value in record.items() if key != 'owner'}
    except BaseException as exc:
        status = 'interrupted' if isinstance(exc, asyncio.CancelledError) else 'timed_out' if isinstance(exc, TimeoutError) else 'failed'
        if record is not None:
            record.update(status=status, finished_at=_now(), updated_at=_now(), error_type=type(exc).__name__, reconciliation_required=dispatched_mutation)
            if active_step:
                record['traces'].append({'sequence': len(record['traces'])+1, 'tool_id': active_step['tool_id'], 'attempt': attempt, 'status': status, 'error_type': type(exc).__name__})
            # Persist state and telemetry independently. A DB outage must not
            # replace the original exception; deadline-based reads expose an
            # interrupted process even if final persistence could not succeed.
            try:
                await _agent_io(workflow_store.put, record['run_id'], record)
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
        if isinstance(exc, (KeyError, ValueError, TypeError)):
            raise HTTPException(422, str(exc), headers={'X-DEPO-Run-ID': record['run_id']} if record else None) from exc
        if isinstance(exc, TimeoutError):
            raise HTTPException(504, 'Workflow deadline exceeded; inspect run state before retrying', headers={'X-DEPO-Run-ID': record['run_id']} if record else None) from exc
        if isinstance(exc, HTTPException) and record:
            exc.headers = {**(exc.headers or {}), 'X-DEPO-Run-ID': record['run_id']}
        if isinstance(exc, (HTTPException, asyncio.CancelledError)) or not isinstance(exc, Exception):
            raise
        raise HTTPException(503, 'Workflow execution failed; inspect run state before retrying', headers={'X-DEPO-Run-ID': record['run_id']} if record else None) from exc


@router.get("/workflow-runs/{run_id}")
def workflow_run(run_id: str, request: Request) -> dict:
    record = workflow_store.get(run_id)
    if not record: raise HTTPException(404, "Workflow run not found")
    from backend.depo_platform.authorization import service_write_identity
    try:
        service_write_identity(request, token_env='AGENTIC_APPROVAL_TOKEN', default_actor='agent-supervisor')
    except HTTPException:
        actor = graph_read_identity(request)
        if not record.get('owner') or record['owner'] != sessions.owner(request, actor):
            raise HTTPException(403, 'Workflow belongs to another identity or requires supervisory access')
    if record.get('status') == 'running' and record.get('deadline_at') and datetime.now(timezone.utc) >= datetime.fromisoformat(record['deadline_at']):
        # A process may die before writing its terminal state. This projection
        # does not overwrite a concurrently completing run or repeat its writes.
        return {**{key: value for key, value in record.items() if key != 'owner'}, 'status': 'interrupted', 'reconciliation_required': True,
                'error_type': 'ExecutionDeadlineElapsed', 'state_source': 'deadline_projection'}
    return {key: value for key, value in record.items() if key != 'owner'}


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
        async with httpx.AsyncClient(timeout=10) as client:
            for tool in catalog.read()["tools"]:
                if tool.get("transport") != "openapi": continue
                service = str(tool["service"])
                if service in unavailable:
                    continue
                if service not in documents:
                    try:
                        response = await client.get(_base(service).removesuffix("/api/v1") + "/openapi.json")
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
