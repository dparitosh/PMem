"""Standalone ingestion service retaining the existing SPA contract."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from .profiles import profiles
from .workflow import workflow
from .neo4j_writer import writer
from .schema_conversion import converter
from .engineering_workflow import workflow as engineering_workflow
from .ap242_mbd import ap242_mbd
from .tabular import MAX_IMPORT_ROWS, MAX_UPLOAD_BYTES, constraint_query, index_query, load_table, node_query, records, relationship_query
import json
import httpx
from defusedxml import ElementTree as ET

router = APIRouter(tags=["ingestion"])


@router.get("/ingestion/health")
def health() -> dict:
    return {"status": "ok", "service": "ingestion", "contract": "v1", "graph_store": writer.status()}


@router.get("/ingestion/graph-store", summary="Read semantic graph-store capability and configuration requirements")
def graph_store_status() -> dict:
    return writer.status()


@router.get("/import/formats", summary="List tracked import formats supported by the ingestion boundary")
def import_formats() -> dict:
    return {
        "formats": [
            "csv", "json", "jsonld", "xml", "xsd", "xmi", "reqif", "step", "stp", "stpx",
            "ttl", "owl", "rdf", "plmxml", "3dxml",
        ],
        "service": "ingestion",
    }


@router.get("/import/tasks", summary="List retained import tasks")
def import_tasks() -> dict:
    """Expose persisted task history used by Import and Ontology Junction."""
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService
        tasks = UnifiedDataImportService.list_tasks()
        return {"total_tasks": len(tasks), "tasks": tasks}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Import task registry is unavailable: {type(exc).__name__}") from exc


@router.post("/schema-conversions/inspect", summary="Convert EXPRESS, STEP/STP/STPX, XMI, or XSD to a normalized Turtle contract")
async def inspect_engineering_schema(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
    try:
        return converter.convert(filename=file.filename or "source", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ap242/inspect", summary="Inspect AP242 XSD schemas, EXPRESS schemas, or STEP instance files")
async def inspect_ap242(file: UploadFile = File(...)) -> dict:
    """Use explicit AP242 adapters; schema publication remains governed and opt-in."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
    try:
        result = converter.convert(filename=file.filename or "source", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.get("standard") != "ap242":
        raise HTTPException(status_code=422, detail="The uploaded file is not identifiable as an AP242 XSD, EXPRESS, or STEP representation")
    return result


@router.post("/ap242/mbd/extract", summary="Extract AP242 MBD product, geometry, PMI, and presentation mappings")
async def extract_ap242_mbd(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
    try:
        return ap242_mbd.extract(filename=file.filename or "source.stp", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ap242/mbd/export-part28", summary="Losslessly export an AP242 Part-28 XML source")
async def export_ap242_part28(file: UploadFile = File(...)) -> Response:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
    try:
        exported = ap242_mbd.export_part28(filename=file.filename or "source.stpx", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    name = Path(file.filename or "ap242_exchange.stpx").stem + ".stpx"
    return Response(content=exported, media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/engineering-workflows", summary="Convert and register an engineering ontology through service boundaries")
async def run_engineering_workflow(
    request: Request,
    file: UploadFile = File(...),
    ontology_name: str = Form(""),
    prefix: str = Form(""),
      description: str = Form(""),
      register_ontology: bool = Form(True),
      publish: bool = Form(False),
      enforce_quality: bool = Form(True),
      policy_exception_ids: list[str] = Form([]),
) -> dict:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
    try:
        return await engineering_workflow.run(
            filename=file.filename or "source", content=content, ontology_name=ontology_name, prefix=prefix,
              description=description, register=register_ontology, request_id=getattr(request.state, "request_id", None),
              publish=publish, enforce_quality=enforce_quality, policy_exception_ids=policy_exception_ids,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ontology service is unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/source-profiles/inspect", summary="Inspect a schema or sample file for profile creation")
async def inspect_source_profile(file: UploadFile = File(...)) -> dict:
    try:
        return profiles.inspect(filename=file.filename or "source", content=await file.read())
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Source inspection failed: {exc}") from exc


@router.get("/source-profiles", summary="List reusable source profiles")
def list_source_profiles() -> dict:
    entries = profiles.list()
    return {"profiles": entries, "count": len(entries)}


@router.post("/source-profiles", summary="Create or version a declarative source profile")
def save_source_profile(profile: dict) -> dict:
    try:
        return profiles.save(profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/source-profiles/{profile_id}/normalize", summary="Normalize one source record for the ontology service")
def normalize_source_record(profile_id: str, record: dict) -> dict:
    try:
        return profiles.normalize(profile=profiles.get(profile_id), record=record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/source-profiles/{profile_id}/execute", summary="Normalize a JSON, JSON-LD, or XML batch with a reusable profile")
async def execute_source_profile(profile_id: str, file: UploadFile = File(...)) -> dict:
    """Produce the canonical entity payload consumed by the ontology service.

    This endpoint deliberately normalizes only; persistence remains an explicit
    downstream ontology/graph operation so uploads cannot mutate the graph by
    surprise.
    """
    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
        return profiles.normalize_batch(
            profile=profiles.get(profile_id), filename=file.filename or "source", content=content,
        )
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        raise HTTPException(status_code=422, detail=f"Profile execution failed: {exc}") from exc


@router.post("/source-profiles/{profile_id}/workflow", summary="Generate and optionally publish an ontology from a source profile batch")
async def run_source_profile_workflow(
    request: Request,
    profile_id: str,
    file: UploadFile = File(...),
    ontology_name: str = Form(""),
    prefix: str = Form(""),
    base_uri: str = Form("https://depo.local/ontology/"),
    publish: bool = Form(False),
    enforce_quality: bool = Form(True),
    policy_exception_ids: str = Form("[]"),
) -> dict:
    """Run normalize → Semantica generate/validate → optional graph publish.

    ``publish`` is deliberately opt-in because it changes the governed graph.
    """
    try:
        profile = profiles.get(profile_id)
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
        normalized = profiles.normalize_batch(profile=profile, filename=file.filename or "source", content=content)
        selected_prefix = prefix or str(profile.get("prefix") or profile_id)
        return await workflow.run(
            normalized=normalized,
            name=ontology_name or str(profile.get("name") or profile_id),
            prefix=selected_prefix,
            base_uri=base_uri,
            publish=publish,
            enforce_quality=enforce_quality,
            policy_exception_ids=list(json.loads(policy_exception_ids)),
            request_id=getattr(request.state, "request_id", None),
        )
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        raise HTTPException(status_code=422, detail=f"Profile workflow failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Dependent semantic service is unavailable: {exc}") from exc


@router.post("/ingest-data", summary="Ingest tabular data through the ingestion service")
async def ingest_data(
    file: UploadFile = File(...), nodeDefinitions: str = Form(...), relationshipDefinitions: str = Form(...),
    indexes: str = Form(...), constraints: str = Form(...),
) -> dict:
    try:
        node_defs, rel_defs, index_defs, constraint_defs = [json.loads(item) for item in (nodeDefinitions, relationshipDefinitions, indexes, constraints)]
        if not all(isinstance(item, list) for item in (node_defs, rel_defs, index_defs, constraint_defs)):
            raise ValueError("All ingestion configuration fields must be JSON arrays")
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
        table = load_table(content, file.filename or "")
        if len(table) > MAX_IMPORT_ROWS:
            raise HTTPException(status_code=413, detail="Import exceeds the 100,000 row limit")
        rows = records(table)
        statements = [
            *(index_query(item["type"], item["name"], item["label"], item["properties"]) for item in index_defs),
            *(constraint_query(item["type"], item["name"], item["label"], item["properties"]) for item in constraint_defs),
            *(node_query(item["label"], item["properties"], item.get("mergeKeys", [])) for item in node_defs if item.get("label") and item.get("properties")),
            *(relationship_query(item["type"], item["fromLabel"], item["toLabel"], item["fromProperty"], item["toProperty"]) for item in rel_defs if item.get("type") and item.get("fromLabel") and item.get("toLabel")),
        ]
        results = []
        for statement in filter(None, statements):
            try:
                writer.execute(statement, parameters={"rows": rows} if "UNWIND" in statement else None)
                results.append({"status": "success"})
            except Exception as exc:
                results.append({"status": "error", "error": str(exc)})
        return {"message": "Data ingestion completed", "results": results}
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
