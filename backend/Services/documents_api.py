"""
Document Upload API Router
Handles bulk document uploads (PDF, Word, PowerPoint) with format detection
"""
import os
import logging
import shutil
from typing import List, Optional
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel

from document_processor import (
    process_documents_batch,
    get_format_description,
    cleanup_temp_directory
)

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

# ========== Configuration ==========
TEMP_UPLOAD_DIR = "temp_uploads"
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILES_PER_UPLOAD = int(os.getenv("MAX_FILES_PER_UPLOAD", "10"))

# ========== Helper Functions ==========
def create_temp_upload_dir() -> str:
    """Create temporary upload directory"""
    Path(TEMP_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    return TEMP_UPLOAD_DIR

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
        file_path = os.path.join(temp_dir, upload_file.filename)
        
        with open(file_path, "wb") as f:
            f.write(upload_file.file.read())
        
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
    max_size_mb = max_size_mb or MAX_FILE_SIZE_MB
    
    try:
        # Check filename
        if not file.filename:
            return False, "File must have a name"
        
        # Check content type or file format
        file_ext = Path(file.filename).suffix.lower()
        supported = [".pdf", ".docx", ".doc", ".pptx", ".ppt"]
        
        if file_ext not in supported:
            return False, f"Unsupported file format: {file_ext}. Supported: {', '.join(supported)}"
        
        return True, None
    
    except Exception as e:
        return False, str(e)

# ========== API Endpoints ==========

@router.get("/supported-formats", response_model=SupportedFormatsResponse)
async def get_supported_formats_endpoint():
    """
    Get list of supported document formats
    
    Returns:
        Information about supported formats and constraints
    """
    try:
        format_desc = get_format_description()
        formats_info = []
        
        # Map formats to extensions
        format_to_ext = {
            "pdf": [".pdf"],
            "word": [".docx", ".doc"],
            "powerpoint": [".pptx", ".ppt"]
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
                "note": "LLM model must have vision capability (GPT-4V, Claude, etc.)"
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
    Upload and process multiple documents (PDF, Word, PowerPoint)
    
    The endpoint automatically detects file format and processes accordingly:
    - **PDF**: Converts pages to images, extracts text using LLM vision
    - **Word**: Converts to images (via LibreOffice or text extraction), extracts using LLM vision
    - **PowerPoint**: Converts slides to images, extracts using LLM vision
    
    All documents are stored as embeddings in Neo4j for later retrieval.
    
    **Important**: Your LLM model must have vision capability (e.g., GPT-4V, Claude 3 Vision)
    
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
        curl -X POST http://localhost:8000/api/documents/upload \\
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
        processing_result = process_documents_batch(
            saved_files,
            index_name=index_name or "datasheet_index"
        )
        
        # Prepare response
        response = DocumentUploadResponse(
            status="success" if processing_result['summary']['failed_processing'] == 0 else "partial",
            message=(
                f"Successfully processed {processing_result['summary']['successfully_processed']} "
                f"out of {processing_result['summary']['total_files']} files"
            ),
            summary=processing_result['summary'],
            results=processing_result['processing_results'],
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
            cleanup_temp_directory()
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
        file: Document file to upload (PDF, Word, or PowerPoint)
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
        processing_result = process_documents_batch(
            [file_path],
            index_name=index_name or "datasheet_index"
        )
        
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
            cleanup_temp_directory()
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
            "status": "healthy",
            "service": "Document Upload API",
            "supported_formats": list(get_format_description().keys()),
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "max_files_per_upload": MAX_FILES_PER_UPLOAD,
            "timestamp": datetime.now().isoformat(),
            "note": "LLM model must have vision capability (GPT-4V, Claude, etc.)"
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
