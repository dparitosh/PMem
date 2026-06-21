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


class DeleteDataRequest(BaseModel):
    label: str | None = None
    prefix: str | None = None
    property: str | None = None
    value: str | int | float | bool | None = None
    batch_size: int = 10000
    dry_run: bool = False
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


def _env_candidates() -> list[Path]:
    root = _project_root()
    return [
        root / "backend" / ".env",
        root / ".env",
        root / "requirements" / ".env",
    ]


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as exc:
        logger.warning("Could not read env file %s: %s", path, exc)
    return values


def _env_lookup(*keys: str) -> tuple[str, str]:
    for env_path in _env_candidates():
        env_values = _read_env_file(env_path)
        for key in keys:
            value = env_values.get(key)
            if value:
                return value.strip(), str(env_path.relative_to(_project_root()))
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip(), "process"
    return "", "default"


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
        if hasattr(get_config, "cache_clear"):
            get_config.cache_clear()
        config = get_config()
        configured_database, configured_database_source = _env_lookup("NEO4J_DATABASE", "Neo4j_database")
        configured_database = configured_database or "neo4j"
        database_status = "active"
        database_message = ""
        if configured_database and configured_database != config.database:
            database_status = "mismatch"
            database_message = (
                f"Configured database is '{configured_database}' from {configured_database_source}, "
                f"but active backend config is '{config.database}'. Restart backend or clear config cache."
            )
        return {
            "id": "neo4j",
            "name": "Neo4j Knowledge Graph",
            "type": "graph_database",
            "status": "configured",
            "uri_masked": _mask_uri(config.uri),
            "database": config.database,
            "active_database": config.database,
            "configured_database": configured_database,
            "configured_database_source": configured_database_source,
            "database_status": database_status,
            "message": database_message,
            "deployment_type": config.deployment_type.value,
            "encrypted": config.encrypted,
            "query_timeout": config.query_timeout,
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
            "active_database": "",
            "configured_database": "",
            "configured_database_source": "",
            "database_status": "degraded",
            "mutable": False,
            "message": str(exc),
        }


def _configuration_registry(neo4j: dict, llm: dict) -> list[dict]:
    uri, uri_source = _env_lookup("NEO4J_URI", "NEO4J_URL", "Neo4j_url")
    user, user_source = _env_lookup("NEO4J_USER", "NEO4J_USERNAME", "Neo4j_user")
    credential, credential_source = _env_lookup("NEO4J_PASS", "NEO4J_PASSWORD", "Neo4j_password")
    encrypted, encrypted_source = _env_lookup("NEO4J_ENCRYPTED")
    timeout, timeout_source = _env_lookup("NEO4J_QUERY_TIMEOUT")
    ollama_base, ollama_source = _env_lookup("OLLAMA_BASE_URL")
    llm_model, model_source = _env_lookup("LLM_MODEL_NAME")
    use_llm, use_llm_source = _env_lookup("USE_LLM")

    rows = [
        {
            "component": "Neo4j",
            "key": "NEO4J_URI",
            "configured_value": _mask_uri(uri),
            "active_value": neo4j.get("uri_masked", ""),
            "source": uri_source,
            "status": "configured" if uri else "missing",
            "mutable": False,
        },
        {
            "component": "Neo4j",
            "key": "NEO4J_USER",
            "configured_value": user,
            "active_value": user,
            "source": user_source,
            "status": "configured" if user else "missing",
            "mutable": False,
        },
        {
            "component": "Neo4j",
            "key": "NEO4J_CREDENTIAL",
            "configured_value": "configured" if credential else "missing",
            "active_value": "redacted" if credential else "missing",
            "source": credential_source,
            "status": "configured" if credential else "missing",
            "mutable": False,
        },
        {
            "component": "Neo4j",
            "key": "NEO4J_DATABASE",
            "configured_value": neo4j.get("configured_database", ""),
            "active_value": neo4j.get("active_database", ""),
            "source": neo4j.get("configured_database_source", ""),
            "status": neo4j.get("database_status", "unknown"),
            "mutable": False,
        },
        {
            "component": "Neo4j",
            "key": "NEO4J_ENCRYPTED",
            "configured_value": encrypted or str(neo4j.get("encrypted", "")),
            "active_value": str(neo4j.get("encrypted", "")),
            "source": encrypted_source,
            "status": "configured" if encrypted else "default",
            "mutable": False,
        },
        {
            "component": "Neo4j",
            "key": "NEO4J_QUERY_TIMEOUT",
            "configured_value": timeout or str(neo4j.get("query_timeout", "")),
            "active_value": str(neo4j.get("query_timeout", "")),
            "source": timeout_source,
            "status": "configured" if timeout else "default",
            "mutable": False,
        },
        {
            "component": "LLM",
            "key": "USE_LLM",
            "configured_value": use_llm or llm.get("provider", ""),
            "active_value": llm.get("provider", ""),
            "source": use_llm_source,
            "status": "configured" if use_llm else "default",
            "mutable": False,
        },
        {
            "component": "LLM",
            "key": "OLLAMA_BASE_URL",
            "configured_value": _mask_uri(ollama_base or llm.get("endpoint", "")),
            "active_value": _mask_uri(llm.get("endpoint", "")),
            "source": ollama_source,
            "status": "configured" if ollama_base else "default",
            "mutable": False,
        },
        {
            "component": "LLM",
            "key": "LLM_MODEL_NAME",
            "configured_value": llm_model or llm.get("model", ""),
            "active_value": llm.get("model", ""),
            "source": model_source,
            "status": "configured" if llm_model else "default",
            "mutable": False,
        },
    ]
    return rows


def _llm_settings() -> dict:
    provider, provider_source = _env_lookup("USE_LLM")
    model, model_source = _env_lookup("LLM_MODEL_NAME", "AZURE_OPENAI_DEPLOYMENT")
    endpoint, endpoint_source = _env_lookup("OLLAMA_BASE_URL", "AZURE_OPENAI_ENDPOINT")
    provider = (provider or "ollama").lower()
    model = model or "llama3:latest"
    endpoint = endpoint or "http://localhost:11434"
    status = "configured" if endpoint and model else "degraded"
    return {
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "status": status,
        "provider_source": provider_source,
        "model_source": model_source,
        "endpoint_source": endpoint_source,
    }


def _workflow_registry() -> list[dict]:
    try:
        from backend.Services.workflow_registry import get_workflow_registry
    except ImportError:
        from Services.workflow_registry import get_workflow_registry

    return get_workflow_registry()


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


def _route_group_services(api_routes: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for route in api_routes:
        group = route.get("service_group") or "Core"
        item = groups.setdefault(group, {
            "id": f"api-{group.lower().replace(' ', '-').replace('_', '-')}",
            "name": f"{group} API",
            "type": "api_route_group",
            "status": "online",
            "owner": "Digital Engineering",
            "endpoint": "",
            "health_endpoint": "",
            "route_count": 0,
            "frontend_mapped_count": 0,
        })
        item["route_count"] += 1
        if route.get("frontend_mapped"):
            item["frontend_mapped_count"] += 1
    return sorted(groups.values(), key=lambda row: row["name"])


def _route_available(api_routes: list[dict], path: str) -> str:
    return path if any(route.get("path") == path for route in api_routes) else ""


def _empty_schema_stats() -> dict:
    return {
        "total_nodes": 0,
        "total_relationships": 0,
        "node_types": [],
        "relationship_types": [],
        "indexes_count": 0,
        "lookup_indexes_count": 0,
        "constraints_count": 0,
    }


def _is_missing_database_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "databasenotfound" in message or "database does not exist" in message

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
    route_group_services = _route_group_services(api_routes)
    backend_health = _route_available(api_routes, "/health")
    llm_health = _route_available(api_routes, "/api/v1/import/ollama/health")
    chat_health = _route_available(api_routes, "/chat/health")

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
                "config_source": "frontend/.env",
                "route_count": 0,
                "frontend_mapped_count": 0,
            },
            {
                "id": "backend-api",
                "name": "DEPO FastAPI Service",
                "type": "api",
                "status": "online",
                "owner": "Digital Engineering",
                "endpoint": backend_endpoint,
                "health_endpoint": backend_health,
                "config_source": "backend/.env",
                "route_count": len(api_routes),
                "frontend_mapped_count": sum(1 for route in api_routes if route.get("frontend_mapped")),
            },
            {
                "id": "llm-agent-runtime",
                "name": "LLM / Agent Runtime",
                "type": "agent",
                "status": llm["status"],
                "owner": "Semantic AI",
                "endpoint": _mask_uri(llm.get("endpoint")),
                "health_endpoint": llm_health,
                "config_source": llm.get("endpoint_source", ""),
                "route_count": 0,
                "frontend_mapped_count": 0,
                "model": llm.get("model", ""),
            },
        ] + route_group_services,
        "api_routes": api_routes,
        "data_sources": [
            neo4j,
        ],
        "configuration": _configuration_registry(neo4j, llm),
        "agents": [
            {
                "id": "semantic-chat",
                "name": "Semantic Chat Agent",
                "provider": llm["provider"],
                "model": llm["model"],
                "status": llm["status"],
                "health_endpoint": chat_health,
                "config_source": llm.get("model_source", ""),
            },
            {
                "id": "workflow-advisor",
                "name": "Workflow Advisor",
                "provider": llm["provider"],
                "model": llm["model"],
                "status": llm["status"],
                "health_endpoint": llm_health,
                "config_source": llm.get("model_source", ""),
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


@router.post("/delete-data")
async def delete_data_by_label(body: DeleteDataRequest):
    """
    Delete large Neo4j node sets in batches.

    Example Cypher shape:
    MATCH (n:LabelName)
    WHERE n.property = $value
    CALL {
        WITH n
        DETACH DELETE n
    } IN TRANSACTIONS OF 10000 ROWS
    """
    if not SCHEMA_CLEANER_AVAILABLE or not Neo4jSchemaCleaner:
        raise HTTPException(status_code=503, detail="Schema cleaner not available")

    if body.confirm != "DELETE_NEO4J_DATA":
        raise HTTPException(
            status_code=400,
            detail="Confirmation token required: confirm='DELETE_NEO4J_DATA'",
        )
    if not body.label and not body.prefix:
        raise HTTPException(status_code=400, detail="Provide either label or prefix.")
    if body.label and body.prefix:
        raise HTTPException(status_code=400, detail="Use either label or prefix, not both.")
    if body.prefix and (body.property or body.value is not None):
        raise HTTPException(status_code=400, detail="Property filters are only supported with label deletes.")
    if body.property and body.value is None:
        raise HTTPException(status_code=400, detail="Property value is required when property is provided.")
    if not body.property and body.value is not None:
        raise HTTPException(status_code=400, detail="Property name is required when value is provided.")

    cleaner = None
    try:
        cleaner = Neo4jSchemaCleaner()
        if body.dry_run and body.prefix:
            result = cleaner.count_nodes_by_prefix(prefix=body.prefix)
        elif body.dry_run:
            result = cleaner.count_nodes_by_label_property(
                label=body.label or "",
                property_name=body.property,
                property_value=body.value,
            )
        elif body.prefix:
            result = cleaner.delete_nodes_by_prefix(
                prefix=body.prefix,
                batch_size=body.batch_size,
            )
        else:
            result = cleaner.delete_nodes_by_label_property(
                label=body.label or "",
                property_name=body.property,
                property_value=body.value,
                batch_size=body.batch_size,
            )
        if result.get("status") != "SUCCESS":
            raise HTTPException(status_code=400, detail=result.get("message", "Delete failed"))
        return {"success": True, "dry_run": body.dry_run, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete Neo4j data")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cleaner is not None:
            cleaner.close()


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
        if _is_missing_database_error(e):
            neo4j = _neo4j_datasource()
            database = neo4j.get("configured_database") or neo4j.get("active_database") or "configured database"
            return {
                "status": "degraded",
                "stats": _empty_schema_stats(),
                "database": database,
                "database_status": "missing",
                "message": (
                    f"Neo4j is configured from {neo4j.get('configured_database_source') or 'backend/.env'} "
                    f"to use database '{database}', but that database does not exist in the running Neo4j instance."
                ),
            }
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


@router.post("/clear-cache")
async def clear_cache():
    """
    Clear non-destructive application caches used by admin and graph views.
    This does not delete Neo4j data.
    """
    cleared = {
        "graph_cache": False,
        "ontology_list_cache": False,
        "config_cache": False,
    }
    try:
        try:
            from backend.main import invalidate_graphvis_cache
        except ImportError:
            from main import invalidate_graphvis_cache
        invalidate_graphvis_cache()
        cleared["graph_cache"] = True
    except Exception as exc:
        logger.warning("Could not clear graph cache: %s", exc)

    try:
        from backend.Services.ontology_upload_manager import OntologyUploadManager
        OntologyUploadManager._invalidate_list_cache()
        cleared["ontology_list_cache"] = True
    except Exception as exc:
        logger.warning("Could not clear ontology list cache: %s", exc)

    try:
        try:
            from backend.core.db_config import get_config
        except ImportError:
            from core.db_config import get_config
        if hasattr(get_config, "cache_clear"):
            get_config.cache_clear()
            cleared["config_cache"] = True
    except Exception as exc:
        logger.warning("Could not clear config cache: %s", exc)

    return {
        "status": "success",
        "message": "Application caches cleared.",
        "cleared": cleared,
    }
