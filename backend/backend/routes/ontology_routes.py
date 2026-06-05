"""
API Routes for AP239 Ontology Mapper and Multi-Domain Pipelines

Endpoints:
- /ontologies/ap239/data-dictionary - AP239 entity definitions
- /ontologies/ap239/mappings/{source_format} - Get AP239 mappings
- /pipelines/domains - List all available industry domains
- /pipelines/process - Process data through domain-specific pipeline
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import logging

# Import services
from ..services.ap239_mapper_service import (
    AP239MapperService,
    AP239DomainPipeline,
    AP239Entity,
)
from ..services.multi_domain_pipeline_controller import (
    MultiDomainPipelineController,
    IndustryDomain,
    DomainPipelineConfig,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ontology", tags=["Ontology & Multi-Domain"])


class EntityMappingRequest(BaseModel):
    """Request to map entity to AP239"""
    entity: Dict[str, Any]
    source_format: str


class DomainPipelineRequest(BaseModel):
    """Request to process data through domain pipeline"""
    entities: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    domain: str
    task_id: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AP239 ONTOLOGY ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/ap239/data-dictionary")
async def get_ap239_data_dictionary():
    """
    Get AP239 entity definitions and property specifications.
    
    Returns:
    - entities: Entity type definitions (ElectronicAssembly, SignalNet, etc.)
    - relationships: Relationship type definitions
    - properties: Standard electrical properties (voltage, current, impedance, etc.)
    """
    try:
        dictionary = AP239MapperService.get_ap239_data_dictionary()
        return {
            "status": "success",
            "ontology": "ap239",
            "data": dictionary,
            "entity_count": len(dictionary.get("entities", {})),
            "relationship_count": len(dictionary.get("relationships", {})),
            "property_count": len(dictionary.get("properties", {})),
        }
    except Exception as e:
        logger.exception("Failed to retrieve AP239 data dictionary")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ap239/mappings/{source_format}")
async def get_ap239_mappings(source_format: str):
    """
    Get AP239 entity mappings for a specific source format.
    
    Parameters:
    - source_format: Source format type (plmxml, step, xmi, xml)
    
    Returns:
    - Mapping of source entity types to AP239 types
    """
    try:
        mappings = AP239MapperService.get_ap239_mapping(source_format)
        if not mappings:
            raise HTTPException(
                status_code=400,
                detail=f"No mappings available for format: {source_format}"
            )
        
        return {
            "status": "success",
            "source_format": source_format,
            "ontology": "ap239",
            "mappings": mappings,
            "mapping_count": len(mappings),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retrieve AP239 mappings for {source_format}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ap239/map-entity")
async def map_entity_to_ap239(request: EntityMappingRequest):
    """
    Map a single entity to AP239 ontology.
    
    Returns:
    - Remapped entity with AP239 type and electronics properties
    """
    try:
        mapped_entity = AP239MapperService.map_entity_to_ap239(
            request.entity,
            request.source_format
        )
        
        return {
            "status": "success",
            "original_entity": request.entity,
            "mapped_entity": mapped_entity,
            "electronics_properties": mapped_entity.get("electronics_properties", {}),
        }
    except Exception as e:
        logger.exception("Failed to map entity to AP239")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ap239/domain-pipelines")
async def get_ap239_domain_pipelines():
    """
    Get available AP239 domain-specific pipelines.
    
    Returns:
    - Schematic capture pipeline
    - PCB design pipeline
    - Test & verification pipeline
    - Manufacturing pipeline
    """
    try:
        pipelines = AP239DomainPipeline.get_domain_pipelines()
        
        return {
            "status": "success",
            "ontology": "ap239",
            "domain": "electronics",
            "pipelines": pipelines,
            "pipeline_count": len(pipelines),
            "description": "Domain-specific data pipelines for electronics design and manufacturing",
        }
    except Exception as e:
        logger.exception("Failed to retrieve AP239 domain pipelines")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MULTI-DOMAIN PIPELINE ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/pipelines/domains")
async def get_available_domains():
    """
    Get all available industry domains for data import pipelines.
    
    Returns:
    - Railway/Transportation: track, signals, rolling stock, coupling
    - Automotive: powertrains, electrical, safety, emissions
    - Aerospace: FMEA, configuration management, maintenance
    - Electronics: schematics, PCB, signal integrity
    - Industrial: structural, motion, electrical, operations
    """
    try:
        domains = MultiDomainPipelineController.get_available_domains()
        
        return {
            "status": "success",
            "domains": domains,
            "domain_count": len(domains),
            "supported_formats_summary": _get_formats_by_domain(domains),
        }
    except Exception as e:
        logger.exception("Failed to retrieve available domains")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipelines/domain/{domain_name}")
async def get_domain_configuration(domain_name: str):
    """
    Get detailed configuration for a specific domain.
    
    Parameters:
    - domain_name: Domain name (railway, automotive, aerospace, electronics, industrial)
    
    Returns:
    - Detailed domain configuration including validation rules and enrichment modules
    """
    try:
        # Find matching domain
        domain_enum = None
        for d in IndustryDomain:
            if d.value == domain_name.lower():
                domain_enum = d
                break
        
        if not domain_enum:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown domain: {domain_name}. Available: railway, automotive, aerospace, electronics, industrial"
            )
        
        config = DomainPipelineConfig.get_domain_config(domain_enum)
        
        return {
            "status": "success",
            "domain": domain_name,
            "configuration": config,
            "required_entities": config.get("required_entities", []),
            "validation_rules": config.get("validation_rules", []),
            "enrichment_modules": config.get("enrichment_modules", []),
            "quality_metrics": config.get("quality_metrics", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retrieve configuration for domain: {domain_name}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipelines/process")
async def process_data_through_pipeline(request: DomainPipelineRequest):
    """
    Process data through domain-specific pipeline.
    
    Parameters:
    - entities: List of extracted entities
    - relationships: List of extracted relationships
    - domain: Target domain (railway, automotive, aerospace, electronics, industrial)
    - task_id: Optional task identifier for tracking
    
    Returns:
    - Validation results
    - Enriched entities
    - Domain-specific metrics
    """
    try:
        # Find matching domain
        domain_enum = None
        for d in IndustryDomain:
            if d.value == request.domain.lower():
                domain_enum = d
                break
        
        if not domain_enum:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown domain: {request.domain}"
            )
        
        # Process through pipeline
        controller = MultiDomainPipelineController()
        result = await controller.process_with_domain(
            request.entities,
            request.relationships,
            domain_enum,
            request.task_id or ""
        )
        
        return {
            "status": "success",
            "pipeline_result": result,
            "total_entities_processed": len(request.entities),
            "total_relationships": len(request.relationships),
            "validation_status": result.get("stages", {}).get("validation", {}).get("overall_status", "unknown"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to process data through {request.domain} pipeline")
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _get_formats_by_domain(domains: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extract supported formats by domain for summary."""
    summary = {}
    for domain_name, domain_info in domains.items():
        summary[domain_name] = domain_info.get("supported_formats", [])
    return summary

