"""
Unified Document Processor
Handles PDF, Word (.docx), and PowerPoint (.pptx) documents
Automatically detects format and routes to appropriate pipeline
"""
import os
import logging
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from langchain_neo4j import Neo4jVector

# Import individual pipelines
from pdf_pipeline import pdf_to_neo4j_pipeline as process_pdf
from word_pipeline import word_to_neo4j_pipeline as process_word
from ppt_pipeline import pptx_to_neo4j_pipeline as process_pptx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# ========== Configuration ==========
def _get_env_config() -> dict:
    """Load configuration from environment variables"""
    return {
        "MAX_FILE_SIZE_MB": int(os.getenv("MAX_FILE_SIZE_MB", "50")),
        "MAX_FILES_PER_UPLOAD": int(os.getenv("MAX_FILES_PER_UPLOAD", "10")),
        "DOCUMENT_TEMP_DIR": os.getenv("DOCUMENT_TEMP_DIR", "temp_documents"),
    }

CONFIG = _get_env_config()

# ========== File Type Detection ==========
SUPPORTED_FORMATS = {
    ".pdf": "pdf",
    ".docx": "word",
    ".doc": "word",
    ".pptx": "powerpoint",
    ".ppt": "powerpoint"
}

def get_file_extension(file_path: str) -> str:
    """Get file extension from path"""
    return Path(file_path).suffix.lower()

def detect_file_format(file_path: str) -> Optional[str]:
    """
    Detect file format from extension
    
    Args:
        file_path: Path to file
        
    Returns:
        Format type: 'pdf', 'word', 'powerpoint', or None if unsupported
    """
    ext = get_file_extension(file_path)
    return SUPPORTED_FORMATS.get(ext, None)

def is_file_supported(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Check if file format is supported
    
    Args:
        file_path: Path to file
        
    Returns:
        Tuple of (is_supported, error_message)
    """
    fmt = detect_file_format(file_path)
    if not fmt:
        ext = get_file_extension(file_path)
        error = f"Unsupported file format: {ext}. Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        return False, error
    return True, None

# ========== File Validation ==========
def validate_file_exists(file_path: str) -> Tuple[bool, Optional[str]]:
    """Check if file exists"""
    if not os.path.exists(file_path):
        error = f"File not found: {file_path}"
        logger.error(error)
        return False, error
    return True, None

def validate_file_size(file_path: str, max_size_mb: int = None) -> Tuple[bool, Optional[str]]:
    """Check if file size is within limits"""
    max_size_mb = max_size_mb or CONFIG["MAX_FILE_SIZE_MB"]
    
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > max_size_mb:
            error = f"File too large: {file_size_mb:.2f} MB (max: {max_size_mb} MB)"
            logger.error(error)
            return False, error
        return True, None
    except Exception as e:
        error = f"Error checking file size: {e}"
        logger.error(error)
        return False, error

def validate_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate file before processing
    
    Args:
        file_path: Path to file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check existence
    exists, error = validate_file_exists(file_path)
    if not exists:
        return False, error
    
    # Check format
    supported, error = is_file_supported(file_path)
    if not supported:
        return False, error
    
    # Check size
    size_ok, error = validate_file_size(file_path)
    if not size_ok:
        return False, error
    
    return True, None

# ========== Batch File Validation ==========
def validate_file_list(file_paths: List[str]) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate a list of files
    
    Args:
        file_paths: List of file paths
        
    Returns:
        Tuple of (all_valid, validation_report)
    """
    if len(file_paths) == 0:
        return False, {"error": "No files provided"}
    
    if len(file_paths) > CONFIG["MAX_FILES_PER_UPLOAD"]:
        return False, {
            "error": f"Too many files: {len(file_paths)} (max: {CONFIG['MAX_FILES_PER_UPLOAD']})"
        }
    
    report = {
        "total_files": len(file_paths),
        "valid_files": [],
        "invalid_files": [],
        "file_types": {}
    }
    
    for file_path in file_paths:
        is_valid, error = validate_file(file_path)
        
        if is_valid:
            fmt = detect_file_format(file_path)
            report["valid_files"].append(file_path)
            report["file_types"][fmt] = report["file_types"].get(fmt, 0) + 1
            logger.info(f"✓ Valid: {file_path} ({fmt})")
        else:
            report["invalid_files"].append({
                "file": file_path,
                "error": error
            })
            logger.error(f"✗ Invalid: {file_path} - {error}")
    
    all_valid = len(report["invalid_files"]) == 0
    return all_valid, report

# ========== Document Processing ==========
def process_document(file_path: str, index_name: str = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Process a single document
    
    Args:
        file_path: Path to document
        index_name: Neo4j index name (optional)
        
    Returns:
        Tuple of (success, result_dict)
    """
    try:
        # Validate file
        is_valid, error = validate_file(file_path)
        if not is_valid:
            return False, {"error": error, "file": file_path}
        
        # Detect format
        fmt = detect_file_format(file_path)
        file_name = os.path.basename(file_path)
        
        logger.info(f"Processing {fmt} document: {file_name}")
        
        result = {
            "file": file_path,
            "file_name": file_name,
            "format": fmt,
            "status": "processing",
            "started_at": datetime.now().isoformat()
        }
        
        # Route to appropriate pipeline
        try:
            if fmt == "pdf":
                vector_store = process_pdf(file_path)
                result["status"] = "success"
                result["message"] = "PDF processed successfully"
            
            elif fmt == "word":
                vector_store = process_word(file_path)
                result["status"] = "success"
                result["message"] = "Word document processed successfully"
            
            elif fmt == "powerpoint":
                vector_store = process_pptx(file_path)
                result["status"] = "success"
                result["message"] = "PowerPoint presentation processed successfully"
            
            else:
                result["status"] = "error"
                result["error"] = f"Unknown format: {fmt}"
                return False, result
            
            result["completed_at"] = datetime.now().isoformat()
            return True, result
        
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["completed_at"] = datetime.now().isoformat()
            logger.error(f"Error processing {file_name}: {e}")
            return False, result
    
    except Exception as e:
        logger.error(f"Unexpected error processing {file_path}: {e}")
        return False, {
            "error": str(e),
            "file": file_path,
            "status": "error"
        }

def process_documents_batch(file_paths: List[str], index_name: str = None) -> Dict[str, Any]:
    """
    Process multiple documents
    
    Args:
        file_paths: List of file paths
        index_name: Neo4j index name (optional)
        
    Returns:
        Summary of processing results
    """
    logger.info(f"Processing batch of {len(file_paths)} documents...")
    
    # Validate all files first
    all_valid, validation_report = validate_file_list(file_paths)
    
    if not all_valid and len(validation_report.get("valid_files", [])) == 0:
        logger.error("No valid files to process")
        return {
            "status": "failed",
            "message": "No valid files to process",
            "validation": validation_report,
            "results": []
        }
    
    # Process valid files
    results = []
    successful = 0
    failed = 0
    
    for file_path in validation_report.get("valid_files", []):
        success, result = process_document(file_path, index_name)
        results.append(result)
        
        if success:
            successful += 1
            logger.info(f"✅ Successfully processed: {os.path.basename(file_path)}")
        else:
            failed += 1
            logger.error(f"❌ Failed to process: {os.path.basename(file_path)}")
    
    summary = {
        "status": "completed",
        "summary": {
            "total_files": len(file_paths),
            "valid_files": len(validation_report.get("valid_files", [])),
            "invalid_files": len(validation_report.get("invalid_files", [])),
            "successfully_processed": successful,
            "failed_processing": failed,
            "file_types": validation_report.get("file_types", {})
        },
        "validation_errors": validation_report.get("invalid_files", []),
        "processing_results": results,
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"Batch processing complete: {successful} successful, {failed} failed")
    return summary

# ========== Utility Functions ==========
def get_supported_formats() -> List[str]:
    """Get list of supported file extensions"""
    return list(SUPPORTED_FORMATS.keys())

def get_format_description() -> Dict[str, str]:
    """Get description of supported formats"""
    return {
        "pdf": "Portable Document Format",
        "word": "Microsoft Word Document (*.docx, *.doc)",
        "powerpoint": "Microsoft PowerPoint Presentation (*.pptx, *.ppt)"
    }

def cleanup_temp_directory(temp_dir: str = None):
    """Remove temporary directory and files"""
    temp_dir = temp_dir or CONFIG["DOCUMENT_TEMP_DIR"]
    
    try:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Could not cleanup temporary directory: {e}")

# Usage example
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python document_processor.py <file1> [file2] [file3] ...")
        print(f"\nSupported formats: {', '.join(get_supported_formats())}")
        sys.exit(1)
    
    file_paths = sys.argv[1:]
    
    try:
        result = process_documents_batch(file_paths)
        
        print("\n" + "="*50)
        print("PROCESSING SUMMARY")
        print("="*50)
        print(f"Total files: {result['summary']['total_files']}")
        print(f"Valid files: {result['summary']['valid_files']}")
        print(f"Successfully processed: {result['summary']['successfully_processed']}")
        print(f"Failed: {result['summary']['failed_processing']}")
        print(f"File types: {result['summary']['file_types']}")
        print("="*50)
        
        if result['summary']['failed_processing'] > 0:
            print("\nProcessing Results:")
            for res in result['processing_results']:
                if res['status'] != 'success':
                    print(f"  ✗ {res.get('file_name', 'unknown')}: {res.get('error', 'Unknown error')}")
        
        # Cleanup
        cleanup_temp_directory()
        
        sys.exit(0 if result['summary']['failed_processing'] == 0 else 1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
