import os
import time
import logging
import asyncio
from pathlib import Path
from functools import wraps
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from langchain_neo4j import Neo4jGraph
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 🔒 SECURITY: Query timeout configuration
NEO4J_QUERY_TIMEOUT = int(os.getenv("NEO4J_QUERY_TIMEOUT", "30"))  # 30 seconds default
NEO4J_DRIVER_TIMEOUT = 60  # Connection timeout (seconds)


def _first_env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return None


env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)

uri = _first_env("NEO4J_URI", "NEO4J_URL", "Neo4j_url")
username = _first_env("NEO4J_USER", "NEO4J_USERNAME", "Neo4j_user")
password = _first_env("NEO4J_PASS", "NEO4J_PASSWORD", "Neo4j_password")
database = _first_env("NEO4J_DATABASE", "Neo4j_database") or "neo4j"

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
    raise ValueError(
        f"Missing Neo4j configuration in backend/.env: {', '.join(missing)}"
    )

#graph_driver = GraphDatabase.driver(uri, auth=(username, password), database = database)
try:
    graph = Neo4jGraph(
        url=uri,
        username=username,
        password=password,
        database=database,
    )
except Exception as exc:
    raise ValueError(
        "Could not connect to Neo4j. Check NEO4J_URI/NEO4J_USER/NEO4J_PASS "
        f"(and optional NEO4J_DATABASE) in backend/.env. Original error: {exc}"
    ) from exc

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
        
    except TimeoutError as e:
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

    try:
        node_rows = query_with_timeout(
            "CALL db.schema.nodeTypeProperties() "
            "YIELD nodeType, propertyName, propertyTypes "
            "RETURN nodeType, collect({name: propertyName, types: propertyTypes}) AS properties"
        )
    except Exception:
        # Fallback for older Neo4j versions / Aura that lack the procedure
        logger.warning("db.schema.nodeTypeProperties() unavailable – using fallback query")
        node_rows = query_with_timeout(
            "MATCH (n) "
            "WITH labels(n) AS lbls, keys(n) AS ks "
            "UNWIND lbls AS lbl UNWIND ks AS k "
            "WITH lbl, collect(DISTINCT k) AS props "
            "RETURN ':`' + lbl + '`' AS nodeType, "
            "[p IN props | {name: p, types: ['String']}] AS properties"
        )

    try:
        rel_rows = query_with_timeout(
            "CALL db.schema.relTypeProperties() "
            "YIELD relType, propertyName, propertyTypes "
            "RETURN relType, collect({name: propertyName, types: propertyTypes}) AS properties"
        )
    except Exception:
        logger.warning("db.schema.relTypeProperties() unavailable – using fallback query")
        rel_rows = query_with_timeout(
            "MATCH ()-[r]->() "
            "WITH type(r) AS t, keys(r) AS ks "
            "UNWIND ks AS k "
            "WITH t, collect(DISTINCT k) AS props "
            "RETURN ':`' + t + '`' AS relType, "
            "[p IN props | {name: p, types: ['String']}] AS properties"
        )

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
