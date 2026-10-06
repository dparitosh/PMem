"""
Context-Aware Graph Embedding Module
=====================================
Generates embeddings for Neo4j graph nodes by serializing each node's
properties together with its 1-hop neighbourhood (relationships + neighbour
identity).  The resulting "GraphChunk" nodes preserve structural context and
work well with hybrid vector + keyword retrieval in a RAG pipeline.

Usage:
    python -m backend.Services.graph_embeddings  # run from repository root
    python Services/graph_embeddings.py          # run from backend/
"""

import os
import sys
import time
import random
import logging
import math
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
import tiktoken

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from backend.core.llm import embeddings, EMBEDDER_AVAILABLE

# ✅ Import centralized database configuration
try:
    from backend.core.db_config import get_config, get_driver
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
# Managed deployments use only the injected root configuration.
if os.getenv('DEPO_ENV_INJECTED', '').lower() != 'true' and not any(
    os.getenv(key, '').lower() in {'prod', 'production'}
    for key in ('DEPO_ENV', 'ENVIRONMENT', 'APP_ENV', 'DEPLOYMENT_ENV')
):
    load_dotenv(env_path, override=False)


def _env(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v:
            return v.strip()
    return None


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


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
EMBEDDING_VECTOR_DIMENSIONS = _positive_int_env("EMBEDDING_VECTOR_DIMENSIONS", 768)

# Tuning
BATCH_SIZE = _positive_int_env("EMBEDDING_BATCH_SIZE", 20)
MAX_RETRIES = _positive_int_env("EMBEDDING_MAX_RETRIES", 6)
BASE_WAIT = float(os.getenv("EMBEDDING_BASE_WAIT", "2"))
MAX_TOKENS_PER_CHUNK = _positive_int_env("EMBEDDING_MAX_TOKENS", 512)
MAX_RELS_PER_CHUNK = _positive_int_env("EMBEDDING_MAX_RELS", 40)

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
    node_element_id: str,
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

    if _token_count(full_text) > MAX_TOKENS_PER_CHUNK:
        full_text = _encoding.decode(_encoding.encode(full_text)[:MAX_TOKENS_PER_CHUNK])

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
     collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE {
         rel_type:  type(r),
         dir:       CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END,
         neighbor_label: CASE WHEN labels(m) IS NOT NULL AND size(labels(m)) > 0
                              THEN labels(m)[0] ELSE 'Node' END,
         neighbor_name:  coalesce(m.name, m.title, m.code, m.key,
                                  m.abbreviation, ''),
         rel_props: properties(r)
     } END) AS rels
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


def _validate_vectors(vectors, count):
    """Reject incomplete or invalid provider output before any batch writes."""
    if not isinstance(vectors, (list, tuple)) or len(vectors) != count:
        raise RuntimeError('Embedding provider returned an incomplete batch')
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) != EMBEDDING_VECTOR_DIMENSIONS:
            raise RuntimeError('Embedding dimensions do not match EMBEDDING_VECTOR_DIMENSIONS')
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in vector):
            raise RuntimeError('Embedding provider returned invalid numeric values')
        if not any(value != 0 for value in vector):
            raise RuntimeError('Embedding provider returned a zero vector unsuitable for cosine search')


def _standalone_auth():
    if not NEO4J_URI:
        raise ValueError('Missing NEO4J_URI in deployment configuration')
    if os.getenv('NEO4J_AUTH_MODE', 'token').strip().lower() == 'none':
        return None
    if not NEO4J_USER or not NEO4J_PASS:
        raise ValueError('Missing Neo4j username/password in deployment configuration')
    return (NEO4J_USER, NEO4J_PASS)


# ---------------------------------------------------------------------------
# Write GraphChunk nodes back to Neo4j
# ---------------------------------------------------------------------------

UPSERT_CHUNK = f"""
UNWIND $rows AS row
MATCH (src) WHERE elementId(src) = row.node_id
MERGE (c:{CHUNK_LABEL} {{node_id: row.node_id}})
SET c.{TEXT_PROPERTY}       = row.content,
    c.{EMBEDDING_PROPERTY}  = row.embedding,
    c.labels_source         = row.labels_source,
    c.updated_at            = datetime()
MERGE (c)-[:EMBEDDED_FROM]->(src)
RETURN count(c) AS written
"""


def upsert_chunks(driver, rows: List[Dict]):
    def write_batch(tx):
        record = tx.run(UPSERT_CHUNK, rows=rows).single(strict=True)
        if record['written'] != len(rows):
            raise RuntimeError('Embedding batch sources changed or chunks are duplicated; batch rolled back')
        return record['written']
    with driver.session(database=NEO4J_DATABASE) as session:
        return session.execute_write(write_batch)


# ---------------------------------------------------------------------------
# Ensure vector + keyword indexes exist
# ---------------------------------------------------------------------------

def ensure_indexes(driver, *, strict=False):
    for name in (VECTOR_INDEX_NAME, KEYWORD_INDEX_NAME, DATASHEET_VECTOR_INDEX, DATASHEET_KEYWORD_INDEX):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Embedding index names must contain only letters, digits and underscores')
    failures = []
    with driver.session(database=NEO4J_DATABASE) as session:
        # --- Operational ontology / import indexes ---
        for statement, label in [
            ("CREATE INDEX `idx_ontologyclass_prefix` IF NOT EXISTS FOR (n:OntologyClass) ON (n.prefix)", "OntologyClass.prefix"),
            ("CREATE INDEX `idx_ontologyclass_ontology_prefix` IF NOT EXISTS FOR (n:OntologyClass) ON (n.ontology_prefix)", "OntologyClass.ontology_prefix"),
            ("CREATE INDEX `idx_ontologyclass_ontology_id` IF NOT EXISTS FOR (n:OntologyClass) ON (n.ontology_id)", "OntologyClass.ontology_id"),
            ("CREATE INDEX `idx_ontologyclass_prefix_name` IF NOT EXISTS FOR (n:OntologyClass) ON (n.prefix, n.name)", "OntologyClass.prefix+name"),
            ("CREATE INDEX `idx_ontologyclass_ontology_prefix_name` IF NOT EXISTS FOR (n:OntologyClass) ON (n.ontology_prefix, n.name)", "OntologyClass.ontology_prefix+name"),
            ("CREATE TEXT INDEX `idx_ontologyclass_name_text` IF NOT EXISTS FOR (n:OntologyClass) ON (n.name)", "OntologyClass.name text"),
            ("CREATE INDEX `idx_ontologyproperty_prefix` IF NOT EXISTS FOR (n:OntologyProperty) ON (n.prefix)", "OntologyProperty.prefix"),
        ]:
            try:
                session.run(statement).consume()
                logger.info("Operational index ensured for %s", label)
            except Exception as exc:
                logger.warning("Operational index creation note for %s: %s", label, exc)

        # --- Operational uniqueness constraints ---
        # These are best-effort because legacy customer databases may already contain
        # duplicates. Import/search code still uses parameterized MERGE and indexes;
        # clean deployments get stronger duplicate protection automatically.
        for statement, label in [
            ("CREATE CONSTRAINT `uniq_graphchunk_node_id` IF NOT EXISTS FOR (c:GraphChunk) REQUIRE c.node_id IS UNIQUE", "GraphChunk.node_id"),
            ("CREATE CONSTRAINT `uniq_ontologyclass_uri` IF NOT EXISTS FOR (n:OntologyClass) REQUIRE n.uri IS UNIQUE", "OntologyClass.uri"),
            ("CREATE CONSTRAINT `uniq_objectproperty_uri` IF NOT EXISTS FOR (n:ObjectProperty) REQUIRE n.uri IS UNIQUE", "ObjectProperty.uri"),
            ("CREATE CONSTRAINT `uniq_datatypeproperty_uri` IF NOT EXISTS FOR (n:DatatypeProperty) REQUIRE n.uri IS UNIQUE", "DatatypeProperty.uri"),
        ]:
            try:
                session.run(statement).consume()
                logger.info("Operational constraint ensured for %s", label)
            except Exception as exc:
                logger.warning("Operational constraint creation skipped for %s: %s", label, exc)
                if label == 'GraphChunk.node_id':
                    failures.append('GraphChunk.node_id uniqueness constraint')

        # --- GraphChunk vector index ---
        try:
            session.run(f"""
                CREATE VECTOR INDEX `{VECTOR_INDEX_NAME}` IF NOT EXISTS
                FOR (c:{CHUNK_LABEL})
                ON (c.{EMBEDDING_PROPERTY})
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_VECTOR_DIMENSIONS},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """).consume()
            logger.info("Vector index '%s' ensured", VECTOR_INDEX_NAME)
        except Exception as exc:
            logger.warning("Vector index creation note: %s", exc)
            failures.append('GraphChunk vector index')

        # --- GraphChunk fulltext keyword index ---
        try:
            session.run(f"""
                CREATE FULLTEXT INDEX `{KEYWORD_INDEX_NAME}` IF NOT EXISTS
                FOR (c:{CHUNK_LABEL})
                ON EACH [c.{TEXT_PROPERTY}]
            """).consume()
            logger.info("Keyword index '%s' ensured", KEYWORD_INDEX_NAME)
        except Exception as exc:
            logger.warning("Keyword index creation note: %s", exc)
            failures.append('GraphChunk keyword index')

        # --- DatasheetChunk vector index ---
        try:
            session.run(f"""
                CREATE VECTOR INDEX `{DATASHEET_VECTOR_INDEX}` IF NOT EXISTS
                FOR (c:{DATASHEET_CHUNK_LABEL})
                ON (c.{EMBEDDING_PROPERTY})
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {EMBEDDING_VECTOR_DIMENSIONS},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """).consume()
            logger.info("Vector index '%s' ensured", DATASHEET_VECTOR_INDEX)
        except Exception as exc:
            logger.warning("Datasheet vector index creation note: %s", exc)

        # --- DatasheetChunk fulltext keyword index ---
        try:
            session.run(f"""
                CREATE FULLTEXT INDEX `{DATASHEET_KEYWORD_INDEX}` IF NOT EXISTS
                FOR (c:{DATASHEET_CHUNK_LABEL})
                ON EACH [c.{TEXT_PROPERTY}]
            """).consume()
            logger.info("Keyword index '%s' ensured", DATASHEET_KEYWORD_INDEX)
        except Exception as exc:
            logger.warning("Datasheet keyword index creation note: %s", exc)
        if strict and not failures:
            indexes = session.run(
                'SHOW INDEXES YIELD name, type, labelsOrTypes, properties, options '
                'WHERE name IN $names RETURN name, type, labelsOrTypes, properties, options',
                names=[VECTOR_INDEX_NAME, KEYWORD_INDEX_NAME],
            ).data()
            by_name = {index['name']: index for index in indexes}
            vector = by_name.get(VECTOR_INDEX_NAME, {})
            keyword = by_name.get(KEYWORD_INDEX_NAME, {})
            dimensions = (vector.get('options') or {}).get('indexConfig', {}).get('vector.dimensions')
            similarity = (vector.get('options') or {}).get('indexConfig', {}).get('vector.similarity_function')
            if (vector.get('type') != 'VECTOR' or vector.get('labelsOrTypes') != [CHUNK_LABEL]
                    or vector.get('properties') != [EMBEDDING_PROPERTY]
                    or dimensions != EMBEDDING_VECTOR_DIMENSIONS or similarity != 'cosine'):
                failures.append('GraphChunk vector index configuration mismatch')
            if (keyword.get('type') != 'FULLTEXT' or keyword.get('labelsOrTypes') != [CHUNK_LABEL]
                    or keyword.get('properties') != [TEXT_PROPERTY]):
                failures.append('GraphChunk keyword index configuration mismatch')
    if strict and failures:
        raise RuntimeError('Required embedding schema could not be ensured: ' + ', '.join(failures))


def ensure_indexes_standalone():
    """Create all required vector + keyword indexes without running the full
    embedding pipeline.  Safe to call at application startup so that
    ``vector.py`` can connect to the indexes even before any chunks exist.
    
    ✅ Uses centralized driver connection when available.
    """
    try:
        if CENTRALIZED_CONFIG_AVAILABLE:
            driver = get_driver()
            logger.info("Using centralized driver for index creation")
            ensure_indexes(driver)
        else:
            driver = GraphDatabase.driver(NEO4J_URI, auth=_standalone_auth())
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

    Provider failures raise rather than reporting completion. Earlier successful
    batches remain persisted; rerunning without force resumes missing chunks.
    
    ✅ Uses centralized driver connection when available.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError('batch_size must be a positive integer')
    if not EMBEDDER_AVAILABLE:
        raise RuntimeError('Embedding model is unavailable; check Ollama/Azure configuration')

    try:
        if CENTRALIZED_CONFIG_AVAILABLE:
            driver = get_driver()
            logger.info("Using centralized driver for embedding pipeline")
        else:
            driver = GraphDatabase.driver(NEO4J_URI, auth=_standalone_auth())
            logger.info("Using standalone driver for embedding pipeline")
    except Exception as exc:
        logger.error(f"Failed to get driver: {exc}")
        raise

    try:
        ensure_indexes(driver, strict=True)
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
            _validate_vectors(vectors, len(batch))

            for doc, vec in zip(batch, vectors):
                doc["embedding"] = vec

            upsert_chunks(driver, batch)
            logger.info("Batch %d upserted", batch_num)

            if i + batch_size < len(documents):
                time.sleep(0.5)

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
