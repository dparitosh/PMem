"""Catalog and bounded execution for independently extensible agents/tools."""
from __future__ import annotations
import base64, binascii, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request
from backend.platform.authorization import approval_identity
from backend.mesh_store import SqliteRegistry

router = APIRouter(prefix="/api/v1", tags=["agentic-control-plane"])

class Catalog:
    def __init__(self) -> None:
        configured = os.getenv("AGENTIC_CATALOG_PATH", "")
        self.path = Path(configured) if configured else Path(__file__).with_name("catalog.json")
    def read(self) -> dict[str, Any]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not all(isinstance(data.get(key), list) for key in ("agents", "tools", "mcp_servers", "workflows")):
            raise ValueError("Catalog must define agents, tools, mcp_servers, and workflows lists")
        return data
    def item(self, kind: str, identifier: str) -> dict[str, Any]:
        for value in self.read()[kind]:
            if value.get("id") == identifier: return value
        raise ValueError(f"Unknown {kind[:-1]}: {identifier}")

catalog = Catalog()
workflow_store = SqliteRegistry(Path(os.getenv("AGENTIC_WORKFLOW_STORAGE", Path(__file__).resolve().parents[2] / "data" / "agentic")) / "workflow_runs")
_services = {"ontology": "ONTOLOGY_SERVICE_URL", "graph": "GRAPH_SERVICE_URL", "ingestion": "INGESTION_SERVICE_URL", "oslc": "OSLC_SERVICE_URL", "qif": "QIF_SERVICE_URL", "catalog": "DATA_CATALOG_URL", "data_products": "DATA_PRODUCT_SERVICE_URL"}

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

@router.post("/plans")
def plan(payload: dict[str, Any]) -> dict:
    try:
        agent, tool = catalog.item("agents", str(payload["agent_id"])), catalog.item("tools", str(payload["tool_id"]))
        if tool["id"] not in agent.get("tools", []): raise ValueError("Tool is not allowlisted for this agent")
        requires_approval = bool(agent.get("approval_required") or tool.get("mutates"))
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

def _multipart(inputs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, tuple[str, bytes, str]]]:
    upload = dict(inputs.get("file") or {})
    encoded = str(upload.get("content_base64") or "")
    if not upload.get("filename") or not encoded:
        raise ValueError("Multipart tools require inputs.file.filename and inputs.file.content_base64")
    try: content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc: raise ValueError("file.content_base64 must be valid base64") from exc
    if len(content) > int(os.getenv("AGENTIC_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))):
        raise ValueError("Agent file exceeds AGENTIC_MAX_UPLOAD_BYTES")
    form = dict(inputs.get("form") or {})
    return form, {"file": (str(upload["filename"]), content, str(upload.get("content_type") or "application/octet-stream"))}

@router.post("/runs")
async def run(payload: dict[str, Any], request: Request) -> dict:
    plan_result = plan(payload)
    approved_by = None
    if plan_result["requires_approval"]:
        approved_by = approval_identity(request, payload, token_env="AGENTIC_APPROVAL_TOKEN")
    tool, inputs = plan_result["tool"], dict(payload.get("inputs") or {})
    if tool.get("transport") != "openapi":
        raise HTTPException(status_code=501, detail="This transport is catalogued but not HTTP-executable")
    try:
        path = _render(str(tool["path"]), inputs)
        async with httpx.AsyncClient(timeout=float(os.getenv("AGENTIC_TOOL_TIMEOUT_SECONDS", "30"))) as client:
            if tool.get("input_kind") == "multipart":
                form, files = _multipart(inputs)
                response = await client.request(tool["method"], _base(tool["service"]) + path, data=form, files=files)
            elif tool.get("input_kind") == "form":
                response = await client.request(tool["method"], _base(tool["service"]) + path, data=inputs)
            else:
                response = await client.request(tool["method"], _base(tool["service"]) + path, params=inputs if tool["method"] == "GET" else None, json=None if tool["method"] == "GET" else inputs)
            response.raise_for_status()
        return {"agent_id": plan_result["agent"], "tool_id": tool["id"], "approved_by": approved_by, "result": response.json()}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc


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
        requested = list(payload.get("step_inputs") or [])
        if requested and len(requested) != len(workflow.get("steps", [])):
            raise ValueError("step_inputs must contain one entry for each workflow step")
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        record: dict[str, Any] = {"run_id": run_id, "workflow_id": workflow["id"], "status": "running", "started_at": _now(), "traces": []}
        workflow_store.put(run_id, record)
        for index, step in enumerate(workflow["steps"]):
            inputs = _resolve_inputs(requested[index] if requested else payload.get("inputs", {}), record["traces"])
            command = {**step, "inputs": inputs, "approved_by": payload.get("approved_by"), "approval_token": payload.get("approval_token")}
            retries, attempt = max(0, int(step.get("retries", 0))), 0
            while True:
                attempt += 1
                try:
                    result = await run(command, request)
                    record["traces"].append({"sequence": index + 1, "tool_id": step["tool_id"], "attempt": attempt, "status": "completed", "result": result.get("result", {})})
                    workflow_store.put(run_id, record)
                    break
                except HTTPException as exc:
                    if attempt <= retries and exc.status_code >= 500:
                        continue
                    record.update({"status": "failed", "finished_at": _now()})
                    record["traces"].append({"sequence": index + 1, "tool_id": step["tool_id"], "attempt": attempt, "status": "failed", "error": str(exc.detail)})
                    workflow_store.put(run_id, record)
                    raise
        record.update({"status": "completed", "finished_at": _now()})
        return workflow_store.put(run_id, record)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/workflow-runs/{run_id}")
def workflow_run(run_id: str) -> dict:
    record = workflow_store.get(run_id)
    if not record: raise HTTPException(404, "Workflow run not found")
    return record


@router.get("/catalog/validate")
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
