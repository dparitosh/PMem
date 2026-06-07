"""
Context-Aware Graph Embedding Module
=====================================
Generates embeddings for Neo4j graph nodes by serializing each node's
properties together with its 1-hop neighbourhood (relationships + neighbour
identity).  The resulting "GraphChunk" nodes preserve structural context and
work well with hybrid vector + keyword retrieval in a RAG pipeline.

Usage:
    python -m Services.graph_embeddings          # run from backend/
    python Services/graph_embeddings.py          # or directly
"""

import os
import sys
import time
import random
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
import tiktoken

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.llm import embeddings, EMBEDDER_AVAILABLE

# ✅ Import centralized database configuration
try:
    from core.db_config import get_config, get_driver
    CENTRALIZED_CONFIG_AVAILABLE = True
except ImportError:
    CENTRALIZED_CONFIG_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)


def _env(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v:
            return v.strip()
    return None


# ✅ Use centralized configuration when available
if CENTRALIZED_CONFIG_AVAILABLE:
    try:
        _config = get_config()
        NEO4J_URI = _config.uri
        NEO4J_USER = _config.username
        NEO4J_PASS = _config.password
        NEO4J_DATABASE = _config.database
        logger.info("Using centralized Neo4j configuration from db_config.py")
    except Exception as e:
        logger.warning(f"Failed to use centralized config: {e}. Falling back to legacy config.")
        NEO4J_URI = _env("NEO4J_URI", "NEO4J_URL")
        NEO4J_USER = _env("NEO4J_USER", "NEO4J_USERNAME")
        NEO4J_PASS = _env("NEO4J_PASS", "NEO4J_PASSWORD")
        NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
else:
    NEO4J_URI = _env("NEO4J_URI", "NEO4J_URL")
    NEO4J_USER = _env("NEO4J_USER", "NEO4J_USERNAME")
    NEO4J_PASS = _env("NEO4J_PASS", "NEO4J_PASSWORD")
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Index / label names – must match what vector.py consumes
VECTOR_INDEX_NAME = os.getenv("NEO4J_GRAPH_VECTOR_INDEX", "graph_embedding")
KEYWORD_INDEX_NAME = os.getenv("NEO4J_GRAPH_KEYWORD_INDEX", "keyword_index")
DATASHEET_VECTOR_INDEX = os.getenv("NEO4J_DATASHEET_VECTOR_INDEX", "datasheet_index")
DATASHEET_KEYWORD_INDEX = os.getenv("NEO4J_DATASHEET_KEYWORD_INDEX", "datasheetkeyword")
CHUNK_LABEL = "GraphChunk"
DATASHEET_CHUNK_LABEL = "DatasheetChunk"
TEXT_PROPERTY = "content"
EMBEDDING_PROPERTY = "embedding"

# Tuning
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "20"))
MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "6"))
BASE_WAIT = float(os.getenv("EMBEDDING_BASE_WAIT", "2"))
MAX_TOKENS_PER_CHUNK = int(os.getenv("EMBEDDING_MAX_TOKENS", "512"))
MAX_RELS_PER_CHUNK = int(os.getenv("EMBEDDING_MAX_RELS", "40"))

_encoding = tiktoken.get_encoding("cl100k_base")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token_count(text: str) -> int:
    return len(_encoding.encode(text))


def _clean_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(i) for i in v)
    return str(v).strip()


def _props_sentence(props: Dict, exclude: set = None) -> str:
    """Turn a property dict into a readable sentence list."""
    exclude = exclude or set()
    parts = []
    for k, v in props.items():
        if k in exclude or k == EMBEDDING_PROPERTY:
            continue
        clean_key = k.replace("_", " ")
        clean_val = _clean_value(v)
        if clean_val:
            parts.append(f"{clean_key}: {clean_val}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Core: build context-aware text for one node
# ---------------------------------------------------------------------------

def build_node_chunk_text(
    labels: List[str],
    props: Dict,
    relationships: List[Dict],
    _node_element_id: str,
) -> str:
    """
    Construct a natural-language chunk that captures:
      1. The node's label(s) and properties.
      2. Its immediate relationships and connected-neighbour identities.

    Relationships are grouped by type and direction, then truncated if the
    token budget would be exceeded.
    """
    primary_label = labels[0] if labels else "Node"
    node_name = (
        props.get("name")
        or props.get("title")
        or props.get("code")
        or props.get("key")
        or props.get("abbreviation")
        or ""
    )

    # --- Section 1: Node identity -------------------------------------------
    header = f'[{primary_label}] "{node_name}"' if node_name else f"[{primary_label}]"
    prop_text = _props_sentence(props, exclude={"name", "title"})
    section_node = f"{header}. Properties: {prop_text}." if prop_text else f"{header}."

    # --- Section 2: Relationships -------------------------------------------
    # Group by (rel_type, direction) to keep text compact
    grouped: Dict[str, List[str]] = {}
    for rel in relationships[:MAX_RELS_PER_CHUNK]:
        direction = rel.get("dir", "related")
        rel_type = rel.get("rel_type", "RELATED_TO")
        nb_label = rel.get("neighbor_label", "Node")
        nb_name = rel.get("neighbor_name", "")
        rel_props = rel.get("rel_props") or {}

        if direction == "outgoing":
            arrow = f"--[:{rel_type}]-->"
        else:
            arrow = f"<--[:{rel_type}]--"

        nb_desc = f'{nb_label} "{nb_name}"' if nb_name else nb_label
        entry = f"{arrow} {nb_desc}"
        if rel_props:
            rp = _props_sentence(rel_props)
            if rp:
                entry += f" ({rp})"

        grouped.setdefault(rel_type, []).append(entry)

    rel_lines = []
    for rtype, entries in grouped.items():
        if len(entries) <= 3:
            rel_lines.extend(entries)
        else:
            # Summarise large groups to stay within token budget
            sample = entries[:2]
            rel_lines.extend(sample)
            rel_lines.append(
                f"...and {len(entries) - 2} more {rtype} relationships."
            )

    section_rels = " ".join(rel_lines) if rel_lines else ""

    # --- Combine & trim to token budget -------------------------------------
    full_text = section_node
    if section_rels:
        full_text += " Relationships: " + section_rels

    # Trim if over budget (drop relationship entries from the end)
    while _token_count(full_text) > MAX_TOKENS_PER_CHUNK and rel_lines:
        rel_lines.pop()
        section_rels = " ".join(rel_lines)
        full_text = section_node + (" Relationships: " + section_rels if section_rels else "")

    return full_text.strip()


# ---------------------------------------------------------------------------
# Fetch nodes + 1-hop neighbourhood from Neo4j
# ---------------------------------------------------------------------------

FETCH_QUERY = """
MATCH (n)
WHERE NOT n:GraphChunk AND NOT n:DatasheetChunk
OPTIONAL MATCH (n)-[r]-(m)
WHERE NOT m:GraphChunk AND NOT m:DatasheetChunk
WITH n,
     collect(DISTINCT {
         rel_type:  type(r),
         dir:       CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END,
         neighbor_label: CASE WHEN labels(m) IS NOT NULL AND size(labels(m)) > 0
                              THEN labels(m)[0] ELSE 'Node' END,
         neighbor_name:  coalesce(m.name, m.title, m.code, m.key,
                                  m.abbreviation, ''),
         rel_props: properties(r)
     }) AS rels
RETURN elementId(n) AS eid,
       labels(n)     AS labels,
       properties(n)  AS props,
       rels
"""


def fetch_graph_nodes(driver) -> List[Dict]:
    """Return list of dicts with keys: eid, labels, props, rels."""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(FETCH_QUERY)
        records = [dict(r) for r in result]
    logger.info("Fetched %d nodes from the graph", len(records))
    return records


# ---------------------------------------------------------------------------
# Batch-embed with retry
# ---------------------------------------------------------------------------

def _embed_batch(texts: List[str], attempt: int = 0) -> Optional[List[List[float]]]:
    if attempt >= MAX_RETRIES:
        logger.error("Max retries exceeded for embedding batch")
        return None
    try:
        return embeddings.embed_documents(texts)
    except Exception as exc:
        wait = BASE_WAIT * (2 ** attempt) + random.uniform(0, 1)
        logger.warning("Embed error (%s). Retry %d in %.1fs", exc, attempt + 1, wait)
        time.sleep(wait)
        return _embed_batch(texts, attempt + 1)


# ---------------------------------------------------------------------------
# Write GraphChunk nodes back to Neo4j
# ---------------------------------------------------------------------------

UPSERT_CHUNK = f"""
UNWIND $rows AS row
MERGE (c:{CHUNK_LABEL} {{node_id: row.node_id}})
SET c.{TEXT_PROPERTY}       = row.content,
    c.{EMBEDDING_PROPERTY}  = row.embedding,
    c.labels_source         = row.labels_source,
    c.updated_at            = datetime()
WITH c, row
MATCH (src) WHERE elementId(src) = row.node_id
MERGE (c)-[:EMBEDDED_FROM]->(src)
"""


def upsert_chunks(driver, rows: List[Dict]):
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run(UPSERT_CHUNK, rows=rows)


# ---------------------------------------------------------------------------
# Ensure vector + keyword indexes exist
# ---------------------------------------------------------------------------

def ensure_indexes(driver):
    with driver.session(database=NEO4J_DATABASE) as session:
        # --- GraphChunk vector index ---
        try:
            session.run(f"""
                CREATE VECTOR INDEX `{VECTOR_INDEX_NAME}` IF NOT EXISTS
                FOR (c:{CHUNK_LABEL})
                ON (c.{EMBEDDING_PROPERTY})
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: 768,
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
            logger.info("Vector index '%s' ensured", VECTOR_INDEX_NAME)
        except Exception as exc:
            logger.warning("Vector index creation note: %s", exc)

        # --- GraphChunk fulltext keyword index ---
        try:
            session.run(f"""
                CREATE FULLTEXT INDEX `{KEYWORD_INDEX_NAME}` IF NOT EXISTS
                FOR (c:{CHUNK_LABEL})
                ON EACH [c.{TEXT_PROPERTY}]
            """)
            logger.info("Keyword index '%s' ensured", KEYWORD_INDEX_NAME)
        except Exception as exc:
            logger.warning("Keyword index creation note: %s", exc)

        # --- DatasheetChunk vector index ---
        try:
            session.run(f"""
                CREATE VECTOR INDEX `{DATASHEET_VECTOR_INDEX}` IF NOT EXISTS
                FOR (c:{DATASHEET_CHUNK_LABEL})
                ON (c.{EMBEDDING_PROPERTY})
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: 768,
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)
            logger.info("Vector index '%s' ensured", DATASHEET_VECTOR_INDEX)
        except Exception as exc:
            logger.warning("Datasheet vector index creation note: %s", exc)

        # --- DatasheetChunk fulltext keyword index ---
        try:
            session.run(f"""
                CREATE FULLTEXT INDEX `{DATASHEET_KEYWORD_INDEX}` IF NOT EXISTS
                FOR (c:{DATASHEET_CHUNK_LABEL})
                ON EACH [c.{TEXT_PROPERTY}]
            """)
            logger.info("Keyword index '%s' ensured", DATASHEET_KEYWORD_INDEX)
        except Exception as exc:
            logger.warning("Datasheet keyword index creation note: %s", exc)


def ensure_indexes_standalone():
    """Create all required vector + keyword indexes without running the full
    embedding pipeline.  Safe to call at application startup so that
    ``vector.py`` can connect to the indexes even before any chunks exist.
    
    ✅ Uses centralized driver connection when available.
    """
    for key, val in {"NEO4J_URI": NEO4J_URI, "NEO4J_USER": NEO4J_USER, "NEO4J_PASS": NEO4J_PASS}.items():
        if not val:
            logger.warning("Cannot ensure indexes – missing %s in .env", key)
            return
    
    try:
        if CENTRALIZED_CONFIG_AVAILABLE:
            driver = get_driver()
            logger.info("Using centralized driver for index creation")
            ensure_indexes(driver)
        else:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            logger.info("Using standalone driver for index creation")
            try:
                ensure_indexes(driver)
            finally:
                try:
                    driver.close()
                except Exception:
                    logger.exception("Error closing standalone driver after index creation")
    except Exception as exc:
        logger.error(f"Failed to ensure indexes: {exc}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_graph_embeddings(
    *,
    force_rebuild: bool = False,
    batch_size: int = BATCH_SIZE,
):
    """
    End-to-end pipeline:
      1. Fetch all non-chunk nodes with 1-hop context.
      2. Serialise each into a context-aware text chunk.
      3. Embed in batches.
      4. Upsert GraphChunk nodes linked back to their source node.
      5. Ensure vector + keyword indexes exist.

    If *force_rebuild* is False (default), only nodes without an existing
    GraphChunk are processed.
    
    ✅ Uses centralized driver connection when available.
    """
    if not EMBEDDER_AVAILABLE:
        logger.error(
            "EMBEDDER MODEL NOT AVAILABLE – cannot create embeddings. "
            "Ensure Ollama / Azure is reachable."
        )
        return

    for key, val in {"NEO4J_URI": NEO4J_URI, "NEO4J_USER": NEO4J_USER, "NEO4J_PASS": NEO4J_PASS}.items():
        if not val:
            raise ValueError(f"Missing {key} in .env")

    try:
        if CENTRALIZED_CONFIG_AVAILABLE:
            driver = get_driver()
            logger.info("Using centralized driver for embedding pipeline")
        else:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            logger.info("Using standalone driver for embedding pipeline")
    except Exception as exc:
        logger.error(f"Failed to get driver: {exc}")
        raise

    try:
        # 1. Fetch
        records = fetch_graph_nodes(driver)
        if not records:
            logger.info("No nodes found in graph")
            return

        # Skip nodes that already have a GraphChunk (unless force_rebuild)
        if not force_rebuild:
            existing = set()
            with driver.session(database=NEO4J_DATABASE) as session:
                result = session.run(
                    f"MATCH (c:{CHUNK_LABEL}) RETURN c.node_id AS nid"
                )
                existing = {r["nid"] for r in result}
            before = len(records)
            records = [r for r in records if r["eid"] not in existing]
            logger.info(
                "Skipping %d nodes with existing chunks, %d to process",
                before - len(records),
                len(records),
            )
            if not records:
                logger.info("All nodes already have embeddings")
                ensure_indexes(driver)
                return

        # 2. Build text chunks
        documents: List[Dict] = []
        for rec in records:
            text = build_node_chunk_text(
                labels=rec["labels"],
                props=rec["props"],
                relationships=rec["rels"],
                node_element_id=rec["eid"],
            )
            if not text.strip():
                continue
            documents.append({
                "node_id": rec["eid"],
                "labels_source": rec["labels"],
                "content": text,
            })

        logger.info("Built %d text chunks (avg %.0f tokens)",
                     len(documents),
                     sum(_token_count(d["content"]) for d in documents) / max(len(documents), 1))

        # 3 + 4. Embed in batches and upsert
        total_batches = (len(documents) + batch_size - 1) // batch_size
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            texts = [d["content"] for d in batch]
            batch_num = i // batch_size + 1

            logger.info("Embedding batch %d/%d (%d chunks)", batch_num, total_batches, len(batch))
            vectors = _embed_batch(texts)
            if not vectors:
                logger.error("Skipping batch %d – embedding failed", batch_num)
                continue

            for doc, vec in zip(batch, vectors):
                doc["embedding"] = vec

            upsert_chunks(driver, batch)
            logger.info("Batch %d upserted", batch_num)

            if i + batch_size < len(documents):
                time.sleep(0.5)

        # 5. Ensure indexes
        ensure_indexes(driver)
        logger.info("Graph embedding pipeline complete – %d chunks created", len(documents))

    finally:
        # Close driver only for standalone (non-centralized) mode to avoid
        # closing the shared application driver managed by Neo4jDriverPool.
        try:
            if not CENTRALIZED_CONFIG_AVAILABLE and driver is not None:
                driver.close()
        except Exception:
            logger.exception("Error closing driver in run_graph_embeddings finally block")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create context-aware graph embeddings")
    parser.add_argument(
        "--force", action="store_true",
        help="Rebuild all chunks even if they already exist",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Embedding batch size (default: {BATCH_SIZE})",
    )
    args = parser.parse_args()
    run_graph_embeddings(force_rebuild=args.force, batch_size=args.batch_size)
