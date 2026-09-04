"""
Document Upload API Router
Handles bulk document uploads with format detection, text extraction, chunking,
embedding, and Neo4j indexing.
"""
import os
import logging
import shutil
import tempfile
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool




def _default_format_description() -> dict:
    return {
        "pdf": "Portable Document Format with page-to-image or text extraction",
        "word": "Microsoft Word document conversion and extraction",
        "powerpoint": "Microsoft PowerPoint slide conversion and extraction",
        "text": "Plain text or Markdown extraction",
        "html": "HTML text extraction",
    }


def _load_document_processor():
    errors = []
    candidates = [
        "backend.Services.document_processor",
        "Services.document_processor",
        "document_processor",
    ]
    for module_name in candidates:
        try:
            module = __import__(module_name, fromlist=[
                "process_documents_batch",
                "get_format_description",
                "cleanup_temp_directory",
            ])
            return (
                getattr(module, "process_documents_batch"),
                getattr(module, "get_format_description"),
                getattr(module, "cleanup_temp_directory"),
                module_name,
            )
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")

    def _unavailable_process_documents_batch(*args, **kwargs):
        raise RuntimeError(
            "Document processing backend is not installed or importable. "
            + " | ".join(errors)
        )

    def _fallback_get_format_description():
        return _default_format_description()

    def _noop_cleanup_temp_directory():
        return None

    return (
        _unavailable_process_documents_batch,
        _fallback_get_format_description,
        _noop_cleanup_temp_directory,
        "unavailable",
    )


def _document_processor_status() -> dict:
    process_documents_batch, get_format_description, cleanup_temp_directory, module_name = _load_document_processor()
    available = module_name != "unavailable"
    runtime = {}
    if available:
        try:
            runtime = __import__(module_name, fromlist=["runtime_status"]).runtime_status()
            available = bool(runtime.get("available"))
        except Exception as exc:
            runtime = {"available": False, "errors": [str(exc)]}
            available = False
    return {
        "available": available,
        "module": module_name,
        "runtime": runtime,
        "process_documents_batch": process_documents_batch,
        "get_format_description": get_format_description,
        "cleanup_temp_directory": cleanup_temp_directory,
    }


def _require_document_processor() -> dict:
    status = _document_processor_status()
    if not status["available"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document processing pipeline is unavailable in this deployment. "
                "Install or package the document processor module and embeddings backend before using upload endpoints."
            ),
        )
    return status

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/documents", tags=["documents"])

# ========== Request/Response Models ==========
class DocumentUploadResponse(BaseModel):
    """Response for document upload endpoint"""
    status: str
    message: str
    summary: Optional[dict] = None
    results: Optional[List[dict]] = None
    total_documents: int = 0
    processed_documents: int = 0
    failed_documents: int = 0
    total_chunks: int = 0
    chunks_created: int = 0
    timestamp: str

class DocumentFormatInfo(BaseModel):
    """Information about supported document formats"""
    format: str
    extensions: List[str]
    description: str

class SupportedFormatsResponse(BaseModel):
    """Response for supported formats endpoint"""
    supported_formats: List[DocumentFormatInfo]
    constraints: dict


class DocumentPlanRequest(BaseModel):
    """Request metadata for unstructured planning."""
    filename: Optional[str] = None
    content_type: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentJobResponse(BaseModel):
    task_id: str
    status: str
    stage: str
    progress: int = 0
    status_url: str
    artifacts_url: str

# ========== Configuration ==========
TEMP_UPLOAD_DIR = os.getenv("DOCUMENT_TEMP_DIR", "temp_uploads")


def _positive_int_setting(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


MAX_FILE_SIZE_MB = _positive_int_setting("MAX_FILE_SIZE_MB", 50)
MAX_FILES_PER_UPLOAD = _positive_int_setting("MAX_FILES_PER_UPLOAD", 10)
DOCUMENT_INDEX_NAME = os.getenv("NEO4J_DATASHEET_VECTOR_INDEX", "datasheet_index").strip() or "datasheet_index"

# ========== Helper Functions ==========
def create_temp_upload_dir() -> str:
    """Create an isolated temporary upload directory for one request."""
    base_dir = Path(TEMP_UPLOAD_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix="document_upload_", dir=str(base_dir))


def _safe_upload_filename(filename: str) -> str:
    safe_name = Path(filename or "uploaded_document").name
    safe_name = "".join(ch if ch.isalnum() or ch in {".", "_", "-", " "} else "_" for ch in safe_name).strip()
    return safe_name or "uploaded_document"

def save_uploaded_file(upload_file: UploadFile, temp_dir: str) -> str:
    """
    Save uploaded file to temporary directory
    
    Args:
        upload_file: FastAPI UploadFile object
        temp_dir: Temporary directory path
        
    Returns:
        Path to saved file
        
    Raises:
        HTTPException: If file save fails
    """
    try:
        safe_name = _safe_upload_filename(upload_file.filename)
        candidate = Path(temp_dir) / safe_name
        if candidate.exists():
            collision_dir = Path(tempfile.mkdtemp(prefix="same_name_", dir=temp_dir))
            candidate = collision_dir / safe_name
        file_path = str(candidate)
        
        with open(file_path, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)
        
        logger.info(f"Saved uploaded file: {file_path}")
        return file_path
    
    except Exception as e:
        error_msg = f"Failed to save uploaded file: {e}"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

def cleanup_temp_files(temp_dir: str):
    """Remove temporary uploaded files"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Could not cleanup temporary directory: {e}")

def validate_upload_size(file: UploadFile, max_size_mb: int = None) -> tuple:
    """
    Validate file size before upload
    
    Args:
        file: Uploaded file
        max_size_mb: Maximum size in MB
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    max_size_mb = MAX_FILE_SIZE_MB if max_size_mb is None else max_size_mb
    
    try:
        # Check filename
        if not file.filename:
            return False, "File must have a name"
        
        # Check content type or file format
        file_ext = Path(file.filename).suffix.lower()
        supported = [".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".htm"]
        
        if file_ext not in supported:
            return False, f"Unsupported file format: {file_ext}. Supported: {', '.join(supported)}"

        max_bytes = max_size_mb * 1024 * 1024
        file.file.seek(0, os.SEEK_END)
        size_bytes = file.file.tell()
        file.file.seek(0)
        if size_bytes == 0:
            return False, f"File is empty: {file.filename}"
        if size_bytes > max_bytes:
            return False, f"File too large: {file.filename} ({round(size_bytes / (1024 * 1024), 2)} MB, max {max_size_mb} MB)"
        
        return True, None
    
    except Exception as e:
        return False, str(e)


def _validated_index_name(index_name: Optional[str]) -> str:
    requested = str(index_name or DOCUMENT_INDEX_NAME).strip()
    if requested != DOCUMENT_INDEX_NAME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported document index '{requested}'; configured index is '{DOCUMENT_INDEX_NAME}'",
        )
    return requested


def _summarize_document_processing(processing_result: dict) -> dict:
    summary = processing_result.get("summary") or {}
    results = processing_result.get("processing_results") or []
    total_chunks = sum(
        int(item.get("chunks_created") or 0)
        for item in results
        if item.get("status") == "success"
    )
    return {
        "total_documents": int(summary.get("total_files") or len(results) or 0),
        "processed_documents": int(summary.get("successfully_processed") or 0),
        "failed_documents": int(summary.get("failed_processing") or 0),
        "total_chunks": total_chunks,
        "chunks_created": total_chunks,
    }


def _job_response(state: dict[str, Any]) -> DocumentJobResponse:
    task_id = str(state.get("task_id") or "")
    return DocumentJobResponse(
        task_id=task_id,
        status=str(state.get("status") or "unknown"),
        stage=str(state.get("stage") or "unknown"),
        progress=int(state.get("progress") or 0),
        status_url=f"/api/v1/documents/jobs/{task_id}",
        artifacts_url=f"/api/v1/documents/jobs/{task_id}/artifacts",
    )

# ========== API Endpoints ==========


@router.post("/plan")
async def plan_document_pipeline(request: DocumentPlanRequest):
    """Return an auditable extraction/chunking/mapping plan for a document."""
    try:
        try:
            from backend.Services.unstructured_agent_pipeline import build_unstructured_plan
        except Exception:
            from Services.unstructured_agent_pipeline import build_unstructured_plan

        metadata = dict(request.metadata or {})
        if request.filename:
            metadata["filename"] = request.filename
        if request.content_type:
            metadata["content_type"] = request.content_type
        if request.mime_type:
            metadata["mime_type"] = request.mime_type
        return {
            "status": "ok",
            "plan": build_unstructured_plan(metadata),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("Document planning failed: %s", exc)
        raise HTTPException(status_code=500, detail="Document planning failed") from exc


@router.post("/jobs", response_model=DocumentJobResponse, status_code=202)
async def submit_document_job(
    files: List[UploadFile] = File(...),
    index_name: Optional[str] = Form(None),
):
    """Retain source documents and process them in a durable background job."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Too many files: {len(files)} (max: {MAX_FILES_PER_UPLOAD})")
    selected_index = _validated_index_name(index_name)
    processor = _require_document_processor()
    del processor  # Readiness is checked before retaining and accepting the job.
    temp_dir = create_temp_upload_dir()
    try:
        from .document_job_service import DocumentJobService
        from .workflow_artifact_service import WorkflowArtifactService
        from backend.artifact_store import ArtifactStore

        saved_uploads: list[tuple[UploadFile, str]] = []
        for upload in files:
            is_valid, error = validate_upload_size(upload, MAX_FILE_SIZE_MB)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error)
            saved_uploads.append((upload, save_uploaded_file(upload, temp_dir)))

        task_id = str(uuid.uuid4())
        WorkflowArtifactService.ensure_task(task_id, "document.unstructured")
        retained_paths: list[str] = []
        source_artifacts: list[dict[str, Any]] = []
        canonical_store = ArtifactStore()
        for position, (upload, temporary_path) in enumerate(saved_uploads, start=1):
            artifact = WorkflowArtifactService.copy_file(
                task_id,
                f"source_{position:03d}",
                _safe_upload_filename(upload.filename),
                temporary_path,
                "source_document",
                {"original_filename": upload.filename or "", "position": position},
            )
            retained = WorkflowArtifactService.resolve_artifact_path(task_id, artifact["path"])
            if retained is None:
                raise RuntimeError("Retained source artifact could not be resolved")
            retained_paths.append(str(retained))
            canonical = canonical_store.ingest(
                retained,
                kind="unstructured-document",
                media_type=str(upload.content_type or artifact.get("mime_type") or "application/octet-stream"),
                provenance={"workflow_id": "document.unstructured", "task_id": task_id, "original_filename": upload.filename or "", "position": position},
            )
            source_artifacts.append({**artifact, "artifact_id": canonical["artifact_id"], "canonical_artifact": canonical})
        state = DocumentJobService.submit(
            retained_paths,
            source_artifacts,
            task_id=task_id,
            index_name=selected_index,
        )
        return _job_response(state)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Document job submission failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Document job submission failed") from exc
    finally:
        cleanup_temp_files(temp_dir)


@router.get("/jobs/{task_id}")
async def get_document_job(task_id: str):
    from .document_job_service import DocumentJobService

    state = DocumentJobService.get_status(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Document job not found")
    return state


@router.post("/jobs/{task_id}/cancel")
async def cancel_document_job(task_id: str):
    from .document_job_service import DocumentJobService

    state = DocumentJobService.cancel(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Document job not found")
    return state


@router.get("/jobs/{task_id}/artifacts")
async def get_document_job_artifacts(task_id: str):
    from .workflow_artifact_service import WorkflowArtifactService

    manifest = WorkflowArtifactService.get_manifest(task_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Document job artifacts not found")
    return manifest


@router.get("/jobs/{task_id}/artifacts/{artifact_path:path}")
async def download_document_job_artifact(task_id: str, artifact_path: str):
    from .workflow_artifact_service import WorkflowArtifactService

    path = WorkflowArtifactService.resolve_artifact_path(task_id, artifact_path)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Document artifact not found")
    return FileResponse(path, filename=path.name)

@router.get("/supported-formats", response_model=SupportedFormatsResponse)
async def get_supported_formats_endpoint():
    """
    Get list of supported document formats
    
    Returns:
        Information about supported formats and constraints
    """
    try:
        processor = _document_processor_status()
        format_desc = processor["get_format_description"]()
        formats_info = []
        
        # Map formats to extensions
        format_to_ext = {
            "pdf": [".pdf"],
            "word": [".docx"],
            "powerpoint": [".pptx"],
            "text": [".txt", ".md"],
            "html": [".html", ".htm"],
        }
        
        for fmt, description in format_desc.items():
            formats_info.append(DocumentFormatInfo(
                format=fmt,
                extensions=format_to_ext.get(fmt, []),
                description=description
            ))
        
        return SupportedFormatsResponse(
            supported_formats=formats_info,
            constraints={
                "max_file_size_mb": MAX_FILE_SIZE_MB,
                "max_files_per_upload": MAX_FILES_PER_UPLOAD,
                "note": "Embeddings are required for indexing. Vision LLMs are only needed for image/scanned-document enhancement.",
            "upload_ready": processor["available"],
            "index_name": DOCUMENT_INDEX_NAME,
            "ocr_available": bool((processor.get("runtime") or {}).get("ocr_available")),
            }
        )
    
    except Exception as e:
        logger.error(f"Error fetching supported formats: {e}")
        raise HTTPException(status_code=500, detail="Unable to retrieve supported document formats") from e

@router.post("/upload", response_model=DocumentUploadResponse, deprecated=True)
async def upload_documents(
    files: List[UploadFile] = File(...),
    index_name: Optional[str] = Form(None)
):
    """
    Retired: direct upload and indexing are no longer permitted.
    
    The endpoint automatically detects file format and processes accordingly:
    - **PDF**: Extracts page text
    - **Word**: Extracts document paragraphs
    - **PowerPoint**: Extracts slide text
    - **Text/Markdown/HTML**: Extracts textual content
    
    Use ``POST /documents/jobs``; it retains immutable evidence and requires
    CEIM/Data Product/Graph Publication approval before any serving write.
    
    Args:
        files: Multiple document files to upload (can be mixed formats)
        index_name: Optional Neo4j index name (defaults to 'datasheet_index')
    
    Returns:
        DocumentUploadResponse with processing status and results
    
    Raises:
        HTTPException: If validation fails or processing encounters errors
    
    Example:
        ```python
        # Upload mixed format documents
        curl -X POST http://localhost:8000/api/v1/documents/upload \\
          -F "files=@datasheet.pdf" \\
          -F "files=@manual.docx" \\
          -F "files=@presentation.pptx"
        ```
    """
    raise HTTPException(
        status_code=410,
        detail="Direct document indexing is retired. Submit /api/v1/documents/jobs so extraction produces governed evidence before CEIM/Data Product/Graph Publication.",
    )

    temp_dir = None
    
    try:
        # Validate upload constraints
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files: {len(files)} (max: {MAX_FILES_PER_UPLOAD})"
            )
        
        logger.info(f"📦 Processing {len(files)} document(s)...")
        selected_index = _validated_index_name(index_name)
        
        # Create temporary directory
        temp_dir = create_temp_upload_dir()
        
        # Save and validate uploaded files
        saved_files = []
        for file in files:
            # Validate file
            is_valid, error = validate_upload_size(file, MAX_FILE_SIZE_MB)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error)
            
            # Save file
            file_path = save_uploaded_file(file, temp_dir)
            saved_files.append(file_path)
            
            logger.info(f"  ✓ Uploaded: {file.filename}")
        
        if not saved_files:
            raise HTTPException(status_code=400, detail="No valid files to process")
        
        logger.info(f"✅ All files uploaded. Processing {len(saved_files)} document(s)...")
        
        # Process documents using batch processor
        processor = _require_document_processor()
        processing_result = await run_in_threadpool(
            processor["process_documents_batch"],
            saved_files,
            index_name=selected_index,
        )
        counters = _summarize_document_processing(processing_result)
        
        # Prepare response
        succeeded = int(processing_result['summary']['successfully_processed'])
        failed = int(processing_result['summary']['failed_processing'])
        response = DocumentUploadResponse(
            status="success" if failed == 0 else ("failed" if succeeded == 0 else "partial"),
            message=(
                f"Successfully processed {processing_result['summary']['successfully_processed']} "
                f"out of {processing_result['summary']['total_files']} files"
            ),
            summary=processing_result['summary'],
            results=processing_result['processing_results'],
            **counters,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        logger.info(f"✅ Upload and processing completed: {response.message}")
        return response
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"❌ Unexpected error during document upload: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing documents: {str(e)}"
        )
    
    finally:
        # Cleanup temporary files
        if temp_dir:
            cleanup_temp_files(temp_dir)
        
        # Also cleanup document processor temp directory
        try:
            _document_processor_status()["cleanup_temp_directory"]()
        except Exception:
            pass

@router.post("/upload-single", response_model=DocumentUploadResponse, deprecated=True)
async def upload_single_document(
    file: UploadFile = File(...),
    index_name: Optional[str] = Form(None)
):
    """
    Retired: direct upload and indexing are no longer permitted.
    
    Convenience endpoint for uploading one document at a time.
    
    Args:
        file: Document file to upload
        index_name: Optional Neo4j index name
    
    Returns:
        DocumentUploadResponse with processing status
    """
    raise HTTPException(
        status_code=410,
        detail="Direct document indexing is retired. Submit /api/v1/documents/jobs so extraction produces governed evidence before CEIM/Data Product/Graph Publication.",
    )

    temp_dir = None
    
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Validate file
        is_valid, error = validate_upload_size(file, MAX_FILE_SIZE_MB)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)
        
        logger.info(f"📄 Processing single document: {file.filename}")
        selected_index = _validated_index_name(index_name)
        
        # Create temporary directory
        temp_dir = create_temp_upload_dir()
        
        # Save file
        file_path = save_uploaded_file(file, temp_dir)
        
        # Process document
        processor = _require_document_processor()
        processing_result = await run_in_threadpool(
            processor["process_documents_batch"],
            [file_path],
            index_name=selected_index,
        )
        counters = _summarize_document_processing(processing_result)
        
        # Prepare response
        response = DocumentUploadResponse(
            status="success" if processing_result['summary']['failed_processing'] == 0 else "failed",
            message=(
                f"Successfully processed {file.filename}"
                if processing_result['summary']['successfully_processed'] == 1
                else f"Failed to process {file.filename}"
            ),
            summary=processing_result['summary'],
            results=processing_result['processing_results'],
            **counters,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        logger.info(f"✅ Single document processing completed")
        return response
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"❌ Error processing single document: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}"
        )
    
    finally:
        # Cleanup temporary files
        if temp_dir:
            cleanup_temp_files(temp_dir)
        
        try:
            _document_processor_status()["cleanup_temp_directory"]()
        except Exception:
            pass

@router.get("/health")
async def health_check():
    """
    Health check endpoint for document pipeline
    
    Returns:
        Status of document processing service
    """
    try:
        processor = _document_processor_status()
        return {
            **({"status": "healthy"} if processor["available"] else {"status": "degraded"}),
            "service": "Document Upload API",
            "processor_available": processor["available"],
            "processor_module": processor["module"],
            "processor_runtime": processor["runtime"],
            "supported_formats": list(processor["get_format_description"]().keys()),
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "max_files_per_upload": MAX_FILES_PER_UPLOAD,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Embeddings are required for indexing. Vision LLMs are only needed for image/scanned-document enhancement.",
            "upload_ready": processor["available"],
            "index_name": DOCUMENT_INDEX_NAME,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Usage in main.py:
# from Services.documents import router as documents_router
# app.include_router(documents_router, prefix="/api", tags=["documents"])
