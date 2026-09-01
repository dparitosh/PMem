"""OpenAPI contract for the independently deployable QIF workflow service."""
from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .agent_registry import registry
from .models import QifActionResponse, QifAgentsResponse, QifCatalogResponse, QifHealthResponse, QifTaskListResponse, QifTaskPreviewResponse, QifTaskResponse
from .task_service import task_service
from .standards import detect_standard, get_standard, public_standards

router = APIRouter(prefix="/qif", tags=["qif"])
_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE_ROOT = _ROOT / "docs" / "xsd"
_MAX_FILES = 40
_MAX_FILE_BYTES = 10 * 1024 * 1024


def _reference_files() -> list[Path]:
    return sorted(_REFERENCE_ROOT.rglob("*.xsd")) if _REFERENCE_ROOT.exists() else []


def _validate_metadata(name: str, prefix: str) -> None:
    if not name or len(name) > 100:
        raise HTTPException(status_code=422, detail="ontology_name must be 1-100 characters")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,49}", prefix or ""):
        raise HTTPException(status_code=422, detail="prefix must start with a letter and contain only letters, numbers, and underscores")


def _start(paths: list[Path], name: str, prefix: str, description: str, source: str, standard_id: str = "generic-xsd") -> dict:
    _validate_metadata(name, prefix)
    task = task_service.create(source_paths=paths, ontology_name=name, prefix=prefix, description=description, source=source, standard_id=standard_id)
    task_service.submit_prepare(task["task_id"])
    return task_service.get(task["task_id"])


@router.get("/health", response_model=QifHealthResponse, summary="QIF workflow service health")
def health() -> dict:
    return {"status": "ok", "service": "qif-workflow", "reference_available": bool(_reference_files())}


@router.get("/catalog", response_model=QifCatalogResponse, summary="List bundled QIF 3.0 schemas")
def catalog() -> dict:
    files = _reference_files()
    return {"standard": "QIF 3.0", "file_count": len(files), "files": [{"name": path.name, "area": path.parent.name} for path in files]}


@router.get("/schema-sets/standards", summary="List multi-XSD engineering-standard adapter profiles")
def schema_set_standards() -> dict:
    return {"standards": public_standards(), "count": len(public_standards())}


@router.get("/agents", response_model=QifAgentsResponse, summary="List available QIF workflow agents")
def list_agents() -> dict:
    agents = registry.list_agents()
    return {"agents": agents, "count": len(agents)}


@router.post("/agents/refresh", summary="Reload declarative QIF agent definitions")
def refresh_agents() -> dict:
    agents = registry.list_agents()
    return {"reloaded": [agent["name"] for agent in agents], "count": len(agents)}


@router.post("/tasks/reference", response_model=QifTaskResponse, summary="Start granular QIF workflow from the bundled reference")
def start_reference_task(ontology_name: str = Form("QIF 3.0 Ontology"), prefix: str = Form("qif"), description: str = Form("Consolidated ontology generated from the QIF 3.0 schema set.")) -> dict:
    sources = _reference_files()
    if not sources:
        raise HTTPException(status_code=404, detail="Bundled QIF reference schemas are unavailable")
    return _start(sources, ontology_name, prefix, description, "bundled_reference", "qif-3")


@router.post("/schema-sets/upload", response_model=QifTaskResponse, summary="Start a generic multi-XSD engineering-standard workflow")
async def start_schema_set(
    files: Annotated[list[UploadFile], File(description="One or more XSD files for a standard or custom schema set")],
    ontology_name: Annotated[str, Form()], prefix: Annotated[str, Form()] = "",
    standard_id: Annotated[str, Form()] = "auto", description: Annotated[str, Form()] = "",
) -> dict:
    if not files or len(files) > _MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Upload between 1 and {_MAX_FILES} XSD files")
    filenames = [Path(item.filename or "").name for item in files]
    selected = detect_standard(filenames) if standard_id == "auto" else standard_id
    try: profile = get_standard(selected)
    except ValueError as exc: raise HTTPException(422, detail=str(exc)) from exc
    selected_prefix = prefix or profile["prefix"]
    _validate_metadata(ontology_name, selected_prefix)
    with TemporaryDirectory(prefix="schema_set_") as tmp:
        root, paths, names = Path(tmp), [], set()
        for item, filename in zip(files, filenames):
            if not filename.lower().endswith(".xsd"):
                raise HTTPException(422, detail=f"{filename or 'Unnamed file'} is not an XSD file")
            if filename.lower() in names:
                raise HTTPException(422, detail=f"Duplicate filename: {filename}")
            content = await item.read()
            if not content or len(content) > _MAX_FILE_BYTES:
                raise HTTPException(422, detail=f"{filename} is empty or exceeds 10 MB")
            path = root / filename; path.write_bytes(content); names.add(filename.lower()); paths.append(path)
        return _start(paths, ontology_name, selected_prefix, description, "uploaded_schema_set", selected)


@router.post("/tasks/upload", response_model=QifTaskResponse, summary="Start granular QIF workflow from multiple XSD files")
async def start_uploaded_task(files: Annotated[list[UploadFile], File(description="One or more QIF XSD files")], ontology_name: Annotated[str, Form()], prefix: Annotated[str, Form()], description: Annotated[str, Form()] = "") -> dict:
    _validate_metadata(ontology_name, prefix)
    if not files or len(files) > _MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Upload between 1 and {_MAX_FILES} XSD files")
    with TemporaryDirectory(prefix="qif_schema_set_") as tmp:
        root = Path(tmp)
        paths: list[Path] = []
        names: set[str] = set()
        for item in files:
            filename = Path(item.filename or "").name
            if not filename.lower().endswith(".xsd"):
                raise HTTPException(status_code=422, detail=f"{filename or 'Unnamed file'} is not an XSD file")
            if filename.lower() in names:
                raise HTTPException(status_code=422, detail=f"Duplicate filename: {filename}")
            content = await item.read()
            if not content or len(content) > _MAX_FILE_BYTES:
                raise HTTPException(status_code=422, detail=f"{filename} is empty or exceeds 10 MB")
            path = root / filename
            path.write_bytes(content)
            names.add(filename.lower())
            paths.append(path)
        return _start(paths, ontology_name, prefix, description, "uploaded_schema_set", "qif-3")


@router.get("/tasks", response_model=QifTaskListResponse, summary="List recent QIF workflow tasks")
def list_tasks(limit: int = 25) -> dict:
    return {"tasks": task_service.list(max(1, min(limit, 100)))}


@router.get("/tasks/{task_id}", response_model=QifTaskResponse, summary="Get QIF task status and stage events")
def task_status(task_id: str) -> dict:
    return task_service.get(task_id)


@router.get("/tasks/{task_id}/preview", response_model=QifTaskPreviewResponse, summary="Get QIF validation and ontology preview")
def task_preview(task_id: str) -> dict:
    return task_service.preview(task_id)


@router.post("/tasks/{task_id}/commit", response_model=QifActionResponse, summary="Approve and persist a reviewed QIF ontology")
def commit_task(task_id: str) -> dict:
    task = task_service.queue_commit(task_id)
    return {"task_id": task["task_id"], "status": task["status"]}


@router.post("/tasks/{task_id}/cancel", response_model=QifTaskResponse, summary="Cancel a pending QIF workflow")
def cancel_task(task_id: str) -> dict:
    return task_service.cancel(task_id)


@router.post("/tasks/{task_id}/retry-graph", response_model=QifActionResponse, summary="Retry failed graph synchronization")
def retry_graph(task_id: str) -> dict:
    task = task_service.queue_graph_retry(task_id)
    return {"task_id": task["task_id"], "status": task["status"]}


@router.get("/tasks/{task_id}/artifacts/{artifact_path:path}", summary="Download a task-owned QIF artifact")
def task_artifact(task_id: str, artifact_path: str):
    task_dir = task_service._task_dir(task_id).resolve()
    target = (task_dir / artifact_path).resolve()
    if task_dir not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="QIF artifact not found")
    return FileResponse(target, filename=target.name)


# Compatibility aliases for the first QIF UI iteration.
@router.post("/ontology/reference", include_in_schema=False)
def build_reference_ontology(ontology_name: str = Form("QIF 3.0 Ontology"), prefix: str = Form("qif"), description: str = Form("")) -> dict:
    return start_reference_task(ontology_name, prefix, description)


@router.post("/ontology/upload", include_in_schema=False)
async def build_uploaded_ontology(files: Annotated[list[UploadFile], File()], ontology_name: Annotated[str, Form()], prefix: Annotated[str, Form()], description: Annotated[str, Form()] = "") -> dict:
    return await start_uploaded_task(files, ontology_name, prefix, description)
