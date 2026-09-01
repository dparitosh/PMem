"""Catalog and bounded execution for independently extensible agents/tools."""
from __future__ import annotations
import base64, binascii, json, os
from pathlib import Path
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException

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
async def run(payload: dict[str, Any]) -> dict:
    plan_result = plan(payload)
    if plan_result["requires_approval"] and not payload.get("approved_by"):
        raise HTTPException(status_code=409, detail="approved_by is required for a mutating agent action")
    tool, inputs = plan_result["tool"], dict(payload.get("inputs") or {})
    if tool.get("transport") != "openapi":
        raise HTTPException(status_code=501, detail="This transport is catalogued but not HTTP-executable")
    path = _render(str(tool["path"]), inputs)
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("AGENTIC_TOOL_TIMEOUT_SECONDS", "30"))) as client:
            if tool.get("input_kind") == "multipart":
                form, files = _multipart(inputs)
                response = await client.request(tool["method"], _base(tool["service"]) + path, data=form, files=files)
            elif tool.get("input_kind") == "form":
                response = await client.request(tool["method"], _base(tool["service"]) + path, data=inputs)
            else:
                response = await client.request(tool["method"], _base(tool["service"]) + path, params=inputs if tool["method"] == "GET" else None, json=None if tool["method"] == "GET" else inputs)
            response.raise_for_status()
        return {"agent_id": plan_result["agent"], "tool_id": tool["id"], "approved_by": payload.get("approved_by"), "result": response.json()}
    except (httpx.HTTPError, ValueError) as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
