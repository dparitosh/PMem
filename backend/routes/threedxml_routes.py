"""
3DXML Ontology Extraction API Routes

Endpoints:
- POST /ontology/extract-3dxml - Upload and extract 3DXML file to ontology
- GET /ontology/3dxml/status/{task_id} - Check extraction task status
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import logging
import os
import uuid
from pathlib import Path
import asyncio

# Import services
from ..Services.splm_ontology_extractor import OntologyExtractorFactory, OntologyFormat
from ..Services.threedxml_ontology_extractor import ThreeDXMLExtractor
from ..core.graph import graph as neo4j_graph
from ..core.db_config import get_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ontology", tags=["3DXML Extraction"])

# Task tracking for async operations
extraction_tasks = {}


class ExtractionRequest(BaseModel):
    """Request to extract ontology from 3DXML"""
    source_path: str
    ontology_name: str = "3DEXPERIENCE_EXTRACTED"


class ExtractionResponse(BaseModel):
    """Response from ontology extraction"""
    status: str
    task_id: str
    entities_extracted: int
    relationships_extracted: int
    entity_types: List[str]
    message: str


class ExtractionStatus(BaseModel):
    """Status of an extraction task"""
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: float
    entities_extracted: Optional[int] = None
    relationships_extracted: Optional[int] = None
    error: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3DXML EXTRACTION ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/extract-3dxml", response_model=ExtractionResponse)
async def extract_3dxml_ontology(
    file: UploadFile = File(...),
    ontology_name: str = Form("3DEXPERIENCE_EXTRACTED"),
    load_to_neo4j: bool = Form(True),
    background_tasks: BackgroundTasks = None
):
    """
    Upload and extract 3DXML file to create ontology
    
    Args:
        file: .3dxml file to extract
        ontology_name: Name for the extracted ontology
        load_to_neo4j: Whether to load extracted ontology to Neo4j
        background_tasks: Background task runner
    
    Returns:
        ExtractionResponse with extraction statistics
    """
    task_id = str(uuid.uuid4())
    
    try:
        # Validate file extension
        if not file.filename.endswith('.3dxml'):
            raise HTTPException(
                status_code=400,
                detail="File must have .3dxml extension"
            )
        
        # Create temporary directory for 3DXML file
        temp_dir = Path("temp_3dxml_uploads")
        temp_dir.mkdir(exist_ok=True)
        
        # Save uploaded file
        file_path = temp_dir / file.filename
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"[Task {task_id}] Saved 3DXML file: {file_path}")
        
        # Extract ontology
        extraction_tasks[task_id] = {
            "status": "processing",
            "progress": 0.2,
            "filename": file.filename
        }
        
        extractor = ThreeDXMLExtractor(str(temp_dir))
        ontology_data = extractor.extract()
        
        extraction_tasks[task_id]["progress"] = 0.6
        logger.info(f"[Task {task_id}] Extraction complete: "
                   f"{len(extractor.entities)} entities, "
                   f"{len(extractor.relationships)} relationships")
        
        # Load to Neo4j if requested
        if load_to_neo4j:
            extraction_tasks[task_id]["progress"] = 0.7
            
            # Create ontology node
            ontology_create_query = """
                MERGE (ont:Ontology {name: $ontology_name})
                SET ont.created_at = datetime(),
                    ont.source = '3DXML',
                    ont.entity_count = $entity_count,
                    ont.relationship_count = $rel_count
                RETURN ont
            """
            
            neo4j_graph.query(ontology_create_query, {
                "ontology_name": ontology_name,
                "entity_count": len(extractor.entities),
                "rel_count": len(extractor.relationships)
            })
            
            # Load entities
            for entity_name, entity in extractor.entities.items():
                entity_query = """
                    MATCH (ont:Ontology {name: $ontology_name})
                    CREATE (e:Entity {
                        name: $name,
                        entity_type: $type,
                        namespace: $namespace,
                        description: $description
                    })
                    CREATE (ont)-[:CONTAINS_ENTITY]->(e)
                """
                
                neo4j_graph.query(entity_query, {
                    "ontology_name": ontology_name,
                    "name": entity_name,
                    "type": entity.entity_type,
                    "namespace": entity.namespace,
                    "description": entity.description
                })
            
            # Load relationships
            for rel in extractor.relationships:
                rel_query = """
                    MATCH (source:Entity {name: $source})
                    MATCH (target:Entity {name: $target})
                    CREATE (source)-[r:RELATES_TO {
                        type: $rel_type,
                        name: $rel_name
                    }]->(target)
                """
                
                try:
                    neo4j_graph.query(rel_query, {
                        "source": rel.source,
                        "target": rel.target,
                        "rel_type": rel.relation_type,
                        "rel_name": rel.name
                    })
                except Exception as e:
                    logger.warning(f"Could not create relationship {rel.name}: {e}")
            
            extraction_tasks[task_id]["progress"] = 0.95
            logger.info(f"[Task {task_id}] Loaded to Neo4j: {ontology_name}")
        
        # Mark as completed
        extraction_tasks[task_id]["status"] = "completed"
        extraction_tasks[task_id]["progress"] = 1.0
        extraction_tasks[task_id]["entities"] = len(extractor.entities)
        extraction_tasks[task_id]["relationships"] = len(extractor.relationships)
        extraction_tasks[task_id]["entity_types"] = list(extractor.entity_types)
        
        # Clean up temp file
        try:
            file_path.unlink()
            temp_dir.rmdir()
        except Exception as e:
            logger.debug(f"Could not clean up temp file: {e}")
        
        return ExtractionResponse(
            status="success",
            task_id=task_id,
            entities_extracted=len(extractor.entities),
            relationships_extracted=len(extractor.relationships),
            entity_types=list(extractor.entity_types),
            message=f"Successfully extracted {len(extractor.entities)} entities "
                   f"from {file.filename}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        extraction_tasks[task_id] = {
            "status": "failed",
            "progress": 0,
            "error": str(e)
        }
        logger.error(f"[Task {task_id}] Extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"3DXML extraction failed: {str(e)}"
        )


@router.get("/3dxml/status/{task_id}", response_model=ExtractionStatus)
async def get_extraction_status(task_id: str):
    """Get status of 3DXML extraction task"""
    
    if task_id not in extraction_tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )
    
    task = extraction_tasks[task_id]
    
    return ExtractionStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        progress=task.get("progress", 0),
        entities_extracted=task.get("entities"),
        relationships_extracted=task.get("relationships"),
        error=task.get("error")
    )


@router.get("/3dxml/formats")
async def get_supported_formats():
    """Get list of supported ontology formats"""
    return {
        "status": "success",
        "formats": [
            {
                "format": "3DXML",
                "extension": ".3dxml",
                "description": "3DEXPERIENCE CAD product structures"
            },
            {
                "format": "SPLM_SCHEMA",
                "extension": "folder structure",
                "description": "SPLM schema with Business/Objects/Relationships folders"
            }
        ]
    }
