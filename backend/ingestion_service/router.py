"""Standalone ingestion service retaining the existing SPA contract."""
from __future__ import annotations

from pathlib import Path
import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from .profiles import profiles
from .workflow import workflow
from .neo4j_writer import writer
from .schema_conversion import converter
from .engineering_workflow import workflow as engineering_workflow
from .ap242_mbd import ap242_mbd
from .ap242_reference import AP242ReferenceValidator
from .governed_import import governed_import, profile_for_filename
from .tabular import MAX_IMPORT_ROWS, MAX_UPLOAD_BYTES, constraint_query, index_query, load_table, node_query, records, relationship_query
import json
import httpx
from defusedxml import ElementTree as ET

router = APIRouter(tags=["ingestion"])


@router.post("/sysml-v2/import-commit", summary="Import the configured SysML v2 commit into an approved data job")
async def import_sysml_commit(request: Request, payload: dict) -> dict:
    from backend.depo_platform.authorization import approval_identity
    from .sysml_repository import read_snapshot
    approval_identity(request, payload, token_env="DATA_JOB_EXECUTION_TOKEN")
    try:
        snapshot = await read_snapshot()
        content = json.dumps(snapshot).encode("utf-8")
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Repository snapshot exceeds ingestion upload limit")
        result = await governed_import.run_job(
            filename="sysml-v2-snapshot.json", content=content, profile="sysml-v2",
            job_id=str(payload.get("job_id") or "semantic-source-validation"),
            job_version=str(payload.get("job_version") or "1.0.0"),
            source_system=f"sysml-v2:{snapshot['project_id']}:{snapshot['commit_id']}",
            request_id=getattr(request.state, "request_id", ""),
        )
        return {**result, "project_id": snapshot["project_id"], "commit_id": snapshot["commit_id"]}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(503, "Repository or data pipeline unavailable") from exc


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


@router.get("/governed-import/profiles", summary="Resolve the governed instance-import profile for a filename")
def governed_import_profile(filename: str) -> dict:
    try:
        return {"filename": filename, "profile": profile_for_filename(filename)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/governed-import", summary="Retain, normalize, and run an approved semantic data job for an engineering instance")
async def run_governed_import(
    request: Request, file: UploadFile = File(...), profile: str = Form("auto"),
    job_id: str = Form("semantic-source-validation"), job_version: str = Form("1.0.0"),
    source_system: str = Form(""),
) -> dict:
    """Route STEP/AP242, ReqIF, QIF, and PLMXML imports into Data Flow.

    The selected job must already be approved.  Importing never publishes to
    Neo4j; publication remains an explicit canonical approval action.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
    try:
        return await governed_import.run_job(
            filename=file.filename or "source", content=content, profile=profile,
            job_id=job_id, job_version=job_version, source_system=source_system,
            request_id=getattr(request.state, "request_id", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Data pipeline service is unavailable") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
        raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
    try:
        return converter.convert(filename=file.filename or "source", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ap242/inspect", summary="Inspect AP242 XSD schemas, EXPRESS schemas, or STEP instance files")
async def inspect_ap242(file: UploadFile = File(...)) -> dict:
    """Use explicit AP242 adapters; schema publication remains governed and opt-in."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
    try:
        result = converter.convert(filename=file.filename or "source", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.get("standard") != "ap242":
        raise HTTPException(status_code=422, detail="The uploaded file is not identifiable as an AP242 XSD, EXPRESS, or STEP representation")
    return result


@router.get("/ap242/reference/validation", summary="Validate the configured AP242 reference model and its semantic conversion")
def validate_ap242_reference() -> dict:
    """Validate the configured AP242 source without publishing or changing graph data.

    The reference location is controlled exclusively through
    ``AP242_REFERENCE_ROOT``.  This prevents the API from becoming an arbitrary
    local-path reader while making the standard-source evidence repeatable for
    deployment verification.
    """
    try:
        return AP242ReferenceValidator().validate()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ap242/mbd/extract", summary="Extract AP242 MBD product, geometry, PMI, and presentation mappings")
async def extract_ap242_mbd(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
    try:
        return ap242_mbd.extract(filename=file.filename or "source.stp", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ap242/mbd/export-part28", summary="Losslessly export an AP242 Part-28 XML source")
async def export_ap242_part28(file: UploadFile = File(...)) -> Response:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
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
        raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
    try:
        return await engineering_workflow.run(
            filename=file.filename or "source", content=content, ontology_name=ontology_name, prefix=prefix,
              description=description, register=register_ontology, request_id=getattr(request.state, "request_id", None),
              publish=publish, enforce_quality=enforce_quality, policy_exception_ids=policy_exception_ids,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
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
            raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
        return profiles.normalize_batch(
            profile=profiles.get(profile_id), filename=file.filename or "source", content=content,
        )
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        raise HTTPException(status_code=422, detail=f"Profile execution failed: {exc}") from exc


@router.post("/source-profiles/{profile_id}/workflow", summary="Generate and register an ontology draft from a source profile batch")
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
    """Run normalize → Semantica generate/validate → draft registration.

    ``publish`` requests publication-readiness checks only. A separate
    approved publication action is required to mutate the governed graph.
    """
    try:
        profile = profiles.get(profile_id)
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
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
    request: Request, file: UploadFile = File(...), nodeDefinitions: str = Form(...), relationshipDefinitions: str = Form(...),
    indexes: str = Form(...), constraints: str = Form(...),
) -> dict:
    # Retain this legacy direct-Cypher shape only for controlled migration.
    # New clients must use governed-import and the canonical publication path.
    if os.getenv("DEPO_ALLOW_DIRECT_TABULAR_WRITES", "false").lower() != "true":
        raise HTTPException(status_code=409, detail="Direct tabular writes are disabled; submit the source through governed-import")
    from backend.depo_platform.authorization import service_write_identity
    service_write_identity(request, token_env="INGESTION_WRITE_TOKEN", default_actor="ingestion-service")
    try:
        node_defs, rel_defs, index_defs, constraint_defs = [json.loads(item) for item in (nodeDefinitions, relationshipDefinitions, indexes, constraints)]
        if not all(isinstance(item, list) for item in (node_defs, rel_defs, index_defs, constraint_defs)):
            raise ValueError("All ingestion configuration fields must be JSON arrays")
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Upload exceeds the configured ingestion limit ({MAX_UPLOAD_BYTES} bytes)")
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
