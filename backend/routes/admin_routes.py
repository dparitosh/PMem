"""
Admin Routes - Schema Management
Provides endpoints for database cleaning and schema operations
"""

from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

# Test endpoint
@router.get("/health")
async def admin_health():
    """Admin health check - always accessible"""
    return {"status": "admin_ok", "message": "Admin routes loaded"}

# Import schema cleaner (optional - graceful fallback if not available)
try:
    # Use absolute import so this module is importable in test contexts
    from Services.neo4j_schema_cleaner import Neo4jSchemaCleaner
    SCHEMA_CLEANER_AVAILABLE = True
except Exception as e:
    logger.warning(f"Schema cleaner not available: {e}")
    SCHEMA_CLEANER_AVAILABLE = False
    Neo4jSchemaCleaner = None


@router.post("/clean-schema")
async def clean_neo4j_schema():
    """
    Clean Neo4j database: delete all nodes, relationships, AND ontology metadata
    ✅ UPDATED: Also clears orphaned ontology metadata from filesystem
    WARNING: This is destructive. Use only in testing/development.
    """
    if not SCHEMA_CLEANER_AVAILABLE or not Neo4jSchemaCleaner:
        raise HTTPException(status_code=503, detail="Schema cleaner not available")
    
    try:
        # 1. Clean database
        cleaner = Neo4jSchemaCleaner()
        result = cleaner.reset_database(recreate_indexes=True)
        cleaner.close()
        
        # 2. ✅ FIXED: Also clear ontology metadata so names don't persist
        try:
            # Import using absolute path to avoid relative-import failures in tests
            from Services.ontology_upload_manager import OntologyUploadManager
            metadata_result = OntologyUploadManager.clear_all_metadata()
            metadata_cleared = metadata_result.get('cleared', 0)
        except Exception as e:
            logger.warning(f"Could not clear metadata: {e}")
            metadata_cleared = 0
        
        return {
            "status": result.get("status"),
            "message": result.get("message") + f" [Metadata files cleared: {metadata_cleared}]",
            "before": result.get("before"),
            "after": result.get("after"),
            "metadata_cleared": metadata_cleared
        }
    except Exception as e:
        logger.exception("Failed to clean schema")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema-stats")
async def get_schema_stats():
    """Get current Neo4j schema statistics"""
    if not SCHEMA_CLEANER_AVAILABLE or not Neo4jSchemaCleaner:
        raise HTTPException(status_code=503, detail="Schema cleaner not available")
    
    try:
        cleaner = Neo4jSchemaCleaner()
        stats = cleaner.get_schema_stats()
        cleaner.close()
        
        return {
            "status": "success",
            "stats": {
                "total_nodes": stats.total_nodes,
                "total_relationships": stats.total_relationships,
                "node_types": stats.node_types,
                "relationship_types": stats.relationship_types,
                "indexes_count": len(stats.indexes),
                "constraints_count": len(stats.constraints)
            }
        }
    except Exception as e:
        logger.exception("Failed to get schema stats")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-database")
async def reset_database(recreate_indexes: bool = True):
    """
    Complete database reset with optional index recreation
    """
    if not SCHEMA_CLEANER_AVAILABLE or not Neo4jSchemaCleaner:
        raise HTTPException(status_code=503, detail="Schema cleaner not available")
    
    try:
        cleaner = Neo4jSchemaCleaner()
        result = cleaner.reset_database(recreate_indexes=recreate_indexes)
        cleaner.close()
        
        return result
    except Exception as e:
        logger.exception("Failed to reset database")
        raise HTTPException(status_code=500, detail=str(e))
