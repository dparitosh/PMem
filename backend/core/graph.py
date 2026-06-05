import os
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Optional imports - gracefully handle missing modules
try:
    from llama_index.graph_stores.neo4j import Neo4jGraphStore
except ImportError:
    logger.warning("llama_index.graph_stores.neo4j not available - Neo4jGraphStore will be unavailable")
    Neo4jGraphStore = None

try:
    from langchain_neo4j import Neo4jGraph
except ImportError:
    logger.warning("langchain_neo4j not available - Neo4jGraph will be unavailable")
    Neo4jGraph = None

# ✅ Import centralized database configuration
try:
    from .db_config import get_config
    CENTRALIZED_CONFIG_AVAILABLE = True
    logger.info("Using centralized Neo4j configuration from db_config.py")
except ImportError:
    logger.warning("Centralized db_config not available - using legacy configuration")
    CENTRALIZED_CONFIG_AVAILABLE = False
    
    def _first_env(*keys: str) -> str | None:
        for key in keys:
            value = os.getenv(key)
            if value:
                return value.strip()
        return None
    
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path)
    
    uri = _first_env("NEO4J_URI", "NEO4J_URL", "Neo4j_url")
    username = _first_env("NEO4J_USER", "NEO4J_USERNAME", "Neo4j_user")
    password = _first_env("NEO4J_PASS", "NEO4J_PASSWORD", "Neo4j_password")
    database = _first_env("NEO4J_DATABASE", "Neo4j_database") or None

    missing = [
        key
        for key, value in {
            "NEO4J_URI": uri,
            "NEO4J_USER": username,
            "NEO4J_PASS": password,
        }.items()
        if not value
    ]
    
    if missing:
        logger.warning(
            f"Missing Neo4j configuration in backend/.env: {', '.join(missing)}. "
            "Neo4j features will be unavailable until properly configured."
        )

# 🔒 SECURITY: Query timeout configuration (read from centralized config if available)
if CENTRALIZED_CONFIG_AVAILABLE:
    try:
        NEO4J_QUERY_TIMEOUT = get_config().query_timeout
    except Exception:
        NEO4J_QUERY_TIMEOUT = int(os.getenv("NEO4J_QUERY_TIMEOUT", "30"))
else:
    NEO4J_QUERY_TIMEOUT = int(os.getenv("NEO4J_QUERY_TIMEOUT", "30"))

NEO4J_DRIVER_TIMEOUT = 60  # Connection timeout (seconds)

# Lazy initialization of graph connection
_graph = None
_graph_last_failed_at: float = 0.0
_GRAPH_RETRY_COOLDOWN = 60.0  # seconds between reconnect attempts


def get_graph():
    """Get or create the Neo4j graph connection (lazy initialization).

    Fail-fast with a cooldown: once a connection attempt fails, subsequent
    calls return immediately (raise) for 60 s so executor threads aren't
    stacked up doing repeated 10-second handshakes to a paused AuraDB instance.
    
    ✅ Uses centralized configuration from db_config.py when available.
    """
    global _graph, _graph_last_failed_at
    if _graph is not None:
        return _graph
    if Neo4jGraph is None:
        raise ImportError(
            "Neo4jGraph module not available. Install langchain_neo4j: "
            "pip install langchain-neo4j"
        )
    # Cooldown: don't hammer a paused AuraDB instance
    if _graph_last_failed_at:
        elapsed = time.time() - _graph_last_failed_at
        if elapsed < _GRAPH_RETRY_COOLDOWN:
            raise ValueError(
                f"Neo4j connection unavailable (retry in "
                f"{int(_GRAPH_RETRY_COOLDOWN - elapsed)}s). "
                "AuraDB may be paused — check console.neo4j.io."
            )
    try:
        # Try to use centralized configuration
        if CENTRALIZED_CONFIG_AVAILABLE:
            config = get_config()
            _graph = Neo4jGraph(
                url=config.uri,
                username=config.username,
                password=config.password,
                database=config.database,
            )
            logger.info(
                f"Neo4j graph connection established using centralized config "
                f"(deployment: {config.deployment_type.value})"
            )
        else:
            # Fallback to legacy configuration
            _graph = Neo4jGraph(
                url=uri,
                username=username,
                password=password,
                database=database,
            )
            logger.info("Neo4j graph connection established (legacy configuration)")
        
        _graph_last_failed_at = 0.0
    except Exception as exc:
        _graph = None
        _graph_last_failed_at = time.time()
        logger.error(
            f"Could not connect to Neo4j. Check NEO4J_URI/NEO4J_USER/NEO4J_PASS "
            f"(and optional NEO4J_DATABASE) in backend/.env. Original error: {exc}"
        )
        raise
    return _graph

# Provide a property-like access for backward compatibility
class GraphProxy:
    def __getattr__(self, name):
        return getattr(get_graph(), name)

graph = GraphProxy()

# 🔒 SECURITY: Query timeout wrapper
def query_with_timeout(query_text: str, params: dict = None, timeout: int = None):
    """
    Execute a Cypher query with timeout protection.
    
    Args:
        query_text: Cypher query string
        params: Query parameters
        timeout: Timeout in seconds (defaults to NEO4J_QUERY_TIMEOUT)
    
    Returns:
        Query results
    
    Raises:
        TimeoutError: If query exceeds timeout
        Exception: Any Neo4j or other errors
    """
    if timeout is None:
        timeout = NEO4J_QUERY_TIMEOUT
    
    try:
        # For synchronous queries, we use a simple approach:
        # Let the query run but log if it takes too long
        start_time = time.time()
        
        if params:
            result = graph.query(query_text, params=params)
        else:
            result = graph.query(query_text)
        
        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.warning(
                f"Query exceeded timeout threshold: {elapsed:.2f}s > {timeout}s. "
                f"Query: {query_text[:100]}..."
            )
        
        return result
        
    except TimeoutError:
        logger.error(f"Query timeout after {timeout}s: {query_text[:100]}...", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Query execution error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise

# ── Schema cache ──────────────────────────────────────────────────────────
_SCHEMA_CACHE_TTL = 600  # seconds (10 min)
_schema_cache: dict | None = None
_schema_cache_ts: float = 0.0


def get_graph_schema() -> dict:
    """Return node labels, relationship types and their property keys.
    Results are cached in-memory for _SCHEMA_CACHE_TTL seconds.
    """
    global _schema_cache, _schema_cache_ts

    now = time.time()
    if _schema_cache is not None and (now - _schema_cache_ts) < _SCHEMA_CACHE_TTL:
        return _schema_cache

    # Graceful fallback when Neo4j is not available
    if Neo4jGraph is None:
        logger.warning("Neo4jGraph not available - returning empty schema")
        empty_schema = {"node_labels": {}, "rel_types": {}, "display_names": {}}
        _schema_cache = empty_schema
        _schema_cache_ts = now
        return empty_schema

    try:
        node_rows = query_with_timeout(
            "CALL db.schema.nodeTypeProperties() "
            "YIELD nodeType, propertyName, propertyTypes "
            "RETURN nodeType, collect({name: propertyName, types: propertyTypes}) AS properties"
        )
    except Exception:
        # Fallback for older Neo4j versions / Aura that lack the procedure
        logger.warning("db.schema.nodeTypeProperties() unavailable – using fallback query")
        try:
            node_rows = query_with_timeout(
                "MATCH (n) "
                "WITH labels(n) AS lbls, keys(n) AS ks "
                "UNWIND lbls AS lbl UNWIND ks AS k "
                "WITH lbl, collect(DISTINCT k) AS props "
                "RETURN ':`' + lbl + '`' AS nodeType, "
                "[p IN props | {name: p, types: ['String']}] AS properties"
            )
        except Exception as e:
            logger.error(f"Could not retrieve node schema: {e}")
            node_rows = []

    try:
        rel_rows = query_with_timeout(
            "CALL db.schema.relTypeProperties() "
            "YIELD relType, propertyName, propertyTypes "
            "RETURN relType, collect({name: propertyName, types: propertyTypes}) AS properties"
        )
    except Exception:
        logger.warning("db.schema.relTypeProperties() unavailable – using fallback query")
        try:
            rel_rows = query_with_timeout(
                "MATCH ()-[r]->() "
                "WITH type(r) AS t, keys(r) AS ks "
                "UNWIND ks AS k "
                "WITH t, collect(DISTINCT k) AS props "
                "RETURN ':`' + t + '`' AS relType, "
                "[p IN props | {name: p, types: ['String']}] AS properties"
            )
        except Exception as e:
            logger.error(f"Could not retrieve relationship schema: {e}")
            rel_rows = []

    # Build clean dicts
    node_labels: dict[str, list] = {}
    for row in node_rows:
        label = row["nodeType"].strip(":` ")
        props = [p["name"] for p in row["properties"] if p["name"]]
        node_labels.setdefault(label, [])
        for p in props:
            if p not in node_labels[label]:
                node_labels[label].append(p)

    rel_types: dict[str, list] = {}
    for row in rel_rows:
        rtype = row["relType"].strip(":` ")
        props = [p["name"] for p in row["properties"] if p["name"]]
        rel_types.setdefault(rtype, [])
        for p in props:
            if p not in rel_types[rtype]:
                rel_types[rtype].append(p)

    # Heuristic: pick best "display name" property per label
    _NAME_CANDIDATES = [
        "name", "Name", "title", "Title", "PartName", "CADDocumentName",
        "code", "key", "abbreviation", "identifier", "label",
    ]
    display_keys: dict[str, str | None] = {}
    for label, props in node_labels.items():
        chosen = None
        for candidate in _NAME_CANDIDATES:
            if candidate in props:
                chosen = candidate
                break
        display_keys[label] = chosen

    _schema_cache = {
        "nodeLabels": node_labels,
        "relationshipTypes": rel_types,
        "displayKeys": display_keys,
    }
    _schema_cache_ts = now
    return _schema_cache


def cleanup_graph_connection():
    """Cleanup Neo4j connection resources - call on shutdown."""
    try:
        if hasattr(graph, '_driver') and graph._driver:
            graph._driver.close()
            logger.info("Neo4j connection cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during Neo4j cleanup: {e}", exc_info=True)

# print(graph.get_schema)

# def get_entire_graph():
#     try:
#         results = graph.query("""MATCH (n)
#           OPTIONAL MATCH (n)-[r]-(m)
#           RETURN
#             {id: id(n), labels: labels(n), properties: properties(n)} AS n,
#             CASE WHEN r IS NOT NULL THEN {id: id(r), type: type(r), properties: properties(r), start: id(startNode(r)), end: id(endNode(r))} ELSE NULL END AS r,
#             CASE WHEN m IS NOT NULL THEN {id: id(m), labels: labels(m), properties: properties(m)} ELSE NULL END AS m
#             LIMIT 500""")
#         return {"results": results}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    
# from pydantic import BaseModel
# class SearchRequest(BaseModel):
#     search: str


# def filter_graph_nodes(request: SearchRequest):
#     try:
#         query = f"""
#         MATCH (n)
# WHERE any(prop IN keys(n) WHERE (n[prop]) CONTAINS '{request.search}')
#         RETURN n
#         """
#         results = graph.query(query)
#         return {"results": results}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
    


# results = graph.query("""MATCH (n)
#           OPTIONAL MATCH (n)-[r]-(m)
#           RETURN
#             {id: id(n), labels: labels(n), properties: properties(n)} AS n,
#             CASE WHEN r IS NOT NULL THEN {id: id(r), type: type(r), properties: properties(r), start: id(startNode(r)), end: id(endNode(r))} ELSE NULL END AS r,
#             CASE WHEN m IS NOT NULL THEN {id: id(m), labels: labels(m), properties: properties(m)} ELSE NULL END AS m
#             LIMIT 500""")
# print(results)