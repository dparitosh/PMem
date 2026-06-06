"""
Admin Routes - Schema Management
Provides endpoints for database cleaning and schema operations
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import logging
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])
CLEAN_SCHEMA_CONFIRM_TOKEN = "CLEAN_NEO4J_SCHEMA"


class CleanSchemaRequest(BaseModel):
    confirm: str | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _mask_uri(uri: str | None) -> str:
    if not uri:
        return ""
    try:
        parsed = urlparse(uri)
        if not parsed.scheme:
            return "***"
        hostname = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        masked_host = "localhost" if hostname in {"localhost", "127.0.0.1"} else "***"
        return urlunparse((parsed.scheme, f"{masked_host}{port}", parsed.path, "", "", ""))
    except Exception:
        return "***"


def _frontend_mapped_paths() -> set[str]:
    config_path = _project_root() / "frontend" / "src" / "config.js"
    if not config_path.exists():
        return set()
    try:
        text = config_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return set()
    paths = set()
    for match in re.findall(r"['\"](/[^'\"]+)['\"]", text):
        paths.add(match.split("?", 1)[0])
    return paths


def _service_group(path: str, tag: str) -> str:
    if tag and tag != "default":
        return tag.replace("v1-", "").replace("_", " ").title()
    parts = [part for part in path.split("/") if part and not part.startswith("{")]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "v1":
        return parts[2].replace("-", " ").title()
    return parts[0].replace("-", " ").title() if parts else "Core"


def _discover_api_routes(request: Request) -> list[dict]:
    mapped_paths = _frontend_mapped_paths()
    routes = []
    try:
        openapi = request.app.openapi()
        for path, methods in sorted(openapi.get("paths", {}).items()):
            for method, operation in sorted(methods.items()):
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                tag = (operation.get("tags") or ["default"])[0]
                frontend_mapped = path in mapped_paths or any(
                    path.replace("{", "{").startswith(mapped_path.rstrip("/{"))
                    for mapped_path in mapped_paths
                )
                routes.append({
                    "method": method.upper(),
                    "path": path,
                    "tag": tag,
                    "service_group": _service_group(path, tag),
                    "frontend_mapped": frontend_mapped,
                })
    except Exception as exc:
        logger.warning("OpenAPI route discovery failed: %s", exc)
    return routes


def _neo4j_datasource() -> dict:
    try:
        try:
            from backend.core.db_config import get_config
        except ImportError:
            from core.db_config import get_config
        config = get_config()
        return {
            "id": "neo4j",
            "name": "Neo4j Knowledge Graph",
            "type": "graph_database",
            "status": "configured",
            "uri_masked": _mask_uri(config.uri),
            "database": config.database,
            "mutable": False,
        }
    except Exception as exc:
        return {
            "id": "neo4j",
            "name": "Neo4j Knowledge Graph",
            "type": "graph_database",
            "status": "degraded",
            "uri_masked": "",
            "database": "",
            "mutable": False,
            "message": str(exc),
        }


def _llm_settings() -> dict:
    provider = (os.getenv("USE_LLM") or "ollama").lower()
    model = os.getenv("LLM_MODEL_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT") or "llama3:latest"
    endpoint = os.getenv("OLLAMA_BASE_URL") or os.getenv("AZURE_OPENAI_ENDPOINT") or "http://localhost:11434"
    status = "configured" if endpoint and model else "degraded"
    return {
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "status": status,
    }


def _workflow_registry() -> list[dict]:
    return [
        {
            "id": "ontology.create",
            "label": "Create Ontology",
            "category": "Ontology",
            "inputs": "EXPRESS, XSD, OWL, CSV, namespace metadata",
            "outputs": "OWL/TTL ontology, prefix registry, retained artifact",
            "writes_to_neo4j": False,
            "retains_artifacts": True,
        },
        {
            "id": "instance.import",
            "label": "Import Instance Graph",
            "category": "Import",
            "inputs": "STEP, STP, STPX, PLMXML, XMI, CSV",
            "outputs": "Neo4j instance graph, parse report, retained artifact",
            "writes_to_neo4j": True,
            "retains_artifacts": True,
        },
        {
            "id": "instance.link",
            "label": "Link Instances to Ontology",
            "category": "Mapping",
            "inputs": "Instance graph, ontology, mapping rules",
            "outputs": "Semantic links, alignment report",
            "writes_to_neo4j": True,
            "retains_artifacts": True,
        },
        {
            "id": "ontology.validate",
            "label": "Validate Ontology",
            "category": "Quality",
            "inputs": "Ontology, SHACL/rules profile",
            "outputs": "Validation issues, quality score",
            "writes_to_neo4j": False,
            "retains_artifacts": True,
        },
        {
            "id": "ontology.merge",
            "label": "Merge Ontologies",
            "category": "Ontology",
            "inputs": "Source ontology, target ontology, merge policy",
            "outputs": "Merged ontology, conflict report",
            "writes_to_neo4j": True,
            "retains_artifacts": True,
        },
        {
            "id": "dictionary.generate",
            "label": "Generate Data Dictionary",
            "category": "Governance",
            "inputs": "Ontology or namespace",
            "outputs": "Data dictionary, taxonomy terms",
            "writes_to_neo4j": False,
            "retains_artifacts": True,
        },
        {
            "id": "artifact.export",
            "label": "Export Artifacts",
            "category": "Reports",
            "inputs": "Ontology, graph, validation run",
            "outputs": "TTL, JSON, CSV, report bundle",
            "writes_to_neo4j": False,
            "retains_artifacts": True,
        },
    ]


def _package_registry() -> list[dict]:
    package_path = _project_root() / "frontend" / "package.json"
    keep = {
        "@emotion/react",
        "@emotion/styled",
        "@mui/material",
        "@mui/x-tree-view",
        "@testing-library/dom",
        "@testing-library/jest-dom",
        "@testing-library/react",
        "@testing-library/user-event",
        "ag-grid-community",
        "ag-grid-react",
        "axios",
        "bootstrap",
        "d3",
        "dompurify",
        "lucide-react",
        "react",
        "react-dom",
        "react-scripts",
        "web-vitals",
    }
    remove_candidates = {
        "@neo4j-nvl/base",
        "cytoscape-cose-bilkent",
        "cytoscape-expand-collapse",
        "framer-motion",
        "fuse",
        "fuse.js",
        "install",
        "neo4j",
        "neo4j-driver",
        "neo4j-driver-core",
        "primereact",
        "react-arborist",
        "react-cytoscapejs",
        "react-select",
        "rsuite",
        "rxjs",
        "sass",
        "three-spritetext",
    }
    packages = []
    try:
        data = json.loads(package_path.read_text(encoding="utf-8"))
        for name in sorted((data.get("dependencies") or {}).keys()):
            if name.startswith("@progress/") or name.startswith("@syncfusion/"):
                recommendation = "remove_candidate"
                used = False
                category = "legacy_ui_suite"
            elif name in remove_candidates:
                recommendation = "remove_candidate"
                used = False
                category = "legacy_or_unused"
            elif name in keep:
                recommendation = "keep"
                used = True
                category = "active_runtime"
            else:
                recommendation = "review"
                used = False
                category = "needs_import_audit"
            packages.append({
                "name": name,
                "category": category,
                "used": used,
                "recommendation": recommendation,
            })
    except Exception as exc:
        logger.warning("Package registry discovery failed: %s", exc)
    return packages

# Test endpoint
@router.get("/health")
async def admin_health():
    """Admin health check - always accessible"""
    return {"status": "admin_ok", "message": "Admin routes loaded"}


@router.get("/registry")
async def get_admin_registry(request: Request):
    """
    Read-only operational catalog for frontend services, APIs, datasources,
    agents, workflows, and package rationalization.
    """
    llm = _llm_settings()
    neo4j = _neo4j_datasource()
    api_routes = _discover_api_routes(request)
    backend_endpoint = str(request.base_url).rstrip("/")

    return {
        "services": [
            {
                "id": "frontend-ui",
                "name": "DEPO Frontend Workspace",
                "type": "frontend",
                "status": "configured",
                "owner": "Digital Engineering",
                "endpoint": "http://localhost:3000",
                "health_endpoint": "",
            },
            {
                "id": "backend-api",
                "name": "DEPO FastAPI Service",
                "type": "api",
                "status": "online",
                "owner": "Digital Engineering",
                "endpoint": backend_endpoint,
                "health_endpoint": "/health",
            },
            {
                "id": "neo4j-graph",
                "name": "Neo4j Graph Datasource",
                "type": "datasource",
                "status": neo4j["status"],
                "owner": "Data Platform",
                "endpoint": neo4j.get("uri_masked", ""),
                "health_endpoint": "/health/neo4j",
            },
            {
                "id": "llm-agent-runtime",
                "name": "LLM / Agent Runtime",
                "type": "agent",
                "status": llm["status"],
                "owner": "Semantic AI",
                "endpoint": _mask_uri(llm.get("endpoint")),
                "health_endpoint": "/api/v1/import/ollama/health",
            },
        ],
        "api_routes": api_routes,
        "data_sources": [
            neo4j,
            {
                "id": "ollama",
                "name": "Ollama / LLM Endpoint",
                "type": "llm",
                "status": llm["status"],
                "uri_masked": _mask_uri(llm.get("endpoint")),
                "database": llm["model"],
                "mutable": False,
            },
        ],
        "agents": [
            {
                "id": "semantic-chat",
                "name": "Semantic Chat Agent",
                "provider": llm["provider"],
                "model": llm["model"],
                "status": llm["status"],
                "health_endpoint": "/chat/sample-queries",
            },
            {
                "id": "workflow-advisor",
                "name": "Workflow Advisor",
                "provider": llm["provider"],
                "model": llm["model"],
                "status": llm["status"],
                "health_endpoint": "/api/v1/import/ollama/health",
            },
        ],
        "workflows": _workflow_registry(),
        "packages": _package_registry(),
    }

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
