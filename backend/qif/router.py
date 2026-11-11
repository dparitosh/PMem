"""OpenAPI contract for the independently deployable QIF workflow service."""
from __future__ import annotations

import re
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from .agent_registry import registry
from .instance_checks import UnsupportedInstance, check_instance
from .models import QifActionResponse, QifAgentsResponse, QifCatalogResponse, QifHealthResponse, QifTaskListResponse, QifTaskPreviewResponse, QifTaskResponse
from .task_service import task_service
from .standards import detect_standard, get_standard, public_standards
from backend.depo_platform.authorization import service_write_identity


def _qif_identity(request: Request) -> str:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return "public-read"
    return service_write_identity(request, token_env="ONTOLOGY_APPROVAL_TOKEN", default_actor="qif-workflow")


router = APIRouter(prefix="/qif", tags=["qif"], dependencies=[Depends(_qif_identity)])
_ROOT = Path(__file__).resolve().parents[2]
_configured_reference = os.getenv('QIF_SCHEMA_DIR', '').strip()
_preferred_reference = _ROOT / 'data' / 'QIF3.0-2018' / 'xsd'
_REFERENCE_ROOT = (Path(_configured_reference) if _configured_reference else
                   _preferred_reference if _preferred_reference.is_dir() else _ROOT / 'docs' / 'xsd')
if not _REFERENCE_ROOT.is_absolute():
    _REFERENCE_ROOT = _ROOT / _REFERENCE_ROOT
_MAX_FILES = 40
_MAX_FILE_BYTES = 10 * 1024 * 1024


def _reference_files() -> list[Path]:
    return sorted(_REFERENCE_ROOT.rglob("*.xsd")) if _REFERENCE_ROOT.exists() else []


def _validate_metadata(name: str, prefix: str) -> None:
    if not name or len(name) > 100:
        raise HTTPException(status_code=422, detail="ontology_name must be 1-100 characters")
    if prefix and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,49}", prefix):
        raise HTTPException(status_code=422, detail="prefix must start with a letter and contain only letters, numbers, and underscores")


def _source_prefix(paths: list[Path], requested: str) -> str:
    """Derive a display alias from the actual schema namespace, never a profile label."""
    if requested and requested.strip():
        return requested.strip()
    from defusedxml import ElementTree
    from backend.depo_platform.ontology_namespace import ontology_prefix
    namespaces = set()
    for path in paths:
        try:
            schema = ElementTree.parse(path).getroot()
        except Exception:
            continue  # The existing schema-validation stage reports malformed sources.
        if schema.tag == '{http://www.w3.org/2001/XMLSchema}schema':
            namespace = (schema.get('targetNamespace') or '').strip()
            if namespace:
                namespaces.add(namespace)
    if len(namespaces) > 1:
        raise HTTPException(422, detail='These schemas declare multiple target namespaces. Choose a prefix override for this combined ontology.')
    return ontology_prefix(next(iter(namespaces), ''))


def _start(paths: list[Path], name: str, prefix: str, description: str, source: str, standard_id: str = "generic-xsd") -> dict:
    prefix = _source_prefix(paths, prefix)
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
def start_reference_task(ontology_name: str = Form("QIF 3.0 Ontology"), prefix: str = Form(""), description: str = Form("Consolidated ontology generated from the QIF 3.0 schema set.")) -> dict:
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
    try: get_standard(selected)
    except ValueError as exc: raise HTTPException(422, detail=str(exc)) from exc
    selected_prefix = prefix.strip()
    _validate_metadata(ontology_name, selected_prefix)
    with TemporaryDirectory(prefix="schema_set_") as tmp:
        root, paths, names = Path(tmp), [], set()
        for item, filename in zip(files, filenames):
            if not filename.lower().endswith(".xsd"):
                raise HTTPException(422, detail=f"{filename or 'Unnamed file'} is not an XSD file")
            if filename.lower() in names:
                raise HTTPException(422, detail=f"Duplicate filename: {filename}")
            content = await item.read(_MAX_FILE_BYTES + 1)
            if not content or len(content) > _MAX_FILE_BYTES:
                raise HTTPException(422, detail=f"{filename} is empty or exceeds 10 MB")
            path = root / filename
            await run_in_threadpool(path.write_bytes, content)
            names.add(filename.lower()); paths.append(path)
        return await run_in_threadpool(_start, paths, ontology_name, selected_prefix, description, "uploaded_schema_set", selected)


@router.post("/tasks/upload", response_model=QifTaskResponse, summary="Start granular QIF workflow from multiple XSD files")
async def start_uploaded_task(files: Annotated[list[UploadFile], File(description="One or more QIF XSD files")], ontology_name: Annotated[str, Form()], prefix: Annotated[str, Form()] = "", description: Annotated[str, Form()] = "") -> dict:
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
            content = await item.read(_MAX_FILE_BYTES + 1)
            if not content or len(content) > _MAX_FILE_BYTES:
                raise HTTPException(status_code=422, detail=f"{filename} is empty or exceeds 10 MB")
            path = root / filename
            await run_in_threadpool(path.write_bytes, content)
            names.add(filename.lower())
            paths.append(path)
        return await run_in_threadpool(_start, paths, ontology_name, prefix, description, "uploaded_schema_set", "qif-3")


@router.post("/instances/check", summary="Validate one QIF 3.0 instance against the schema and QIF XSLT checks")
async def check_qif_instance(file: Annotated[UploadFile, File(description="One QIF 3.0 instance document (.xml)")]) -> dict:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".xml"):
        raise HTTPException(status_code=422, detail=f"{filename or 'Unnamed file'} is not an XML file")
    content = await file.read(_MAX_FILE_BYTES + 1)
    if not content or len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=422, detail=f"{filename} is empty or exceeds 10 MB")
    try:
        result = await run_in_threadpool(check_instance, content)
    except UnsupportedInstance as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"filename": filename, **result}


async def _boc_report(qif_file: UploadFile, ap242_file: UploadFile) -> dict:
    qif_name = Path(qif_file.filename or "").name
    ap_name = Path(ap242_file.filename or "").name
    if not qif_name.lower().endswith(".xml"):
        raise HTTPException(status_code=422, detail=f"{qif_name or 'QIF file'} must be an XML file")
    if Path(ap_name).suffix.lower() not in {".stp", ".step", ".stpx", ".xml"}:
        raise HTTPException(status_code=422, detail=f"{ap_name or 'AP242 file'} must be a STEP or AP242 XML file")
    qif_content = await qif_file.read(_MAX_FILE_BYTES + 1)
    ap_content = await ap242_file.read(_MAX_FILE_BYTES + 1)
    for name, content in ((qif_name, qif_content), (ap_name, ap_content)):
        if not content or len(content) > _MAX_FILE_BYTES:
            raise HTTPException(status_code=422, detail=f"{name} is empty or exceeds 10 MB")

    def _compare() -> dict:
        from backend.ceim.ap242_adapter import ap242_to_ceim_batch
        from backend.ceim.boc_conformance import compare_boc
        from backend.ceim.qif_adapter import qif_to_ceim_batch
        return compare_boc(ap242_to_ceim_batch(ap_content, filename=ap_name), qif_to_ceim_batch(qif_content))

    try:
        result = await run_in_threadpool(_compare)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"qif_filename": qif_name, "ap242_filename": ap_name, **result}


@router.post("/instances/boc-check", summary="Compare a QIF Bill of Characteristics with the AP242 PMI it came from")
async def check_boc_pair(qif_file: Annotated[UploadFile, File(description="QIF 3.0 instance (.xml)")],
                         ap242_file: Annotated[UploadFile, File(description="AP242 STEP (.stp/.step/.stpx) or AP242 XML")]) -> dict:
    from backend.ceim.boc_document import serialize_boc
    report = await _boc_report(qif_file, ap242_file)
    return {**report, "bill_of_characteristics_turtle": serialize_boc(report)}


@router.post("/boc/export", summary="Export a Bill of Characteristics as an AAS-style submodel, Turtle, or JSON")
async def export_boc(qif_file: Annotated[UploadFile, File(description="QIF 3.0 instance (.xml)")],
                     ap242_file: Annotated[UploadFile, File(description="AP242 STEP (.stp/.step/.stpx) or AP242 XML")],
                     format: Annotated[str, Query(pattern="^(aas|turtle|json)$")] = "aas"):
    # Stateless export: nothing is stored, published, or registered.
    from backend.ceim.boc_aas import build_boc_submodel
    from backend.ceim.boc_document import serialize_boc
    report = await _boc_report(qif_file, ap242_file)
    if format == "turtle":
        return Response(content=serialize_boc(report), media_type="text/turtle")
    if format == "json":
        return report
    return build_boc_submodel(report)


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
def build_reference_ontology(ontology_name: str = Form("QIF 3.0 Ontology"), prefix: str = Form(""), description: str = Form("")) -> dict:
    return start_reference_task(ontology_name, prefix, description)


@router.post("/ontology/upload", include_in_schema=False)
async def build_uploaded_ontology(files: Annotated[list[UploadFile], File()], ontology_name: Annotated[str, Form()], prefix: Annotated[str, Form()] = "", description: Annotated[str, Form()] = "") -> dict:
    return await start_uploaded_task(files, ontology_name, prefix, description)
