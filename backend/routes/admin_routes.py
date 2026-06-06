"""
Admin Routes - Schema Management
Provides endpoints for database cleaning and schema operations
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])
CLEAN_SCHEMA_CONFIRM_TOKEN = "CLEAN_NEO4J_SCHEMA"


class CleanSchemaRequest(BaseModel):
    confirm: str | None = None

# Test endpoint
@router.get("/health")
async def admin_health():
    """Admin health check - always accessible"""
    return {"status": "admin_ok", "message": "Admin routes loaded"}

# Import schema cleaner (optional - graceful fallback if not available)
try:
    from backend.Services.neo4j_schema_cleaner import Neo4jSchemaCleaner
    SCHEMA_CLEANER_AVAILABLE = True
except Exception as e:
    try:
        from Services.neo4j_schema_cleaner import Neo4jSchemaCleaner
        SCHEMA_CLEANER_AVAILABLE = True
    except Exception as fallback_error:
        logger.warning(f"Schema cleaner not available: {e}; fallback failed: {fallback_error}")
        SCHEMA_CLEANER_AVAILABLE = False
        Neo4jSchemaCleaner = None


@router.post("/clean-schema")
async def clean_neo4j_schema(body: CleanSchemaRequest | None = None):
    """
    Clean Neo4j database: delete all nodes, relationships, AND ontology metadata
    ✅ UPDATED: Also clears orphaned ontology metadata from filesystem
    WARNING: This is destructive. Use only in testing/development.
    """
    if not SCHEMA_CLEANER_AVAILABLE or not Neo4jSchemaCleaner:
        raise HTTPException(status_code=503, detail="Schema cleaner not available")

    if not body or body.confirm != CLEAN_SCHEMA_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation token required: confirm='{CLEAN_SCHEMA_CONFIRM_TOKEN}'",
        )
    
    try:
        # 1. Clean database and schema. The UI action is a destructive full schema clean,
        # so leave indexes/constraints empty instead of recreating default indexes.
        cleaner = Neo4jSchemaCleaner()
        try:
            result = cleaner.reset_database(recreate_indexes=False)
        finally:
            cleaner.close()

        if result.get("status") != "SUCCESS":
            raise HTTPException(status_code=500, detail=result.get("message", "Schema cleanup failed"))
        
        # 2. ✅ FIXED: Also clear ontology metadata so names don't persist
        try:
            # Import using absolute path to avoid relative-import failures in tests
            try:
                from backend.Services.ontology_upload_manager import OntologyUploadManager
            except ImportError:
                from Services.ontology_upload_manager import OntologyUploadManager
            metadata_result = OntologyUploadManager.clear_all_metadata()
            metadata_cleared = metadata_result.get('cleared', 0)
        except Exception as e:
            logger.warning(f"Could not clear metadata: {e}")
            metadata_cleared = 0
        
        return {
            "success": True,
            "status": result.get("status"),
            "message": result.get("message") + f" [Metadata files cleared: {metadata_cleared}]",
            "before": result.get("before"),
            "after": result.get("after"),
            "metadata_cleared": metadata_cleared
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
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
        custom_indexes = [
            index
            for index in stats.indexes
            if ": LOOKUP" not in str(index).upper()
        ]
        lookup_indexes = [
            index
            for index in stats.indexes
            if ": LOOKUP" in str(index).upper()
        ]
        
        return {
            "status": "success",
            "stats": {
                "total_nodes": stats.total_nodes,
                "total_relationships": stats.total_relationships,
                "node_types": stats.node_types,
                "relationship_types": stats.relationship_types,
                "indexes_count": len(custom_indexes),
                "lookup_indexes_count": len(lookup_indexes),
                "constraints_count": len(stats.constraints)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to reset database")
        raise HTTPException(status_code=500, detail=str(e))
