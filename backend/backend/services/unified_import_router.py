"""
Unified Data Import Router
Provides 5 endpoints for file import with progress tracking, preview, and commit capabilities.
"""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

# ✅ SECURITY: File size limits
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_FILE_SIZE_DISPLAY = "500 MB"

from .unified_data_import import (
    UnifiedDataImportService,
    FileFormatDetector,
    ImportStatus,
)

logger = logging.getLogger(__name__)

# Initialize service
UnifiedDataImportService.initialize()

router = APIRouter(prefix="/import", tags=["data-import"])


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


class UploadResponse(BaseModel):
    """Response from upload endpoint"""
    task_id: str
    filename: str
    file_type: str
    message: str
    supported_formats: list


class OntologyMappingRequest(BaseModel):
    """Request for ontology mapping"""
    task_id: str
    target_ontology: str = Field(..., description="Target ontology (windchill, ap242_product, pifrl)")
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0, description="Minimum confidence for entity mappings")


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


# ========== Endpoints ==========

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file and start import task.
    
    Supports: CSV, Excel, EXPRESS (.exp), PLMXML, STEP, XML
    
    Returns: task_id for tracking progress
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a name")
        
        # Validate filename length
        if len(file.filename) > 255:
            raise HTTPException(status_code=400, detail="Filename too long (max 255 characters)")
        
        # Validate file type
        file_type = FileFormatDetector.detect(file.filename)
        if not file_type:
            supported = FileFormatDetector.get_supported_formats()
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Supported: {', '.join(supported)}"
            )
        
        # Read file content with size check
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # ✅ SECURITY: Check file size
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE_DISPLAY}"
            )
        
        # Start import task
        task_id = await UnifiedDataImportService.start_import(file_content, file.filename)
        
        return UploadResponse(
            task_id=task_id,
            filename=file.filename,
            file_type=file_type.value,
            message="File uploaded successfully. Use /import/{task_id}/status to check progress.",
            supported_formats=FileFormatDetector.get_supported_formats()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # ✅ SECURITY: Don't leak internal errors to client
        logger.error(f"Upload error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="File upload failed. Please check file format and try again."
        )


@router.get("/owl/{task_id}")
async def get_owl(task_id: str):
    """
    Get generated OWL/Turtle RDF for a completed EXPRESS import.
    
    Only available for EXPRESS files after parse stage completes.
    Returns full OWL separately from status for large schemas.
    """
    try:
        status = UnifiedDataImportService.get_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        
        if status['file_type'] != 'express':
            raise HTTPException(
                status_code=400, 
                detail="OWL only available for EXPRESS schema files"
            )
        
        owl_ttl = status.get('owl_ttl')
        if not owl_ttl:
            raise HTTPException(
                status_code=404,
                detail="OWL not yet generated or task incomplete"
            )
        
        return {
            "task_id": task_id,
            "filename": status['filename'],
            "schema_name": status.get('schema_metadata', {}).get('schema_name'),
            "owl_format": "turtle",
            "owl_ttl": owl_ttl,
            "line_count": len(owl_ttl.split('\n')),
            "byte_size": len(owl_ttl.encode('utf-8'))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OWL retrieval error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve OWL. Please try again.")


@router.post("/convert-schema")
async def convert_schema_to_owl(file: UploadFile = File(...)):
    """
    Convert schema directly to OWL/Turtle (Step 2 of import).
    
    Supports:
    - .exp (EXPRESS schema files)
    - .stp, .step, .stpx (STEP data files in AP203/AP242)
    
    This is the main Step 2 operation:
    - Create import task to track progress
    - Parse schema (EXPRESS or STEP)
    - Generate OWL/Turtle RDF representation
    - Return full OWL + task_id for later stages
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a name")
        
        # Determine file type and validate
        file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        
        if file_ext == 'exp':
            file_type = 'EXPRESS'
        elif file_ext in ('stp', 'step', 'stpx'):
            file_type = 'STEP'
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '.{file_ext}'. Supported formats: .exp (EXPRESS), .stp/.step/.stpx (STEP data files)"
            )
        
        # Read file
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Create import task (for tracking through all 7 stages)
        task_id = await UnifiedDataImportService.start_import(file_content, file.filename)
        
        # Generate OWL based on file type
        from .owl_generation_service import OWLGenerationService
        
        if file_type == 'EXPRESS':
            owl_ttl, metadata = OWLGenerationService.generate_owl_from_express(
                file_content,
                file.filename
            )
        else:  # STEP
            owl_ttl, metadata = OWLGenerationService.generate_owl_from_step(
                file_content,
                file.filename
            )
        
        # Store OWL in task for Stage 3+
        import_tasks = UnifiedDataImportService.import_tasks if hasattr(UnifiedDataImportService, 'import_tasks') else {}
        if task_id in import_tasks:
            import_tasks[task_id]['owl_ttl'] = owl_ttl
            import_tasks[task_id]['schema_metadata'] = {
                'entity_count': metadata.get('entity_count'),
                'derived_attributes': metadata.get('derived_attributes'),
                'inverse_attributes': metadata.get('inverse_attributes'),
                'unique_constraints': metadata.get('unique_constraints'),
                'schema_references': metadata.get('schema_references'),
                'schema_name': metadata.get('schema_name'),
                'entities': metadata.get('entities', []),
            }
        
        return {
            "task_id": task_id,
            "filename": file.filename,
            "schema_name": metadata.get('schema_name'),
            "schema_id": metadata.get('schema_id'),
            "schema_metadata": {
                'entity_count': metadata.get('entity_count'),
                'derived_attributes': metadata.get('derived_attributes', 0),
                'inverse_attributes': metadata.get('inverse_attributes', 0),
                'unique_constraints': metadata.get('unique_constraints', 0),
                'schema_references': metadata.get('schema_references', []),
            },
            "owl_ttl": owl_ttl,
            "owl_triple_count": metadata.get('owl_triple_count'),
            "line_count": len(owl_ttl.split('\n')),
            "byte_size": len(owl_ttl.encode('utf-8'))
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        # Parsing/generation errors - return helpful message
        error_msg = str(e)
        logger.error(f"Schema parsing failed: {error_msg}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"File parsing failed: {error_msg}")
    except Exception as e:
        # Unexpected errors
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Schema conversion error: {error_type}: {error_msg}", exc_info=True)
        
        # Return appropriate error based on type
        if "parse" in error_msg.lower():
            raise HTTPException(status_code=400, detail=f"File format error: Could not parse {file_type} file. {error_msg}")
        elif "memory" in error_msg.lower():
            raise HTTPException(status_code=413, detail="File too large to process. Please try a smaller file.")
        else:
            raise HTTPException(status_code=500, detail=f"File conversion failed: {error_msg[:100]}")


@router.post("/map-ontology", response_model=OntologyMappingResponse)
async def map_to_ontology(request: OntologyMappingRequest):
    """
    Map and align schema to target ontology (Stage 3).
    
    Takes OWL from Stage 2 and maps entities to target ontology namespace.
    
    Supported target ontologies:
    - windchill: Infineon Windchill product ontology
    - ap242_product: ISO 10303 AP242 product alignment
    - pifrl: Product Information and Fulfillment Reference Library
    
    Returns: Aligned OWL + entity mapping metadata with confidence scores
    """
    try:
        # Get import task status (contains OWL from Stage 2)
        status = UnifiedDataImportService.get_status(request.task_id)
        if not status:
            raise HTTPException(status_code=404, detail="Task not found or has expired.")
        
        if status['file_type'] != 'express':
            raise HTTPException(
                status_code=400,
                detail="Ontology mapping only available for EXPRESS schema files"
            )
        
        # Get OWL and metadata from Stage 2
        owl_ttl = status.get('owl_ttl')
        schema_metadata = status.get('schema_metadata', {})
        
        if not owl_ttl:
            raise HTTPException(
                status_code=400,
                detail="OWL not available. Complete Stage 2 (Convert) first."
            )
        
        # Perform ontology mapping
        from .ontology_mapping_service import (
            map_express_to_ontology,
            TargetOntologyRegistry
        )
        
        # Validate target ontology
        if not TargetOntologyRegistry.get_ontology(request.target_ontology):
            available = TargetOntologyRegistry.list_ontologies()
            raise HTTPException(
                status_code=400,
                detail=f"Unknown target ontology. Available: {', '.join(available)}"
            )
        
        # Get source entities
        source_entities = schema_metadata.get('entities', [])
        source_namespace = f"http://express.schema/{schema_metadata.get('schema_name', 'unknown')}#"
        
        # Perform alignment
        alignment_result = map_express_to_ontology(
            owl_ttl=owl_ttl,
            source_namespace=source_namespace,
            source_entities=source_entities,
            target_ontology_name=request.target_ontology,
            confidence_threshold=request.confidence_threshold
        )
        
        # Store aligned OWL in task for Stage 4+
        import_tasks = UnifiedDataImportService.import_tasks if hasattr(UnifiedDataImportService, 'import_tasks') else {}
        if request.task_id in import_tasks:
            import_tasks[request.task_id]['aligned_owl_ttl'] = alignment_result.aligned_owl_ttl
            import_tasks[request.task_id]['entity_mappings'] = [
                {
                    'source': m.source_entity,
                    'target': m.target_entity,
                    'confidence': m.confidence,
                    'reason': m.reason,
                }
                for m in alignment_result.entity_mappings
            ]
        
        return OntologyMappingResponse(
            task_id=request.task_id,
            source_namespace=alignment_result.source_namespace,
            target_namespace=alignment_result.target_namespace,
            entity_mappings_count=len(alignment_result.entity_mappings),
            unmapped_entities_count=len(alignment_result.unmapped_entities),
            overall_confidence=alignment_result.confidence_score,
            mapping_metadata=alignment_result.mapping_metadata,
            aligned_owl_ttl=alignment_result.aligned_owl_ttl
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ontology mapping error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ontology mapping failed. Please verify your mapping configuration.")


@router.get("/ontologies")
async def list_available_ontologies():
    """List available target ontologies for mapping"""
    try:
        from .ontology_mapping_service import TargetOntologyRegistry
        
        ontologies = {}
        for name in TargetOntologyRegistry.list_ontologies():
            onto = TargetOntologyRegistry.get_ontology(name)
            ontologies[name] = {
                'namespace': onto['namespace'],
                'entity_count': len(onto['entities']),
                'sample_entities': onto['entities'][:5]
            }
        
        return {
            'available_ontologies': ontologies,
            'count': len(ontologies)
        }
        
    except Exception as e:
        logger.error(f"List ontologies error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve available ontologies.")


@router.post("/parse-schema")
async def parse_schema(file: UploadFile = File(...)):
    """
    Parse schema file (EXPRESS) and extract metadata.
    
    Returns schema structure, entities, DERIVE/INVERSE/UNIQUE constraints.
    
    Supports: EXPRESS (.exp), STEP (.stp/.stpx), CSV, Excel
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a name")
        
        # Detect file type
        file_type = FileFormatDetector.detect(file.filename)
        if not file_type:
            supported = FileFormatDetector.get_supported_formats()
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Supported: {', '.join(supported)}"
            )
        
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Parse based on type
        from .unified_data_import import FileParser
        rows, metadata = FileParser.parse(file_content, file_type)
        
        return {
            "filename": file.filename,
            "file_type": file_type.value,
            "schema_metadata": metadata,
            "preview_rows": rows[:20],  # First 20 rows
            "total_rows": len(rows)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Parse schema error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to parse schema. Please verify your file format.")


@router.get("/status/{task_id}", response_model=ImportStatusResponse)
async def get_status(task_id: str):
    """
    Get import task status.
    
    Tracks progress through stages: upload → parse → validate → transform → preview → ingest
    """
    try:
        status = UnifiedDataImportService.get_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        
        return ImportStatusResponse(**status)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status retrieval error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve task status.")


@router.get("/preview/{task_id}", response_model=PreviewResponse)
async def get_preview(task_id: str):
    """
    Get data preview before importing.
    
    Shows sample rows and auto-detected schema.
    Call this before /commit to review transformation.
    """
    try:
        preview = UnifiedDataImportService.get_preview(task_id)
        
        if not preview:
            raise HTTPException(status_code=404, detail="Preview not available. Task may have expired or encountered an error.")
        
        preview['task_id'] = task_id
        return PreviewResponse(**preview)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate preview. Please check the file.")


@router.post("/commit/{task_id}", response_model=CommitResponse)
async def commit_import(task_id: str, config: Optional[ImportConfigRequest] = None):
    """
    Commit import to Neo4j.
    
    If config is omitted, uses auto-detected schema.
    If config provided, uses specified node/relationship/index definitions.
    """
    try:
        config_dict = config.dict(exclude_none=True) if config else None
        result = await UnifiedDataImportService.commit_import(task_id, config_dict)
        
        return CommitResponse(
            task_id=task_id,
            status="completed",
            message="Data imported successfully",
            result=result
        )
        
    except ValueError as e:
        logger.error(f"Commit validation error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid configuration provided. Please check your settings.")
    except Exception as e:
        logger.error(f"Commit import error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to commit import. Please verify your data and try again.")


@router.post("/cancel/{task_id}")
async def cancel_import(task_id: str):
    """
    Cancel an import task.
    
    Only works on tasks in 'processing' state.
    """
    try:
        UnifiedDataImportService.cancel_import(task_id)
        return {"task_id": task_id, "message": "Import task cancelled"}
        
    except Exception as e:
        logger.error(f"Cancel import error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel import task. Please try again.")


# ========== Ollama / LLM Endpoints ==========

class OllamaQueryRequest(BaseModel):
    """Request for Ollama query"""
    question: str
    context: Optional[str] = None
    temperature: float = 0.7


class OllamaQueryResponse(BaseModel):
    """Response from Ollama query"""
    question: str
    answer: str
    sources: list
    confidence: float


@router.post("/ollama/query", response_model=OllamaQueryResponse)
async def ollama_query(request: OllamaQueryRequest):
    """
    Query Ollama LLM with optional context.
    
    Requires Ollama running on localhost:11434
    """
    try:
        from .ollama_service import get_ollama_service
        
        ollama = get_ollama_service()
        
        # Check health
        if not ollama.health_check():
            raise HTTPException(
                status_code=503,
                detail="Ollama service not available. Install from https://ollama.ai"
            )
        
        # Get answer
        result = ollama.answer_question(
            request.question,
            graph_context=request.context,
            temperature=request.temperature
        )
        
        return OllamaQueryResponse(
            question=request.question,
            answer=result['answer'],
            sources=result['sources'],
            confidence=result['confidence']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ollama query error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to process query. The LLM service may be temporarily unavailable.")


@router.get("/ollama/health")
async def ollama_health():
    """Check if Ollama is running and available"""
    try:
        from .ollama_service import get_ollama_service
        
        ollama = get_ollama_service()
        is_healthy = ollama.health_check()
        
        if is_healthy:
            models = ollama.list_models()
            return {
                "status": "healthy",
                "available": True,
                "models": models,
                "default_model": ollama.model
            }
        else:
            return {
                "status": "unavailable",
                "available": False,
                "models": [],
                "message": "Ollama service not running"
            }
            
    except Exception as e:
        logger.error(f"Ollama health check error: {str(e)}")
        return {
            "status": "error",
            "available": False,
            "message": str(e)
        }


# ========== Stages 4-7 Pipeline Execution ==========

class PipelineStages4to7Request(BaseModel):
    """Request to execute Stages 4-7 of pipeline"""
    task_id: str = Field(..., description="Task ID from Stage 3")
    owl_ttl: str = Field(..., description="OWL/Turtle content from Stage 2")
    schema_metadata: dict = Field(default_factory=dict, description="Schema metadata from Stage 2")


class PipelineStages4to7Response(BaseModel):
    """Response with Stages 4-7 results"""
    task_id: str
    stage_4_validate: dict
    stage_5_enrich: dict
    stage_6_load: dict
    stage_7_verify: dict
    overall_status: str
    timestamp: str


@router.post("/process-stages-4-7", response_model=PipelineStages4to7Response)
async def process_pipeline_stages_4_to_7(request: PipelineStages4to7Request):
    """
    Execute Stages 4-7 of the import pipeline:
    - Stage 4: SHACL Validation (structural checks)
    - Stage 5: Semantic Enrichment (OWL 2 DL characteristics)
    - Stage 6: Neo4j Ingestion (load to graph database)
    - Stage 7: Health Check (post-load verification)
    
    This endpoint processes the OWL/Turtle from Stage 2 and schema metadata,
    running all four stages sequentially with real validation and enrichment logic.
    """
    from datetime import datetime
    from .pipeline_stages_4_7 import UnifiedStage4to7Service
    
    try:
        service = UnifiedStage4to7Service()
        
        # Process all stages
        results = service.process_stages(
            request.owl_ttl,
            request.schema_metadata,
            request.task_id
        )
        
        return PipelineStages4to7Response(
            task_id=request.task_id,
            stage_4_validate=results['stage_4_validate'],
            stage_5_enrich=results['stage_5_enrich'],
            stage_6_load=results['stage_6_load'],
            stage_7_verify=results['stage_7_verify'],
            overall_status=results['overall_status'],
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Pipeline processing error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Data processing failed. Please check your file and try again.")


# ========== Helper Endpoint ==========

@router.get("/formats")
async def get_supported_formats():
    """Get list of supported file formats"""
    return {
        "supported_formats": FileFormatDetector.get_supported_formats(),
        "descriptions": {
            ".csv": "Comma-separated values",
            ".xlsx": "Microsoft Excel (2007+)",
            ".xls": "Microsoft Excel (legacy)",
            ".exp": "EXPRESS schema format (ISO 10303)",
            ".plmxml": "PLM XML format",
            ".step": "STEP 3D model format",
            ".stp": "STEP 3D model format (alternate)",
            ".stpx": "STEP XML format",
            ".xml": "Generic XML format",
        }
    }
