"""Translate the existing Depo frontend contract to an exported IIF runtime.

This module is a router factory, not a second FastAPI application. Mount the
returned router on the IIF-exported ``app`` without an additional prefix.
"""

from __future__ import annotations

import importlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field


_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_ONTOLOGY_EXTENSIONS = {".owl", ".rdf", ".xml", ".ttl", ".nt", ".n3", ".jsonld"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_. -]{1,128}$")


class InputsRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(InputsRequest):
    workflow_id: str


class OpenAPIImportRequest(BaseModel):
    document: dict[str, Any]
    source_name: str = ""


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _runtime_root() -> Path:
    configured = os.getenv("DEPO_IIF_RUNTIME_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    try:
        from bootstrap import bootstrap_runtime_root

        return Path(bootstrap_runtime_root()).resolve()
    except ImportError:
        return Path.cwd().resolve()


def _agent_dir() -> Path:
    return _runtime_root() / "AgentsRegistry" / "Agents"


def _workflow_dir() -> Path:
    configured = os.getenv("DEPO_IIF_WORKFLOW_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else _runtime_root() / "storage"


def _upload_dir() -> Path:
    configured = os.getenv("DEPO_IIF_UPLOAD_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else _runtime_root() / "Uploaded_files" / "ontology"


def _read_agent_specs() -> list[dict[str, Any]]:
    directory = _agent_dir()
    if not directory.is_dir():
        return []
    specs = []
    seen = set()
    for path in sorted(directory.glob("*.yaml")):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise HTTPException(status_code=500, detail=f"Invalid agent registry file {path.name}: {exc}") from exc
        if not isinstance(value, dict) or not str(value.get("name", "")).strip():
            raise HTTPException(status_code=500, detail=f"Invalid agent registry file: {path.name}")
        name = str(value["name"]).strip()
        if name in seen:
            raise HTTPException(status_code=500, detail=f"Duplicate agent name: {name}")
        seen.add(name)
        specs.append(value)
    return specs


def _tool_policy(tool: dict[str, Any]) -> tuple[str, str, bool]:
    name = str(tool.get("name", "")).lower()
    tool_type = str(tool.get("type", "python")).lower()
    if tool_type == "mcp":
        return "graph", "dynamic_mcp", True
    if name == "ontology_export":
        return "ontology", "filesystem_write", True
    if name.startswith("external_"):
        return "integration", "external_read", False
    return "ontology", "read_only", False


def _catalogs() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    agents = []
    tools_by_name: dict[str, dict[str, Any]] = {}
    invalid = []
    for spec in _read_agent_specs():
        tool_names = [str(tool.get("name", "")) for tool in spec.get("tools", []) if isinstance(tool, dict)]
        agents.append(
            {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "tools": tool_names,
                "can_handoff_to": spec.get("can_handoff_to", []),
            }
        )
        for tool in spec.get("tools", []):
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            name = str(tool["name"])
            category, side_effect, approval = _tool_policy(tool)
            entry = tools_by_name.setdefault(
                name,
                {
                    "name": name,
                    "description": tool.get("description", ""),
                    "type": tool.get("type", "python"),
                    "module": tool.get("module", ""),
                    "object": tool.get("object", ""),
                    "category": category,
                    "side_effect": side_effect,
                    "requires_approval": approval,
                    "agents": [],
                },
            )
            entry["agents"].append(spec["name"])
            module_name, object_name = entry["module"], entry["object"]
            if module_name and object_name:
                try:
                    module = importlib.import_module(module_name)
                    getattr(module, object_name)
                except Exception as exc:
                    invalid.append({"name": name, "error": str(exc)})
    return agents, list(tools_by_name.values()), invalid


def _load_workflow(workflow_id: str) -> list[dict[str, Any]]:
    workflow_id = workflow_id.strip()
    if not _SAFE_ID.fullmatch(workflow_id) or ".." in workflow_id:
        raise HTTPException(status_code=400, detail="Invalid workflow_id")
    directory = _workflow_dir()
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"Workflow directory not found: {directory}")
    requested = workflow_id.casefold()
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidates: list[tuple[str, Any]] = [(path.stem, raw)]
        if isinstance(raw, dict):
            if isinstance(raw.get("steps"), list):
                candidates.append((str(raw.get("id") or raw.get("name") or path.stem), raw["steps"]))
            candidates.extend((str(key), value) for key, value in raw.items() if isinstance(value, list))
        for candidate_id, candidate in candidates:
            if candidate_id.casefold() != requested:
                continue
            plan = candidate.get("steps") if isinstance(candidate, dict) else candidate
            if not isinstance(plan, list) or not all(isinstance(step, dict) for step in plan):
                raise HTTPException(status_code=400, detail=f"Workflow {workflow_id} has an invalid plan")
            return _validate_plan(plan)
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


def _validate_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known = {spec["name"] for spec in _read_agent_specs()}
    normalized = []
    aliases = set()
    for index, raw_step in enumerate(plan):
        step = dict(raw_step)
        agent = str(step.get("agent", "")).strip()
        alias = str(step.get("alias", "")).strip()
        if agent not in known:
            raise HTTPException(status_code=400, detail=f"Workflow step {index} references unknown agent: {agent}")
        if not alias or alias in aliases:
            raise HTTPException(status_code=400, detail=f"Workflow step {index} has a missing or duplicate alias")
        aliases.add(alias)
        step.setdefault("purpose", "")
        step.setdefault("inputs", ["User Query"] if index == 0 else [normalized[-1]["alias"]])
        normalized.append(step)
    if not normalized:
        raise HTTPException(status_code=400, detail="Workflow plan is empty")
    return normalized


def _query(inputs: dict[str, Any]) -> str:
    direct = inputs.get("query")
    if isinstance(direct, str) and direct.strip():
        remainder = {key: value for key, value in inputs.items() if key != "query"}
        return direct.strip() if not remainder else f"{direct.strip()}\nInputs: {json.dumps(remainder, ensure_ascii=False)}"
    return json.dumps(inputs, ensure_ascii=False)


async def _workflow_execute(query: str, plan: list[dict[str, Any]]) -> Any:
    try:
        from app.api.workflow.Workflow import workflow_execute
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="IIF workflow runtime is not available") from exc
    return await workflow_execute(query, plan)


async def _authorize(authorization: str | None = Header(default=None)) -> None:
    if not _bool_env("DEPO_IIF_ADAPTER_SECURITY_ENABLED"):
        return
    expected = os.getenv("DEPO_IIF_ADAPTER_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Adapter security is enabled but no token is configured")
    supplied = authorization or ""
    if not hmac.compare_digest(supplied, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


def _openapi_catalog(payload: OpenAPIImportRequest) -> dict[str, Any]:
    document = payload.document
    version = str(document.get("openapi", ""))
    if not version.startswith("3."):
        raise HTTPException(status_code=400, detail="Only OpenAPI 3.x JSON documents are supported")
    paths = document.get("paths", {})
    if not isinstance(paths, dict):
        raise HTTPException(status_code=400, detail="OpenAPI paths must be an object")
    operations = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": str(path),
                    "operation_id": operation.get("operationId", ""),
                    "summary": operation.get("summary", ""),
                }
            )
    schemas = document.get("components", {}).get("schemas", {}) if isinstance(document.get("components", {}), dict) else {}
    info = document.get("info", {}) if isinstance(document.get("info", {}), dict) else {}
    return {
        "title": info.get("title") or payload.source_name or "OpenAPI service",
        "version": info.get("version", ""),
        "source_name": payload.source_name,
        "summary": {"operations": len(operations), "schemas": len(schemas) if isinstance(schemas, dict) else 0},
        "operations": operations,
        "dynamic_tools_created": False,
    }


def create_depo_compat_router() -> APIRouter:
    """Create routes matching ``frontend/src/services/agenticApi.js``."""
    router = APIRouter(dependencies=[Depends(_authorize)])

    @router.get("/health", tags=["Depo compatibility"])
    async def health() -> dict[str, Any]:
        agents, tools, invalid = _catalogs()
        return {
            "status": "ok" if not invalid else "degraded",
            "service": "iif-depo-ontology-adapter",
            "agents": len(agents),
            "tools": len(tools),
            "invalid_exports": len(invalid),
        }

    @router.get("/api/v1/agents", tags=["Depo compatibility"])
    async def list_agents() -> dict[str, Any]:
        agents, _, _ = _catalogs()
        return {"agents": agents}

    @router.get("/api/v1/tools", tags=["Depo compatibility"])
    async def list_tools() -> dict[str, Any]:
        _, tools, invalid = _catalogs()
        return {"tools": tools, "invalid_exports": invalid}

    @router.post("/api/v1/openapi/import", tags=["Depo compatibility"])
    async def inspect_openapi(payload: OpenAPIImportRequest) -> dict[str, Any]:
        return _openapi_catalog(payload)

    @router.post("/api/v1/agents/{agent_name}/run", tags=["Depo compatibility"])
    async def run_agent(agent_name: str, payload: InputsRequest) -> dict[str, Any]:
        specs = {spec["name"]: spec for spec in _read_agent_specs()}
        if agent_name not in specs:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")
        alias = re.sub(r"[^A-Za-z0-9_]+", "_", agent_name).strip("_").lower() or "agent"
        plan = [{"agent": agent_name, "alias": alias, "purpose": specs[agent_name].get("description", ""), "inputs": ["User Query"]}]
        result = await _workflow_execute(_query(payload.inputs), plan)
        return {"status": "completed", "agent": agent_name, "result": result}

    @router.post("/api/v1/workflows/run", tags=["Depo compatibility"])
    async def run_workflow(payload: WorkflowRunRequest) -> dict[str, Any]:
        plan = _load_workflow(payload.workflow_id)
        result = await _workflow_execute(_query(payload.inputs), plan)
        return {"status": "completed", "workflow_id": payload.workflow_id, "result": result}

    @router.post("/api/v1/ontology/files", tags=["Depo compatibility"])
    async def upload_ontology(file: UploadFile = File(...)) -> dict[str, Any]:
        original = Path(file.filename or "").name
        suffix = Path(original).suffix.lower()
        if suffix not in _ONTOLOGY_EXTENSIONS:
            await file.close()
            raise HTTPException(status_code=400, detail=f"Unsupported ontology extension: {suffix}")
        try:
            maximum = int(os.getenv("DEPO_IIF_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="DEPO_IIF_MAX_UPLOAD_BYTES must be an integer") from exc
        if maximum <= 0:
            raise HTTPException(status_code=500, detail="DEPO_IIF_MAX_UPLOAD_BYTES must be positive")
        destination_dir = _upload_dir()
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{uuid4().hex}_{original}"
        total = 0
        try:
            with destination.open("xb") as target:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > maximum:
                        raise HTTPException(status_code=413, detail="Ontology upload exceeds configured size limit")
                    target.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {"status": "uploaded", "filename": original, "path": str(destination), "size": total}

    return router


__all__ = ["create_depo_compat_router"]
