"""
Unified Data Import Router
Provides 5 endpoints for file import with progress tracking, preview, and commit capabilities.
"""

import logging
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Form
from pydantic import BaseModel, Field

# ✅ SECURITY: File size limits
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_FILE_SIZE_DISPLAY = "500 MB"


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload incrementally and reject oversized content early."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"File too large. Maximum size: {MAX_FILE_SIZE_DISPLAY}")
        chunks.append(chunk)
    return b"".join(chunks)

from .unified_data_import import (
    UnifiedDataImportService,
    FileFormatDetector,
)
from .ontology_upload_manager import OntologyUploadManager
from .owl_generation_service import _extract_xsd_target_namespace, _normalize_base_uri
from .oslc_trs_service import OSLCTRSService

logger = logging.getLogger(__name__)

# Initialize services
UnifiedDataImportService.initialize()
OntologyUploadManager.initialize()

router = APIRouter(prefix="/import", tags=["data-import"])

# Router for ontology-specific operations
ontology_router = APIRouter(prefix="/ontology", tags=["ontology"])


# ========== Request/Response Models ==========

class ImportStatusResponse(BaseModel):
    """Response for import status"""
    task_id: str
    filename: str
    file_type: str
    current_stage: str
    progress: int
    message: str
    status: str
    error: Optional[str] = None
    stats: Optional[dict] = None
    schema_metadata: Optional[dict] = None
    started_at: str
    completed_at: Optional[str] = None


class PreviewResponse(BaseModel):
    """Response for data preview"""
    task_id: str
    row_count: int
    columns: list
    sample_rows: list
    auto_schema: dict


class ImportConfigRequest(BaseModel):
    """Request to configure import"""
    nodes: Optional[list] = Field(None, description="Node definitions")
    relationships: Optional[list] = Field(None, description="Relationship definitions")
    indexes: Optional[list] = Field(None, description="Index definitions")
    constraints: Optional[list] = Field(None, description="Constraint definitions")


class CommitResponse(BaseModel):
    """Response from commit"""
    task_id: str
    status: str
    message: str
    result: dict


class OntologyMetadataRequest(BaseModel):
    """Request with ontology metadata for upload"""
    ontology_name: str = Field(..., description="User-friendly ontology name")
    prefix: str = Field(..., description="Ontology namespace prefix")
    generation_type: str = Field(..., description="What to generate: shacl, owl, both")
    file_type: str = Field(..., description="File type: xsd, xmi")
    description: Optional[str] = Field(None, description="Ontology description")


class UploadResponse(BaseModel):
    """Response from upload endpoint"""
    task_id: str
    filename: str
    file_type: str
    ontology_id: Optional[str] = None
    ontology_name: Optional[str] = None
    prefix: Optional[str] = None
    source_namespace: Optional[str] = None
    base_uri: Optional[str] = None
    message: str
    supported_formats: list
    storage_path: Optional[str] = None


class OntologyMappingRequest(BaseModel):
    """Legacy request for source profile mapping. Prefer SemanticWorkflowService instance.link for instance-to-ontology alignment."""
    task_id: str
    target_ontology: str = Field(..., description="Legacy target/profile id for ontology-to-ontology mapping; not required for Semantic Bridge instance linking")
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0, description="Minimum confidence for legacy entity-to-entity mapping suggestions")


class OntologyMappingResponse(BaseModel):
    """Response from ontology mapping"""
    task_id: str
    source_namespace: str
    target_namespace: str
    entity_mappings_count: int
    unmapped_entities_count: int
    overall_confidence: float
    mapping_metadata: dict
    aligned_owl_ttl: Optional[str] = None


class OntologyMergeRequest(BaseModel):
    """Request for ontology merge"""
    from_ontology_id: str = Field(..., description="Source ontology ID to merge from")
    to_ontology_id: str = Field(..., description="Target ontology ID to merge into")
    dry_run: bool = Field(False, description="If true, preview impact without mutating data")


# ========== Endpoints ==========

# ========== Endpoints ==========

@ontology_router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload Ontology File",
    description="Upload and register an ontology file (XSD/XMI/OWL/RDF/TTL) with metadata. Captures ontology metadata and stores for future reuse.",
    tags=["ontology"],
    responses={
        200: {
            "description": "Ontology uploaded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "task_id": "abc123xyz",
                        "filename": "Domain_model.xsd",
                        "file_type": "xsd",
                        "ontology_id": "ap239_1735123456",
                        "ontology_name": "AP239 Product Model",
                        "prefix": "ap239",
                        "message": "Ontology 'AP239 Product Model' uploaded and registered",
                        "storage_path": "/path/to/ontology_uploads/ap239_1735123456/Domain_model.xsd",
                        "supported_formats": [".csv", ".xsd", ".xmi", ".owl", ".rdf", ".ttl"]
                    }
                }
            }
        },
        400: {"description": "Invalid file or missing metadata"},
        413: {"description": "File too large"},
        500: {"description": "Server error during upload"}
    }
)
async def upload_ontology_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="XSD, XMI, OWL, RDF/XML, or TTL ontology file"),
    ontology_name: str = Form(..., description="Human-readable name for the ontology"),
    prefix: str = Form("", description="Optional namespace prefix; derived from the source namespace when omitted"),
    generation_type: str = Form(..., description="Generation type: shacl, owl, or both"),
    description: str = Form("", description="Optional ontology description"),
    schema_type: str = Form("schema", description="File classification: schema or instance")
):
    """
    Upload and register an ontology file (XSD/XMI/OWL/RDF/TTL) with metadata.
    
    Captures ontology metadata and stores for future reuse.
    
    Parameters:
    - file: XSD, XMI, OWL, RDF/XML, or TTL file
    - ontology_name: Human-readable name (e.g., "AP239 Product Model")
    - prefix: Namespace prefix (e.g., "ap239")
    - generation_type: What to generate - 'shacl', 'owl', or 'both'
    - description: Optional ontology description
    
    Returns: task_id + ontology_id for tracking and future reuse
    """
    try:
        # ✅ INPUT VALIDATION
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a name")
        
        # Validate ontology_name (1-100 chars, alphanumeric + space/dash)
        import re
        if not ontology_name or len(ontology_name) > 100:
            raise HTTPException(status_code=400, detail="ontology_name must be 1-100 characters")
        if not re.match(r'^[a-zA-Z0-9_\-\s]+$', ontology_name):
            raise HTTPException(status_code=400, detail="ontology_name contains invalid characters. Use only letters, numbers, spaces, underscores, and dashes")
        
        # Validate prefix (1-50 chars, must start with letter, alphanumeric + underscore)
        if prefix and len(prefix) > 50:
            raise HTTPException(status_code=400, detail="prefix must be at most 50 characters")
        if prefix and not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', prefix):
            raise HTTPException(status_code=400, detail="prefix must start with a letter and contain only alphanumeric characters and underscores")
        
        # Validate generation_type
        if generation_type not in ['shacl', 'owl', 'both', 'as_is']:
            raise HTTPException(status_code=400, detail="generation_type must be 'shacl', 'owl', 'both', or 'as_is'")
        
        # Validate description (max 500 chars)
        if description and len(description) > 500:
            raise HTTPException(status_code=400, detail="description must be 500 characters or less")
        
        # Validate file type
        file_type = FileFormatDetector.detect(file.filename)
        if not file_type or file_type.value not in ['xsd', 'xmi', 'ontology']:
            raise HTTPException(
                status_code=400,
                detail="Only XSD, XMI, OWL, RDF/XML, and TTL files are supported for ontology upload."
            )

        # Ontology files are loaded as-is (no XSD/XMI generation semantics required).
        resolved_generation_type = generation_type
        if file_type.value == 'ontology' and generation_type == 'shacl':
            resolved_generation_type = 'as_is'

        source_namespace = ""
        base_uri = ""
        
        # Read file content
        file_content = await _read_upload_with_limit(file, MAX_FILE_SIZE)
        if not file_content:
            raise HTTPException(status_code=400, detail="File is empty")
        
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE_DISPLAY}"
            )

        if file_type.value == 'xsd':
            source_namespace = _extract_xsd_target_namespace(file_content)
            base_uri = _normalize_base_uri(source_namespace, f"http://depo-onto.local/xsd#{Path(file.filename).stem}/")
        
        # Save ontology file and metadata
        save_result = OntologyUploadManager.save_ontology_file(
            file_content=file_content,
            filename=file.filename,
            ontology_name=ontology_name,
            prefix=prefix,
            file_type=file_type.value,
            generation_type=resolved_generation_type,
            description=description or "",
            schema_type=schema_type or "schema",
            source_namespace=source_namespace,
        )
        
        if save_result['status'] != 'success':
            raise HTTPException(status_code=500, detail=save_result.get('error'))
        
        # File is saved — use a stable task_id derived from the ontology_id
        # (start_import is intentionally skipped: it parses the full file synchronously
        #  which blocks the event loop and causes client-side timeouts for large XSD/XMI files)
        task_id = save_result['ontology_id']

        neo4j_info = " Source retained. Graph publication requires the governed semantic approval workflow."

        version = save_result.get('version', 1)
        is_new_version = save_result.get('is_new_version', False)
        version_msg = f" (v{version}, replaces {save_result['replaces']})" if is_new_version else f" (v{version})"

        return UploadResponse(
            task_id=task_id,
            filename=file.filename,
            file_type=file_type.value,
            ontology_id=save_result['ontology_id'],
            ontology_name=ontology_name,
            prefix=save_result.get('metadata', {}).get('prefix') or prefix,
            source_namespace=save_result.get('metadata', {}).get('namespace') or source_namespace or None,
            base_uri=save_result.get('metadata', {}).get('ontology_uri') or base_uri or None,
            message=f"Ontology '{ontology_name}' uploaded and registered{version_msg}. Task ID: {task_id}.{neo4j_info}",
            supported_formats=FileFormatDetector.get_supported_formats(),
            storage_path=save_result['storage_path']
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ontology upload error: {e}")
        raise HTTPException(status_code=500, detail="Import service failed. Please try again later.") from e


@ontology_router.get(
    "/registered",
    summary="List Registered Ontologies",
    description="Retrieve all registered ontologies with their metadata including name, prefix, file type, generation type, and upload timestamp",
    tags=["ontology"],
    responses={
        200: {
            "description": "List of registered ontologies",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "ontologies": [
                            {
                                "ontology_id": "ap239_1735123456",
                                "ontology_name": "AP239 Product Model",
                                "prefix": "ap239",
                                "file_type": "xsd",
                                "generation_type": "shacl",
                                "uploaded_at": "2026-05-25T12:30:45.123456",
                                "file_size": 125460
                            }
                        ]
                    }
                }
            }
        },
        500: {"description": "Server error while retrieving ontologies"}
    }
)
async def list_registered_ontologies():
    """List all registered ontologies with metadata.
    Merges file-based upload registry with ontologies discovered directly in Neo4j
    (e.g. loaded via scripts rather than the upload pipeline).
    """
    try:
        try:
            from core.graph import graph as _g
        except ModuleNotFoundError:
            from ..core.graph import graph as _g
    except Exception as e:
        logger.warning(f"[registered] Neo4j unavailable for count enrichment: {e}")
        _g = None

    return OntologyUploadManager.list_ontologies_with_neo4j_counts(_g)


@ontology_router.get(
    "/{ontology_id}",
    summary="Get Registered Ontology",
    description="Retrieve public metadata for one registered ontology by its stable identifier.",
    tags=["ontology"],
    responses={404: {"description": "Ontology not found"}},
)
async def get_registered_ontology(ontology_id: str):
    """Return ontology metadata without exposing server-side storage paths."""
    result = OntologyUploadManager.get_ontology(ontology_id)
    if result.get("status") != "success":
        error = result.get("error", "Ontology not found")
        status_code = 404 if str(error).lower() == "ontology not found" else 500
        raise HTTPException(status_code=status_code, detail=error)

    metadata = result.get("metadata") or {}
    public_fields = {
        "ontology_id",
        "ontology_name",
        "prefix",
        "file_type",
        "generation_type",
        "description",
        "schema_type",
        "version",
        "status",
        "uploaded_at",
        "file_size",
        "source_namespace",
        "target_namespace",
        "is_latest",
        "replaces",
        "superseded_by",
        "merged_into",
    }
    public_metadata = {
        key: value
        for key, value in metadata.items()
        if key in public_fields
    }
    public_metadata.setdefault("ontology_id", ontology_id)
    return {
        "status": "success",
        "metadata": public_metadata,
        "file_exists": bool(result.get("file_exists")),
    }


@ontology_router.post(
    "/merge",
    summary="Merge two ontologies",
    description="Merge all nodes/relationships from the source ontology into the target ontology in Neo4j. Sets ontology_prefix on source nodes to the target prefix.",
    tags=["ontology"],
)
async def merge_ontologies(body: dict):
    """
    Merge FROM ontology into TO ontology in Neo4j.
    Body: { "from_ontology_id": "...", "to_ontology_id": "..." }
    """
    from_id = body.get("from_ontology_id", "").strip()
    to_id = body.get("to_ontology_id", "").strip()
    raw_dry_run = body.get("dry_run", False)
    if isinstance(raw_dry_run, str):
        dry_run = raw_dry_run.strip().lower() in {"1", "true", "yes", "y", "on"}
    else:
        dry_run = bool(raw_dry_run)

    if not from_id or not to_id:
        raise HTTPException(status_code=422, detail="Both from_ontology_id and to_ontology_id are required.")
    if from_id == to_id:
        raise HTTPException(status_code=422, detail="from_ontology_id and to_ontology_id must be different.")

    # Resolve prefixes from registry.
    # IMPORTANT: The UI uses /ontology/registered which merges file-uploaded ontologies
    # with Neo4j-discovered prefixes (e.g. ds3dx/sysml). Merge must accept those too.
    all_onts = {o.get("ontology_id"): o for o in (await list_registered_ontologies()).get("ontologies", []) if o.get("ontology_id")}
    if from_id not in all_onts:
        raise HTTPException(status_code=404, detail=f"Ontology not found: {from_id}")
    if to_id not in all_onts:
        raise HTTPException(status_code=404, detail=f"Ontology not found: {to_id}")

    from_prefix = all_onts[from_id].get("prefix", from_id)
    to_prefix = all_onts[to_id].get("prefix", to_id)
    to_name = all_onts[to_id].get("ontology_name", to_id)

    # Make sure ontology/search indexes exist before any merge mutation runs.
    index_audit = {"ensured": False, "warning": None}
    try:
        try:
            from Services.graph_embeddings import ensure_indexes_standalone as _ensure_indexes
        except ModuleNotFoundError:
            from ..Services.graph_embeddings import ensure_indexes_standalone as _ensure_indexes
        if _ensure_indexes is not None:
            _ensure_indexes()
            index_audit["ensured"] = True
    except Exception as idx_err:
        logger.warning("Ontology merge index preflight skipped: %s", idx_err)
        index_audit["warning"] = f"{type(idx_err).__name__}: {idx_err}"

    # Neo4j: count candidates before mutation (used for dry-run and post-merge checks)
    try:
        try:
            from core.graph import graph as _g
        except ModuleNotFoundError:
            from ..core.graph import graph as _g

        ontology_labels = [
            "Ontology", "OntologyClass", "OntologyProperty", "OntologyMetadata",
            "OntologyResource", "OntologyRestriction", "OntologyIndividual",
        ]
        ontology_scope = """
            any(label IN labels(n) WHERE label IN $ontology_labels)
        """
        count_rows = _g.query(
            f"MATCH (n) WHERE {ontology_scope} AND (coalesce(n.ontology_prefix, n.prefix) = $from_p OR n.ontology_id = $from_id) RETURN count(n) AS total",
            {"from_p": from_prefix, "from_id": from_id, "ontology_labels": ontology_labels},
        )
        candidate_nodes = count_rows[0]["total"] if count_rows else 0

        if dry_run:
            return {
                "status": "success",
                "mode": "dry_run",
                "message": (
                    f"Dry run: would merge '{from_prefix}' into '{to_prefix}' ({to_name})"
                ),
                "candidate_nodes": candidate_nodes,
                "from_ontology_id": from_id,
                "to_ontology_id": to_id,
                "index_audit": index_audit,
            }

        # Update ontology_prefix property
        updated = _g.query(
            f"MATCH (n) WHERE {ontology_scope} AND (coalesce(n.ontology_prefix, n.prefix) = $from_p OR n.ontology_id = $from_id) "
            "SET n.ontology_prefix = $to_p, n.prefix = $to_p, "
            "n.merged_from_ontology_id = $from_id, n.merged_into_ontology_id = $to_id "
            "RETURN count(n) AS updated",
            {"from_p": from_prefix, "from_id": from_id, "to_id": to_id, "to_p": to_prefix, "ontology_labels": ontology_labels},
        )
        nodes_updated = updated[0]["updated"] if updated else 0

        # Create a MERGED_INTO relationship between the two ontology root nodes (if any)
        _g.query(
            "MATCH (src) WHERE src.ontology_id = $fid "
            "MATCH (tgt) WHERE tgt.ontology_id = $tid "
            "MERGE (src)-[:MERGED_INTO]->(tgt)",
            {"fid": from_id, "tid": to_id}
        )

        # Best-effort consistency check. Non-fatal because concurrent writes may alter counts.
        consistency_warning = None
        if nodes_updated != candidate_nodes:
            consistency_warning = (
                f"Updated {nodes_updated} nodes but pre-count was {candidate_nodes}. "
                "Concurrent graph writes may have occurred during merge."
            )
    except Exception as neo_err:
        logger.exception("Neo4j merge failed")
        raise HTTPException(
            status_code=500,
            detail=f"Merge failed in Neo4j: {type(neo_err).__name__}: {neo_err}",
        )

    # Update metadata: mark source as merged (best-effort; Neo4j-discovered ontologies may not have metadata.json)
    try:
        OntologyUploadManager.update_metadata(from_id, {"merged_into": to_id, "is_latest": False})
    except Exception:
        # Non-fatal
        pass

    try:
        OSLCTRSService.publish_event(
            OSLCTRSService.ontology_resource_uri(to_id),
            "Modification",
            title=f"Ontology merge from {from_id} into {to_id}",
            metadata={"from_ontology_id": from_id, "to_ontology_id": to_id, "from_prefix": from_prefix, "to_prefix": to_prefix, "nodes_updated": nodes_updated},
        )
    except Exception as exc:
        logger.warning("OSLC TRS publish skipped for ontology merge %s -> %s: %s", from_id, to_id, exc)

    response = {
        "status": "success",
        "message": f"Merged '{from_prefix}' into '{to_prefix}' ({to_name})",
        "nodes_updated": nodes_updated,
        "candidate_nodes": candidate_nodes,
        "from_ontology_id": from_id,
        "to_ontology_id": to_id,
        "index_audit": index_audit,
    }

    if consistency_warning:
        response["warning"] = consistency_warning

    return response


@ontology_router.post(
    "/cleanup-old-xsd",
    summary="Delete old ingested XSD schemas",
    description=(
        "Delete superseded/merged non-latest XSD ontology uploads. "
        "Supports dry-run preview and optional Neo4j cleanup."
    ),
    tags=["ontology"],
)
async def cleanup_old_xsd_schemas(body: dict):
    """
    Cleanup old XSD ontology uploads.

    Body options:
    - dry_run: bool (default true)
    - delete_from_neo4j: bool (default true)
    - confirm: must be exactly "DELETE_OLD_XSD" when dry_run is false
    - batch_size: int (default 25, min 1, max 200)
    """
    raw_dry_run = body.get("dry_run", True)
    if isinstance(raw_dry_run, str):
        dry_run = raw_dry_run.strip().lower() in {"1", "true", "yes", "y", "on"}
    else:
        dry_run = bool(raw_dry_run)

    raw_delete_from_neo4j = body.get("delete_from_neo4j", True)
    if isinstance(raw_delete_from_neo4j, str):
        delete_from_neo4j = raw_delete_from_neo4j.strip().lower() in {"1", "true", "yes", "y", "on"}
    else:
        delete_from_neo4j = bool(raw_delete_from_neo4j)

    confirm_token = str(body.get("confirm", "")).strip()

    raw_batch_size = body.get("batch_size", 25)
    try:
        batch_size = int(raw_batch_size)
    except Exception:
        raise HTTPException(status_code=422, detail="batch_size must be an integer")
    if batch_size < 1 or batch_size > 200:
        raise HTTPException(status_code=422, detail="batch_size must be between 1 and 200")

    all_result = OntologyUploadManager.list_all_ontologies()
    if all_result.get("status") != "success":
        raise HTTPException(status_code=500, detail=all_result.get("error", "Failed to list ontologies"))

    candidates = []
    for ont in all_result.get("ontologies", []):
        if str(ont.get("file_type", "")).lower() != "xsd":
            continue
        if ont.get("is_latest", True) and not ont.get("merged_into"):
            continue
        candidates.append(ont)

    candidate_ids = [o.get("ontology_id") for o in candidates if o.get("ontology_id")]
    candidate_prefixes = sorted({o.get("prefix") for o in candidates if o.get("prefix")})

    # Only allow prefix-wide cleanup when no remaining non-candidate ontology keeps that prefix.
    all_ontology_ids = {o.get("ontology_id") for o in all_result.get("ontologies", []) if o.get("ontology_id")}
    candidate_id_set = set(candidate_ids)
    remaining_ids = all_ontology_ids - candidate_id_set
    safe_prefixes = sorted({
        p for p in candidate_prefixes
        if not any((o.get("prefix") == p and o.get("ontology_id") in remaining_ids) for o in all_result.get("ontologies", []))
    })

    id_to_prefix = {
        o.get("ontology_id"): o.get("prefix")
        for o in candidates
        if o.get("ontology_id")
    }

    if dry_run:
        return {
            "status": "success",
            "mode": "dry_run",
            "candidate_count": len(candidate_ids),
            "candidate_ontology_ids": candidate_ids,
            "candidate_prefixes": candidate_prefixes,
            "safe_prefixes_for_cleanup": safe_prefixes,
            "estimated_batches": (len(candidate_ids) + batch_size - 1) // batch_size,
            "batch_size": batch_size,
            "required_confirm_token": "DELETE_OLD_XSD",
        }

    if confirm_token != "DELETE_OLD_XSD":
        raise HTTPException(
            status_code=422,
            detail="Confirmation token required: confirm='DELETE_OLD_XSD'",
        )

    neo4j_deleted_by_id_or_source = 0
    neo4j_deleted_by_prefix = 0
    deleted_ontology_ids = []
    errors = []
    total_batches = (len(candidate_ids) + batch_size - 1) // batch_size
    batches = []

    for batch_index in range(total_batches):
        start = batch_index * batch_size
        end = start + batch_size
        batch_ids = candidate_ids[start:end]
        batch_prefixes = sorted({
            id_to_prefix.get(oid)
            for oid in batch_ids
            if id_to_prefix.get(oid) in safe_prefixes
        })

        batch_neo4j_primary = 0
        batch_neo4j_prefix = 0

        if delete_from_neo4j and batch_ids:
            try:
                try:
                    from core.graph import graph as _g
                except ModuleNotFoundError:
                    from ..core.graph import graph as _g

                rows_primary = _g.query(
                    """
                    MATCH (n)
                    WHERE n.ontology_id IN $ontology_ids
                       OR n.source_ontology IN $ontology_ids
                    WITH count(n) AS before_count
                    MATCH (m)
                    WHERE m.ontology_id IN $ontology_ids
                       OR m.source_ontology IN $ontology_ids
                    DETACH DELETE m
                    RETURN before_count AS deleted
                    """,
                    {"ontology_ids": batch_ids},
                )
                batch_neo4j_primary = rows_primary[0].get("deleted", 0) if rows_primary else 0

                if batch_prefixes:
                    rows_prefix = _g.query(
                        """
                        MATCH (n)
                        WHERE n.ontology_prefix IN $prefixes
                          AND (
                            n.ontology_id IS NULL
                            OR NOT n.ontology_id IN $ontology_ids
                          )
                          AND (
                            n.source_ontology IS NULL
                            OR NOT n.source_ontology IN $ontology_ids
                          )
                        WITH count(n) AS before_count
                        MATCH (m)
                        WHERE m.ontology_prefix IN $prefixes
                          AND (
                            m.ontology_id IS NULL
                            OR NOT m.ontology_id IN $ontology_ids
                          )
                          AND (
                            m.source_ontology IS NULL
                            OR NOT m.source_ontology IN $ontology_ids
                          )
                        DETACH DELETE m
                        RETURN before_count AS deleted
                        """,
                        {"prefixes": batch_prefixes, "ontology_ids": batch_ids},
                    )
                    batch_neo4j_prefix = rows_prefix[0].get("deleted", 0) if rows_prefix else 0
            except Exception as neo_err:
                logger.exception("Neo4j cleanup failed for old XSD schemas")
                raise HTTPException(
                    status_code=500,
                    detail=f"Neo4j cleanup failed in batch {batch_index + 1}: {type(neo_err).__name__}: {neo_err}",
                )

        batch_deleted = []
        for ontology_id in batch_ids:
            result = OntologyUploadManager.delete_ontology(ontology_id)
            if result.get("status") == "success":
                deleted_ontology_ids.append(ontology_id)
                batch_deleted.append(ontology_id)
            else:
                errors.append({"batch": batch_index + 1, "ontology_id": ontology_id, "error": result.get("error", "Unknown error")})

        neo4j_deleted_by_id_or_source += batch_neo4j_primary
        neo4j_deleted_by_prefix += batch_neo4j_prefix
        neo4j_deleted_by_id_or_source + neo4j_deleted_by_prefix

        batches.append({
            "batch": batch_index + 1,
            "batch_size": len(batch_ids),
            "deleted_ontology_ids": batch_deleted,
            "neo4j_deleted_by_id_or_source": batch_neo4j_primary,
            "neo4j_deleted_by_prefix": batch_neo4j_prefix,
        })
