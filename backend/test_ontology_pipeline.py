#!/usr/bin/env python3
"""
Test script to verify 3DEXPERIENCE ontology extraction and loading pipeline

Tests:
1. Extract SPLM schema into structured ontology
2. Load ontology into Neo4j using existing graph infrastructure
3. Verify graph connectivity
4. Validate relationships
"""

import asyncio
import logging
import json
from pathlib import Path
import sys
import os

# Ensure backend directory is in path for relative imports
backend_dir = Path(__file__).parent.absolute()
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Load environment variables
from dotenv import load_dotenv
env_file = backend_dir / '.env'
if env_file.exists():
    load_dotenv(env_file)

# Direct imports from backend modules
from Services.ontology_extractor import (
    extract_ontology,
    OntologyFormat,
    OntologyExtractorFactory
)
from core.graph import graph as neo4j_graph
from Services.ontology_upload_manager import OntologyUploadManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_extraction():
    """Test 1: Extract SPLM ontology"""
    logger.info("=" * 80)
    logger.info("TEST 1: Extract SPLM Schema")
    logger.info("=" * 80)
    
    splm_path = r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared"
    
    try:
        # Auto-detect format
        logger.info(f"Detecting format for {splm_path}...")
        detected_format = OntologyExtractorFactory._detect_format(splm_path)
        logger.info(f"Detected format: {detected_format.value}")
        
        # Extract ontology
        logger.info("Starting extraction...")
        result = await extract_ontology(splm_path, detected_format)
        
        # Display results
        metadata = result.get("metadata", {})
        stats = metadata.get("stats", {})
        
        logger.info("\n✅ Extraction Successful!")
        logger.info(f"   Source Format: {metadata.get('source_format')}")
        logger.info(f"   Source Path: {metadata.get('source_path')}")
        logger.info(f"   Entities: {stats.get('entities', 0)}")
        logger.info(f"   Relationships: {stats.get('relationships', 0)}")
        logger.info(f"   Attributes: {stats.get('unique_attributes', 0)}")
        logger.info(f"   Entity Types: {stats.get('entity_types', 0)}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Extraction failed: {e}", exc_info=True)
        return None


async def test_loading(ontology_data, ontology_name="3DEXPERIENCE_SPLM", ontology_prefix="splm"):
    """Test 2: Load ontology into Neo4j using existing graph"""
    logger.info("\n" + "="*80)
    logger.info(f"TEST 2: Load Ontology into Neo4j ({ontology_name})")
    logger.info("="*80)
    
    if not ontology_data:
        logger.warning("No ontology data to load")
        return None
    
    try:
        # Use existing Neo4j graph infrastructure
        logger.info(f"Cleaning up existing ontology data ({ontology_name})...")
        cleanup_query = f"MATCH (ont:Ontology {{name: '{ontology_name}'}}) DETACH DELETE ont"
        neo4j_graph.query(cleanup_query)
        logger.info("Cleanup complete")
        
        # Load entities
        entities = ontology_data.get("entities", {})
        logger.info(f"Loading {len(entities)} entities...")
        
        for entity_name, entity_data in entities.items():
            query = f"""
            MERGE (ont:Ontology {{name: '{ontology_name}'}})
            SET ont.ontology_prefix = '{ontology_prefix}'
            MERGE (entity:Entity {{name: $name, namespace: $namespace}})
            SET entity.entity_type = $entity_type,
                entity.description = $description,
                entity.attribute_count = $attr_count,
                entity.relationship_count = $rel_count,
                entity.ontology_prefix = '{ontology_prefix}'
            MERGE (ont)-[:CONTAINS_ENTITY]->(entity)
            """
            
            neo4j_graph.query(
                query,
                {
                    "name": entity_name,
                    "namespace": entity_data.get("namespace", ""),
                    "entity_type": entity_data.get("entity_type", "Unknown"),
                    "description": entity_data.get("description", ""),
                    "attr_count": len(entity_data.get("attributes", {})),
                    "rel_count": len(entity_data.get("relationships", []))
                }
            )
        
        # Load relationships
        relationships = ontology_data.get("relationships", [])
        logger.info(f"Loading {len(relationships)} relationships...")
        
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("relation_type", "connects")
            
            if source and target:
                query = """
                MATCH (source:Entity {name: $source})
                MATCH (target:Entity {name: $target})
                MERGE (source)-[r:RELATES_TO {type: $rel_type}]->(target)
                """
                
                neo4j_graph.query(
                    query,
                    {"source": source, "target": target, "rel_type": rel_type}
                )
        
        logger.info("\n✅ Loading Successful!")
        logger.info(f"   Entities Loaded: {len(entities)}")
        logger.info(f"   Relationships Loaded: {len(relationships)}")
        
        return {
            "ontology_name": ontology_name,
            "ontology_prefix": ontology_prefix,
            "entities_loaded": len(entities),
            "relationships_loaded": len(relationships),
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"❌ Loading failed: {e}", exc_info=True)
        return None


async def test_connectivity():
    """Test 3: Verify graph connectivity"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Verify Graph Connectivity")
    logger.info("=" * 80)
    
    try:
        query = """
        MATCH (ont:Ontology {name: '3DEXPERIENCE_SPLM'})-[:CONTAINS_ENTITY]->(e:Entity)
        WITH count(e) as total_entities
        
        MATCH (ont:Ontology {name: '3DEXPERIENCE_SPLM'})-[:CONTAINS_ENTITY]->(e1:Entity)
        WHERE (e1)-[]-() 
        WITH count(e1) as connected_entities, total_entities
        
        MATCH (ont:Ontology {name: '3DEXPERIENCE_SPLM'})-[:CONTAINS_ENTITY]->(e:Entity)
        MATCH (e)-[r]->()
        WITH count(r) as total_relationships, connected_entities, total_entities
        
        RETURN {
            total_entities: total_entities,
            connected_entities: connected_entities,
            connectivity_percent: CASE WHEN total_entities > 0 
                                      THEN (connected_entities * 100.0 / total_entities) 
                                      ELSE 0 
                                  END,
            total_relationships: total_relationships,
            is_fully_connected: connected_entities = total_entities
        } as stats
        """
        
        result = neo4j_graph.query(query)
        
        if result and len(result) > 0:
            stats = result[0]["stats"]
            
            logger.info("\n✅ Connectivity Check Complete!")
            logger.info(f"   Total Entities: {stats.get('total_entities', 0)}")
            logger.info(f"   Connected Entities: {stats.get('connected_entities', 0)}")
            logger.info(f"   Connectivity: {stats.get('connectivity_percent', 0):.1f}%")
            logger.info(f"   Total Relationships: {stats.get('total_relationships', 0)}")
            
            is_connected = stats.get('is_fully_connected', False)
            status = "✅ FULLY CONNECTED" if is_connected else "⚠️ PARTIALLY CONNECTED"
            logger.info(f"   Status: {status}")
            
            return stats
        else:
            logger.warning("No ontology found for connectivity check")
            return None
        
    except Exception as e:
        logger.error(f"❌ Connectivity check failed: {e}", exc_info=True)
        return None


async def register_ontology_metadata(ontology_name: str, stats: dict):
    """Register ontology metadata for UI discovery"""
    logger.info("\nRegistering ontology metadata...")
    try:
        # Use OntologyUploadManager to register metadata
        # Use 'splm' prefix to match Neo4j data (not the full ontology name)
        result = OntologyUploadManager.save_ontology_file(
            file_content=b'',  # SPLM data is in Neo4j, not a file
            filename=f"{ontology_name}.xlsx",
            ontology_name=ontology_name,
            prefix="splm",  # Must match Neo4j ontology_prefix
            file_type="xlsx",
            generation_type="as_is",
            description=f"{ontology_name} ontology with {stats.get('total_entities', 0)} entities and {stats.get('total_relationships', 0)} relationships"
        )
        if result.get('status') == 'success':
            logger.info(f"\u2705 Metadata registered: {result.get('ontology_id')}")
            return result
        else:
            logger.warning(f"\u274c Metadata registration failed: {result.get('error', 'Unknown error')}")
            return None
    except Exception as e:
        logger.error(f"\u274c Error registering metadata: {e}", exc_info=True)
        return None


async def test_visualization():
    """Test 4: Generate visualization data"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Generate Visualization Data")
    logger.info("=" * 80)
    
    try:
        query = """
        MATCH (ont:Ontology {name: '3DEXPERIENCE_SPLM'})
        WITH ont
        OPTIONAL MATCH (ont)-[:CONTAINS_ENTITY]->(e:Entity)
        WITH ont, count(DISTINCT e) as entity_count, collect(DISTINCT e.entity_type) as types
        OPTIONAL MATCH (ont)-[:CONTAINS_ENTITY]->(e1:Entity)-[r]->(e2:Entity)
        WITH ont, entity_count, types, count(DISTINCT r) as relationship_count
        RETURN {
            entities: entity_count,
            relationships: relationship_count,
            ontology: ont.name,
            entity_types: types
        } as stats
        """
        
        result = neo4j_graph.query(query)
        
        if result and len(result) > 0:
            stats = result[0]["stats"]
            logger.info("\n✅ Visualization Data Generated!")
            logger.info(f"   Entities: {stats.get('entities', 0)}")
            logger.info(f"   Relationships: {stats.get('relationships', 0)}")
            logger.info(f"   Entity Types: {len(stats.get('entity_types', []))}")
            
            return stats
        else:
            logger.warning("No ontology found for visualization")
            return None
        
    except Exception as e:
        logger.error(f"❌ Visualization generation failed: {e}", exc_info=True)
        return None


async def main():
    """Run all tests"""
    logger.info("\n")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 20 + "3DEXPERIENCE ONTOLOGY PIPELINE TEST" + " " * 24 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    logger.info("\n")
    
    # Test 1: Extraction
    ontology_data = await test_extraction()
    
    # Test 2: Loading
    if ontology_data:
        load_stats = await test_loading(ontology_data)
    else:
        load_stats = None
    
    # Register metadata (if loading successful)
    metadata_registered = None
    if load_stats:
        connectivity = await test_connectivity()
        if connectivity:
            metadata_registered = await register_ontology_metadata(
                "3DEXPERIENCE_SPLM",
                connectivity
            )
    else:
        connectivity = None
    
    # Test 4: Visualization
    if connectivity:
        viz_data = await test_visualization()
    else:
        viz_data = None
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    results = {
        "extraction": "✅ PASSED" if ontology_data else "❌ FAILED",
        "loading": "✅ PASSED" if load_stats else "❌ FAILED",
        "connectivity": "✅ PASSED" if connectivity else "❌ FAILED",
        "metadata_registration": "✅ PASSED" if metadata_registered else "❌ FAILED",
        "visualization": "✅ PASSED" if viz_data else "❌ FAILED"
    }
    
    for test, status in results.items():
        logger.info(f"{test.upper():20} {status}")
    
    overall = "✅ ALL TESTS PASSED" if all("PASSED" in s for s in results.values()) else "⚠️ SOME TESTS FAILED"
    logger.info(f"\n{overall}")
    
    logger.info("\n")


if __name__ == "__main__":
    asyncio.run(main())
