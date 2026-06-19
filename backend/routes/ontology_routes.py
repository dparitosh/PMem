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
from ..Services.ap239_mapper_service import (
    AP239MapperService,
    AP239DomainPipeline,
)
from ..Services.multi_domain_pipeline_controller import (
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
    """Delegate to generic handler — live Neo4j data only, no hardcoded catalog."""
    try:
        return await get_generic_data_dictionary(
            "ap239",
            instance_limit=2000,
            relationship_limit=500,
            fallback_limit=200,
        )
    except HTTPException as e:
        if e.status_code == 404:
            return {
                "status": "success",
                "ontology": "ap239",
                "data": {
                    "entities": {},
                    "relationships": {},
                    "properties": {},
                },
                "entity_count": 0,
                "relationship_count": 0,
                "property_count": 0,
                "source": "empty",
                "message": "No AP239 data found yet.",
            }
        raise


@router.get("/ap239/mappings/{source_format}")
async def get_ap239_mappings(source_format: str):
    """Get AP239 entity mappings — delegates to live Neo4j generic handler."""
    return await get_generic_mappings("ap239", source_format, mapping_limit=5000)


@router.get("/ap242/data-dictionary")
async def get_ap242_data_dictionary():
    """Best-effort AP242 dictionary. Returns empty payload when no AP242 data exists yet."""
    try:
        return await get_generic_data_dictionary(
            "ap242",
            instance_limit=2000,
            relationship_limit=500,
            fallback_limit=200,
        )
    except HTTPException as e:
        if e.status_code == 404:
            return {
                "status": "success",
                "ontology": "ap242",
                "data": {
                    "entities": {},
                    "relationships": {},
                    "properties": {},
                },
                "entity_count": 0,
                "relationship_count": 0,
                "property_count": 0,
                "source": "empty",
                "message": "No AP242 data found yet.",
            }
        raise


@router.get("/ap242/mappings/{source_format}")
async def get_ap242_mappings(source_format: str):
    """Best-effort AP242 mappings. Returns empty payload when no AP242 data exists yet."""
    try:
        return await get_generic_mappings("ap242", source_format, mapping_limit=5000)
    except HTTPException as e:
        if e.status_code == 404:
            return {
                "status": "success",
                "source_format": source_format,
                "ontology": "ap242",
                "mappings": {},
                "mapping_edges": [],
                "mapping_count": 0,
                "source": "empty",
                "message": "No AP242 data found yet.",
            }
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GENERIC ONTOLOGY ENDPOINTS (any uploaded ontology prefix)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_INTERNAL_PROPS = {"ontology_prefix", "ontology_id", "ontology_name", "source_ontology",
                   "version", "created_at", "updated_at", "id", "elementId",
                   "prefix", "source_format", "source_file"}


@router.get("/{prefix}/data-dictionary")
async def get_generic_data_dictionary(
    prefix: str,
    instance_limit: int = Query(default=2000, ge=100, le=20000),
    relationship_limit: int = Query(default=500, ge=50, le=5000),
    fallback_limit: int = Query(default=200, ge=50, le=2000),
):
    """
    Build a live data dictionary from Neo4j for any ontology prefix.

    Three-layer query strategy:
    1. OntologyClass nodes with {prefix = $prefix}  — written by push_to_neo4j (ontology upload flow).
       Gives class names, concept_type, namespace.  OntologyProperty nodes linked via PROPERTY_OF
       give per-class properties when present.
    2. For each OntologyClass name found, look at actual Neo4j nodes carrying that label
       to derive the real property keys that were written by the data-import commit.
    3. Relationship types between nodes carrying those class labels → relationships section.

    Fallback: derive a lightweight dictionary from live instance labels/properties when no schema nodes exist.
    """
    try:
        normalized_prefix = (prefix or "").strip()
        if not normalized_prefix:
            raise HTTPException(status_code=400, detail="Ontology prefix is required")

        from ..core.graph import get_graph
        graph = get_graph()

        entities: Dict[str, Any] = {}
        all_props: Dict[str, Any] = {}
        relationships: Dict[str, Any] = {}

        # ── 1. OntologyClass schema nodes (ontology upload / push-to-neo4j flow) ─
        schema_rows = graph.query(
            """
            MATCH (c:OntologyClass)
            WHERE coalesce(c.ontology_prefix, c.prefix) = $prefix
            OPTIONAL MATCH (p:OntologyProperty)-[:PROPERTY_OF]->(c)
            RETURN c.name         AS name,
                   c.concept_type AS concept_type,
                   c.namespace    AS namespace,
                   collect(DISTINCT p.name) AS schema_props
            ORDER BY c.name
            """,
            {"prefix": normalized_prefix},
        )

        class_names: List[str] = []
        for row in (schema_rows or []):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            class_names.append(name)
            # OntologyProperty nodes (schema_props) - may be empty if push_to_neo4j
            # didn't create OntologyProperty nodes. We'll enrich from instance data next.
            static_props = [p for p in (row.get("schema_props") or []) if p]
            entities[name] = {
                "type": name,
                "concept_type": row.get("concept_type") or "Class",
                "namespace": row.get("namespace") or normalized_prefix,
                "ontology_prefix": normalized_prefix,
                "source": "schema",
                "properties": static_props,
            }
            for p in static_props:
                all_props.setdefault(p, {"name": p, "classes": []})
                all_props[p]["classes"].append(name)

        # ── 2. Instance data nodes — property keys from nodes with OntologyClass labels ─
        # This captures the actual fields written by the data-import commit flow.
        if class_names:
            inst_rows = graph.query(
                """
                MATCH (n)
                WHERE any(lbl IN labels(n) WHERE lbl IN $class_names)
                  AND coalesce(n.ontology_prefix, n.prefix) = $prefix
                RETURN DISTINCT labels(n) AS labels, keys(n) AS prop_keys
                LIMIT toInteger($instance_limit)
                """,
                {
                    "class_names": class_names,
                    "prefix": normalized_prefix,
                    "instance_limit": instance_limit,
                },
            )
            for row in (inst_rows or []):
                matched_label = next(
                    (lbl for lbl in (row.get("labels") or []) if lbl in class_names), None
                )
                if matched_label and matched_label in entities:
                    for key in (row.get("prop_keys") or []):
                        if key and key not in _INTERNAL_PROPS:
                            if key not in entities[matched_label]["properties"]:
                                entities[matched_label]["properties"].append(key)
                            all_props.setdefault(key, {"name": key, "classes": []})
                            if matched_label not in all_props[key]["classes"]:
                                all_props[key]["classes"].append(matched_label)

            # ── 3. Relationship types between nodes of OntologyClass labels ──────
            rel_rows = graph.query(
                """
                MATCH (a)-[r]->(b)
                WHERE any(la IN labels(a) WHERE la IN $class_names)
                  AND any(lb IN labels(b) WHERE lb IN $class_names)
                                    AND coalesce(a.ontology_prefix, a.prefix) = $prefix
                                    AND coalesce(b.ontology_prefix, b.prefix) = $prefix
                RETURN DISTINCT type(r)      AS rel_type,
                                                             head([la IN labels(a) WHERE la IN $class_names]) AS from_class,
                                                             head([lb IN labels(b) WHERE lb IN $class_names]) AS to_class
                                LIMIT toInteger($relationship_limit)
                """,
                                {
                                        "class_names": class_names,
                                        "prefix": normalized_prefix,
                                        "relationship_limit": relationship_limit,
                                },
            )
            for row in (rel_rows or []):
                rt = row.get("rel_type")
                if not rt:
                    continue
                if rt not in relationships:
                    relationships[rt] = {"type": rt, "connections": []}
                from_class = row.get("from_class")
                to_class = row.get("to_class")
                if from_class and to_class:
                    relationships[rt]["connections"].append({
                        "from": from_class,
                        "to": to_class,
                    })

            # Relationships between OntologyClass nodes (schema-only uploads)
            oc_rows = graph.query(
                """
                MATCH (a:OntologyClass)-[r]->(b:OntologyClass)
                WHERE coalesce(a.ontology_prefix, a.prefix) = $prefix
                  AND coalesce(b.ontology_prefix, b.prefix) = $prefix
                RETURN DISTINCT type(r) AS rel_type,
                                a.name AS from_class,
                                b.name AS to_class
                LIMIT toInteger($relationship_limit)
                """,
                {
                    "prefix": normalized_prefix,
                    "relationship_limit": relationship_limit,
                },
            )
            for row in (oc_rows or []):
                rt = row.get("rel_type")
                if not rt:
                    continue
                if rt not in relationships:
                    relationships[rt] = {"type": rt, "connections": []}
                from_class = row.get("from_class")
                to_class = row.get("to_class")
                if from_class and to_class:
                    relationships[rt]["connections"].append({
                        "from": from_class,
                        "to": to_class,
                    })

            # Relationships between OntologyProperty nodes and OntologyClass nodes (schema props)
            # This is important for XMI-derived ontologies like SysML/AP239 where class-to-class
            # relationships may be sparse but PROPERTY_OF edges exist and should appear in the
            # Mapping Vocabulary view.
            prop_rows = graph.query(
                """
                MATCH (p:OntologyProperty)-[:PROPERTY_OF]->(c:OntologyClass)
                WHERE coalesce(p.ontology_prefix, p.prefix) = $prefix
                  AND coalesce(c.ontology_prefix, c.prefix) = $prefix
                RETURN DISTINCT
                  'PROPERTY_OF' AS rel_type,
                  coalesce(p.name, p.key, p.id) AS from_term,
                  c.name AS to_term
                LIMIT toInteger($relationship_limit)
                """,
                {
                    "prefix": normalized_prefix,
                    "relationship_limit": relationship_limit,
                },
            )
            for row in (prop_rows or []):
                rt = row.get("rel_type")
                if not rt:
                    continue
                if rt not in relationships:
                    relationships[rt] = {"type": rt, "connections": []}
                from_term = (row.get("from_term") or "").strip()
                to_term = (row.get("to_term") or "").strip()
                if from_term and to_term:
                    relationships[rt]["connections"].append({
                        "from": from_term,
                        "to": to_term,
                    })
            
            # ── 3b. Fallback: Check for Instance node relationships ──────
            # If no relationships found via class labels, try Instance nodes
            if not relationships and class_names:
                inst_rel_rows = graph.query(
                    """
                    MATCH (a:Instance {prefix: $prefix})-[r]->(b:Instance {prefix: $prefix})
                    WHERE a.type IN $class_names AND b.type IN $class_names
                    RETURN DISTINCT type(r) AS rel_type,
                                    a.type AS from_class,
                                    b.type AS to_class
                    LIMIT toInteger($relationship_limit)
                    """,
                    {
                        "class_names": class_names,
                        "prefix": normalized_prefix,
                        "relationship_limit": relationship_limit,
                    },
                )
                for row in (inst_rel_rows or []):
                    rt = row.get("rel_type")
                    if not rt:
                        continue
                    if rt not in relationships:
                        relationships[rt] = {"type": rt, "connections": []}
                    from_class = row.get("from_class")
                    to_class = row.get("to_class")
                    if from_class and to_class:
                        relationships[rt]["connections"].append({
                            "from": from_class,
                            "to": to_class,
                        })

        # ── 4. Instance-node fallback: when no OntologyClass schema nodes exist,
        #       derive entities from actual Neo4j nodes with ontology_prefix = prefix.
        if not entities:
            inst_fallback = graph.query(
                """
                MATCH (n)
                                WHERE coalesce(n.ontology_prefix, n.prefix) = $prefix
                  AND NOT (n:DatasheetChunk OR n:GraphChunk)
                WITH labels(n) AS lbls, keys(n) AS ks
                UNWIND lbls AS lbl
                WITH lbl, collect(DISTINCT ks) AS prop_sets
                RETURN lbl, prop_sets
                                LIMIT toInteger($fallback_limit)
                """,
                                {"prefix": normalized_prefix, "fallback_limit": fallback_limit},
            )
            for row in (inst_fallback or []):
                lbl = row.get("lbl")
                if not lbl or lbl in ("OntologyClass", "OntologyProperty"):
                    continue
                props = sorted({
                    k
                    for ks in (row.get("prop_sets") or [])
                    for k in ks
                    if k and k not in _INTERNAL_PROPS
                })
                if lbl not in entities:
                    entities[lbl] = {
                        "type": lbl,
                        "concept_type": "Class",
                        "namespace": normalized_prefix,
                        "ontology_prefix": normalized_prefix,
                        "source": "instance",
                        "properties": props,
                    }
                for p in props:
                    all_props.setdefault(p, {"name": p, "classes": []})
                    if lbl not in all_props[p]["classes"]:
                        all_props[p]["classes"].append(lbl)

        if not entities and not all_props:
            raise HTTPException(
                status_code=404,
                detail=f"No data found in Neo4j for ontology prefix '{normalized_prefix}'. "
                       f"Commit an import with this prefix first.",
            )

        return {
            "status": "success",
            "ontology": normalized_prefix,
            "data": {
                "entities": entities,
                "relationships": relationships,
                "properties": all_props,
            },
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "property_count": len(all_props),
            "source": "neo4j_live",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to retrieve data dictionary for prefix '{prefix}'")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{prefix}/mappings/{source_format}")
async def get_generic_mappings(
    prefix: str,
    source_format: str,
    mapping_limit: int = Query(default=5000, ge=100, le=20000),
):
    """
    Get entity mappings for any ontology prefix + source format combination.
    Derives label-to-label mappings from live Neo4j relationship types.
    """
    try:
        normalized_prefix = (prefix or "").strip()
        if not normalized_prefix:
            raise HTTPException(status_code=400, detail="Ontology prefix is required")

        from ..core.graph import get_graph
        graph = get_graph()
        normalized_source_format = (source_format or "").strip().lower()
        rows = graph.query(
            """
            MATCH (a)-[r]->(b)
            WITH a, b, r,
                 toLower(
                   coalesce(
                     a.source_format,
                     a.file_type,
                     a.source_format_detected,
                     ''
                   )
                 ) AS src_fmt
                        WHERE coalesce(a.ontology_prefix, a.prefix) = $prefix
                            AND coalesce(b.ontology_prefix, b.prefix) = $prefix
              AND (src_fmt = '' OR src_fmt = $source_format)
            RETURN DISTINCT
              CASE
                WHEN 'OntologyClass' IN labels(a) THEN coalesce(a.name, labels(a)[0])
                WHEN 'OntologyProperty' IN labels(a) THEN coalesce(a.name, labels(a)[0])
                ELSE labels(a)[0]
              END AS from_label,
              CASE
                WHEN 'OntologyClass' IN labels(b) THEN coalesce(b.name, labels(b)[0])
                WHEN 'OntologyProperty' IN labels(b) THEN coalesce(b.name, labels(b)[0])
                ELSE labels(b)[0]
              END AS to_label,
              type(r) AS rel
            LIMIT toInteger($mapping_limit)
            """,
            {
                "prefix": normalized_prefix,
                "source_format": normalized_source_format,
                "mapping_limit": mapping_limit,
            },
        )

        mapping_edges = [
            {
                "source_label": row.get("from_label"),
                "target_label": row.get("to_label"),
                "mapping_type": row.get("rel", "mapsTo"),
                "source_term": f"{source_format}:{row.get('from_label')}",
                "target_term": f"{normalized_prefix}:{row.get('to_label')}",
            }
            for row in (rows or [])
            if row.get("from_label") and row.get("to_label")
        ]

        # Keep legacy dict format for backwards compatibility,
        # but include target label in key to avoid overwrite collisions.
        mappings = {
            f"{e['source_label']}_{e['mapping_type']}_{e['target_label']}": e["target_label"]
            for e in mapping_edges
        }

        return {
            "status": "success",
            "source_format": source_format,
            "ontology": normalized_prefix,
            "mappings": mappings,
            "mapping_edges": mapping_edges,
            "mapping_count": len(mapping_edges),
        }
    except Exception as e:
        logger.exception(f"Failed to retrieve mappings for '{prefix}' / '{source_format}'")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ap239/map-entity")
async def map_entity_to_ap239(request: EntityMappingRequest):
    """
    Legacy single-entity seed mapping to AP239. Use Semantic Bridge instance.link for persisted instance-to-ontology alignment.
    
    Returns:
    - Remapped entity with AP239 type and electronics properties
    """
    try:
        mapped_entity = AP239MapperService.map_entity_to_ap239(
            request.entity,
            request.source_format
        )

        # If the UI provided an explicit target selection, honor it.
        try:
            entity = dict(request.entity or {})
            props = dict(entity.get("properties") or {})
            selected_target = props.get("selected_target")
            if selected_target:
                mapped_entity["type"] = selected_target
        except Exception:
            pass
        
        return {
            "status": "success",
            "original_entity": request.entity,
            "mapped_entity": mapped_entity,
            "electronics_properties": mapped_entity.get("electronics_properties", {}),
            "deprecated": True,
            "mode": "legacy_single_entity_seed_mapping",
            "replacement_workflow": "instance.link",
            "replacement_endpoint": "/api/v1/workflows/execute",
        }
    except Exception as e:
        logger.exception("Failed to map entity to AP239")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{prefix}/map-entity")
async def map_entity_generic(prefix: str, request: EntityMappingRequest):
    """
    Generic map-entity endpoint for non-AP239 ontologies.
    Uses the UI-selected target (if provided) to set the mapped type.
    """
    try:
        normalized_prefix = (prefix or "").strip()
        if not normalized_prefix:
            raise HTTPException(status_code=400, detail="Ontology prefix is required")

        entity = dict(request.entity or {})
        props = dict(entity.get("properties") or {})
        selected_target = props.get("selected_target")

        mapped_entity = dict(entity)
        if selected_target:
            mapped_entity["type"] = selected_target

        mapped_entity.setdefault("properties", {})
        mapped_entity["properties"].update({
            "mapped_from_ui": True,
            "mapping_prefix": normalized_prefix,
        })

        return {
            "status": "success",
            "ontology": normalized_prefix,
            "original_entity": entity,
            "mapped_entity": mapped_entity,
            "mapping_strategy": "ui_selected_target" if selected_target else "passthrough",
            "deprecated": True,
            "mode": "legacy_single_entity_seed_mapping",
            "replacement_workflow": "instance.link",
            "replacement_endpoint": "/api/v1/workflows/execute",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to map entity (generic)")
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
