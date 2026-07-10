"""
Document Upload API Router
Handles bulk document uploads with format detection, text extraction, chunking,
embedding, and Neo4j indexing.
"""
import os
import logging
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel




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
    metadata: Dict[str, Any] = {}

# ========== Configuration ==========
TEMP_UPLOAD_DIR = os.getenv("DOCUMENT_TEMP_DIR", "temp_uploads")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILES_PER_UPLOAD = int(os.getenv("MAX_FILES_PER_UPLOAD", "10"))

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
        file_path = os.path.join(temp_dir, safe_name)
        
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
        supported = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".html", ".htm"]
        
        if file_ext not in supported:
            return False, f"Unsupported file format: {file_ext}. Supported: {', '.join(supported)}"

        max_bytes = max_size_mb * 1024 * 1024
        file.file.seek(0, os.SEEK_END)
        size_bytes = file.file.tell()
        file.file.seek(0)
        if size_bytes > max_bytes:
            return False, f"File too large: {file.filename} ({round(size_bytes / (1024 * 1024), 2)} MB, max {max_size_mb} MB)"
        
        return True, None
    
    except Exception as e:
        return False, str(e)


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
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        logger.error("Document planning failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

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
            "word": [".docx", ".doc"],
            "powerpoint": [".pptx", ".ppt"],
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
            "upload_ready": _document_processor_status()["available"]
            }
        )
    
    except Exception as e:
        logger.error(f"Error fetching supported formats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    index_name: Optional[str] = Form(None)
):
    """
    Upload and process multiple documents.
    
    The endpoint automatically detects file format and processes accordingly:
    - **PDF**: Extracts page text
    - **Word**: Extracts document paragraphs
    - **PowerPoint**: Extracts slide text
    - **Text/Markdown/HTML**: Extracts textual content
    
    All documents are stored as embeddings in Neo4j for later retrieval.
    
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
        processing_result = processor["process_documents_batch"](
            saved_files,
            index_name=index_name or "datasheet_index"
        )
        counters = _summarize_document_processing(processing_result)
        
        # Prepare response
        response = DocumentUploadResponse(
            status="success" if processing_result['summary']['failed_processing'] == 0 else "partial",
            message=(
                f"Successfully processed {processing_result['summary']['successfully_processed']} "
                f"out of {processing_result['summary']['total_files']} files"
            ),
            summary=processing_result['summary'],
            results=processing_result['processing_results'],
            **counters,
            timestamp=datetime.now().isoformat()
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
        except:
            pass

@router.post("/upload-single", response_model=DocumentUploadResponse)
async def upload_single_document(
    file: UploadFile = File(...),
    index_name: Optional[str] = Form(None)
):
    """
    Upload and process a single document
    
    Convenience endpoint for uploading one document at a time.
    
    Args:
        file: Document file to upload
        index_name: Optional Neo4j index name
    
    Returns:
        DocumentUploadResponse with processing status
    """
    temp_dir = None
    
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Validate file
        is_valid, error = validate_upload_size(file, MAX_FILE_SIZE_MB)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)
        
        logger.info(f"📄 Processing single document: {file.filename}")
        
        # Create temporary directory
        temp_dir = create_temp_upload_dir()
        
        # Save file
        file_path = save_uploaded_file(file, temp_dir)
        
        # Process document
        processor = _require_document_processor()
        processing_result = processor["process_documents_batch"](
            [file_path],
            index_name=index_name or "datasheet_index"
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
            timestamp=datetime.now().isoformat()
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
        except:
            pass

@router.get("/health")
async def health_check():
    """
    Health check endpoint for document pipeline
    
    Returns:
        Status of document processing service
    """
    try:
        return {
            **({"status": "healthy"} if _document_processor_status()["available"] else {"status": "degraded"}),
            "service": "Document Upload API",
            "processor_available": _document_processor_status()["available"],
            "processor_module": _document_processor_status()["module"],
            "processor_runtime": _document_processor_status()["runtime"],
            "supported_formats": list(_document_processor_status()["get_format_description"]().keys()),
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "max_files_per_upload": MAX_FILES_PER_UPLOAD,
            "timestamp": datetime.now().isoformat(),
            "note": "Embeddings are required for indexing. Vision LLMs are only needed for image/scanned-document enhancement.",
            "upload_ready": _document_processor_status()["available"]
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Usage in main.py:
# from Services.documents import router as documents_router
# app.include_router(documents_router, prefix="/api", tags=["documents"])
