"""Catalog and bounded execution for independently extensible agents/tools."""
from __future__ import annotations
import base64, binascii, json, os
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from backend.mesh_store import PostgresRegistry
from .companion import companion
from .transport_auth import APPROVAL_TOKENS, downstream_headers, downstream_inputs
from .oslc_graph_rag import oslc_graph_rag
from .dt_requirements_adapter import assess_manifest
from .dt_gateway import execute_current_plan
from .dt_bindings import extend_catalog, capabilities as dt_capabilities

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
    try: return path.format(**values)
    except KeyError as exc: raise ValueError(f"Missing path parameter: {exc.args[0]}") from exc

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
              "execution_scope": "current_plan", "started_at": _now()}
    dt_run_store.put(run_id, record)
    try:
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
    record["finished_at"] = _now()
    return dt_run_store.put(run_id, record)


@router.get("/integrations/dt-requirements-design/runs/{run_id}")
def dt_run_status(run_id: str, request: Request) -> dict:
    from backend.depo_platform.authorization import service_write_identity
    service_write_identity(request, token_env="AGENTIC_APPROVAL_TOKEN", default_actor="dt-agent")
    record = dt_run_store.get(run_id)
    if not record:
        raise HTTPException(404, "DT run not found")
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


_COMPANION_PROMPTS = [
    "Show MBSE to EBOM traceability for the Variable Speed Drive",
    "Compare EBOM and MBOM for 5 HP MOTOR ASSEMBLY",
    "Show the bill of process for MOTOR COVER",
    "Show requirements linked to the Variable Speed Drive",
    "Analyse change impact if ROTOR SHAFT tolerance is modified",
]


@router.get("/chat/sample-queries")
def companion_sample_queries() -> dict:
    return {"queries": _COMPANION_PROMPTS, "data_available": True, "mode": "evidence-grounded"}


@router.post("/chat/validate", dependencies=[Depends(graph_read_identity)])
def companion_validate(payload: dict[str, Any]) -> dict:
    message = " ".join(str(payload.get("message") or "").split())
    if not message:
        raise HTTPException(status_code=422, detail="message is required")
    return {"status": "ok", "valid": True, "session_id": payload.get("session_id"), "graph_context_present": bool(payload.get("graph_context"))}


@router.post("/chat", dependencies=[Depends(graph_read_identity)])
async def companion_chat(payload: dict[str, Any], request: Request) -> dict:
    message = " ".join(str(payload.get("message") or "").split())
    if not message:
        raise HTTPException(status_code=422, detail="message is required")
    try:
        headers = downstream_headers(request, companion._graph_root(), graph_read=True)
        result = await companion.ask(message, headers=headers)
        return {"session_id": str(payload.get("session_id") or uuid4()), **result, "mode": "evidence-grounded"}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat/jobs", status_code=202, dependencies=[Depends(graph_read_identity)])
async def companion_job(payload: dict[str, Any], request: Request) -> dict:
    response = await companion_chat(payload, request)
    job_id = f"companion-{uuid4()}"
    record = {"job_id": job_id, "status": "completed", "session_id": response["session_id"], "response": response["response"], "answerable": response["answerable"], "evidence": response["evidence"], "sources": response["sources"], "created_at": _now(), "finished_at": _now()}
    companion_job_store.put(job_id, record)
    return {"status": "accepted", "job_id": job_id, "poll_endpoint": f"/api/v1/chat/jobs/{job_id}", "session_id": response["session_id"]}


@router.get("/chat/jobs/{job_id}", dependencies=[Depends(graph_read_identity)])
def companion_job_status(job_id: str) -> dict:
    record = companion_job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Chat job not found")
    return record


@router.get("/chat/health")
@router.get("/chat/status")
def companion_health() -> dict:
    return {"status": "ok", "service": "knowledge-companion", "mode": "evidence-grounded", "streaming": True, "fail_closed": True}


@router.get("/chat/capabilities")
def companion_capabilities() -> dict:
    return {"name": "knowledge-companion", "mode": "evidence-grounded", "operations": ["validate", "ask", "stream", "job", "sample-queries"], "evidence_required": True}


@router.post("/chat-stream", dependencies=[Depends(graph_read_identity)])
async def companion_stream(payload: dict[str, Any], request: Request) -> StreamingResponse:
    response = await companion_chat(payload, request)

    async def events():
        yield f"data: {json.dumps({'token': response['response']})}\n\n"
        yield f"data: {json.dumps({'evidence': response['evidence'], 'sources': response['sources'], 'answerable': response['answerable']})}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={'X-Session-ID': response['session_id']})

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
    if len(parts) < 4 or parts[2] != "result":
        raise ValueError("workflow reference must use $steps.N.result[.field]")
    try:
        current: Any = traces[int(parts[1]) - 1]["result"]
        for part in parts[3:]: current = current[part]
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
    try: content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc: raise ValueError("file.content_base64 must be valid base64") from exc
    if len(content) > int(os.getenv("AGENTIC_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))):
        raise ValueError("Agent file exceeds AGENTIC_MAX_UPLOAD_BYTES")
    form = dict(inputs.get("form") or {})
    return form, {file_field: (str(upload["filename"]), content, str(upload.get("content_type") or "application/octet-stream"))}

@router.post("/runs")
async def run(payload: dict[str, Any], request: Request) -> dict:
    plan_result = plan(payload)
    approved_by = None
    if plan_result["requires_approval"]:
        approved_by = approval_identity(request, payload, token_env="AGENTIC_APPROVAL_TOKEN")
    else:
        graph_read_identity(request)
    tool, inputs = plan_result["tool"], dict(payload.get("inputs") or {})
    if tool.get("transport") != "openapi":
        raise HTTPException(status_code=501, detail="This transport is catalogued but not HTTP-executable")
    try:
        path = _render(str(tool["path"]), inputs)
        endpoint = _base(tool["service"]) + path
        headers = downstream_headers(request, endpoint, graph_read=tool["service"] in {"graph", "agentic"})
        inputs = downstream_inputs(tool, inputs, approved_by)
        async with httpx.AsyncClient(timeout=float(os.getenv("AGENTIC_TOOL_TIMEOUT_SECONDS", "30"))) as client:
            if tool.get("input_kind") == "multipart":
                form, files = _multipart(inputs, 'artifact' if tool['id'] == 'ontology.register' else 'file')
                response = await client.request(tool["method"], endpoint, headers=headers, data=form, files=files)
            elif tool.get("input_kind") == "form":
                response = await client.request(tool["method"], endpoint, headers=headers, data=inputs)
            else:
                response = await client.request(tool["method"], endpoint, headers=headers, params=inputs if tool["method"] == "GET" else None, json=None if tool["method"] == "GET" else inputs)
            response.raise_for_status()
        if tool["id"] == "ontology.export":
            result = {"content_base64": base64.b64encode(response.content).decode("ascii"),
                      "content_type": response.headers.get("content-type", "application/octet-stream")}
        else:
            result = response.json()
        return {"agent_id": plan_result["agent"], "tool_id": tool["id"], "approved_by": approved_by, "result": result}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail="Downstream tool request failed; inspect service status before retrying") from exc


@router.post("/workflow-runs")
async def run_workflow(payload: dict[str, Any], request: Request) -> dict:
    """Execute an ordered declarative workflow and persist its trace.

    Callers provide ``step_inputs`` indexed from zero.  Values may reference a
    prior result using ``$steps.1.result.some_field``.  Individual step retry
    counts are declared in the workflow manifest, keeping retry behavior out of
    page/UI code.
    """
    try:
        workflow = catalog.item("workflows", str(payload["workflow_id"]))
        planned = workflow_plan(payload)
        approved_workflow = any(step['requires_approval'] for step in planned['steps'])
        if approved_workflow:
            approval_identity(request, payload, token_env="AGENTIC_APPROVAL_TOKEN")
        else:
            graph_read_identity(request)
        requested = list(payload.get("step_inputs") or [])
        if requested and len(requested) != len(workflow.get("steps", [])):
            raise ValueError("step_inputs must contain one entry for each workflow step")
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        record: dict[str, Any] = {"run_id": run_id, "workflow_id": workflow["id"], "status": "running", "started_at": _now(), "traces": []}
        workflow_store.put(run_id, record)
        for index, step in enumerate(workflow["steps"]):
            inputs = _resolve_inputs(requested[index] if requested else payload.get("inputs", {}), record["traces"])
            command = {**step, "approval_required": approved_workflow or step.get('approval_required', False), "inputs": inputs, "approved_by": payload.get("approved_by"), "approval_token": payload.get("approval_token")}
            retries, attempt = max(0, int(step.get("retries", 0))), 0
            while True:
                attempt += 1
                try:
                    result = await run(command, request)
                    record["traces"].append({"sequence": index + 1, "tool_id": step["tool_id"], "attempt": attempt, "status": "completed", "result": result.get("result", {})})
                    workflow_store.put(run_id, record)
                    break
                except HTTPException as exc:
                    # Never blindly repeat a mutating operation after an
                    # uncertain downstream response. Mutation APIs must offer
                    # their own receipt/reconciliation contract first.
                    if attempt <= retries and exc.status_code >= 500 and not step.get('mutates', False):
                        continue
                    record.update({"status": "failed", "finished_at": _now()})
                    record["traces"].append({"sequence": index + 1, "tool_id": step["tool_id"], "attempt": attempt, "status": "failed", "error": str(exc.detail)})
                    workflow_store.put(run_id, record)
                    raise
        record.update({"status": "completed", "finished_at": _now()})
        return workflow_store.put(run_id, record)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/workflow-runs/{run_id}", dependencies=[Depends(graph_read_identity)])
def workflow_run(run_id: str) -> dict:
    record = workflow_store.get(run_id)
    if not record: raise HTTPException(404, "Workflow run not found")
    return record


@router.get("/catalog/validate", dependencies=[Depends(graph_read_identity)])
async def validate_openapi_catalog() -> dict:
    """Compare declarative HTTP tools with their live OpenAPI operations."""
    errors: list[dict[str, str]] = []
    documents: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for tool in catalog.read()["tools"]:
                if tool.get("transport") != "openapi": continue
                service = str(tool["service"])
                if service not in documents:
                    response = await client.get(_base(service).removesuffix("/api/v1") + "/openapi.json")
                    response.raise_for_status(); documents[service] = response.json()
                operation = documents[service].get("paths", {}).get("/api/v1" + tool["path"], {}).get(str(tool["method"]).lower())
                if not operation: errors.append({"tool_id": tool["id"], "error": "operation is absent from live OpenAPI"})
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(503, f"Unable to validate live OpenAPI contracts: {exc}") from exc
    return {"valid": not errors, "errors": errors, "services": sorted(documents)}


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
