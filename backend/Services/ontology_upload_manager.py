"""
AP239 Ontology Upload Handler
Captures ontology metadata and stores files for reuse
"""

import os
import json
import time
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import re

logger = logging.getLogger(__name__)


class OntologyUploadManager:
    """Manages ontology file uploads and metadata"""
    
    # Storage directory for uploaded ontology files (configurable via env or defaults to ontology_uploads/)
    ONTOLOGY_STORAGE_DIR = Path(
        os.getenv('ONTOLOGY_STORAGE_DIR') or str(Path(__file__).parent.parent.parent / "ontology_uploads")
    )
    _LIST_CACHE_TTL_SEC = 5
    _list_cache: Optional[Dict[str, Any]] = None
    _list_cache_ts: float = 0.0

    @classmethod
    def _invalidate_list_cache(cls) -> None:
        cls._list_cache = None
        cls._list_cache_ts = 0.0
    
    @classmethod
    def initialize(cls):
        """Create storage directory if it doesn't exist"""
        cls.ONTOLOGY_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ontology storage initialized at: {cls.ONTOLOGY_STORAGE_DIR}")
    
    @classmethod
    def save_ontology_file(
        cls,
        file_content: bytes,
        filename: str,
        ontology_name: str,
        prefix: str,
        file_type: str,
        generation_type: str,
        description: str = "",
        schema_type: str = "schema"
    ) -> Dict[str, Any]:
        """
        Save ontology file and metadata
        
        Args:
            file_content: Raw file bytes (XSD/XMI)
            filename: Original filename
            ontology_name: User-friendly name (e.g., "AP239 Product Model")
            prefix: Ontology prefix (e.g., "ap239")
            file_type: File extension (xsd, xmi)
            generation_type: What to generate (shacl, owl, both)
            description: Ontology description
            schema_type: File classification ("schema" or "instance")
        
        Returns:
            {
                'status': 'success',
                'ontology_id': str,
                'storage_path': str,
                'metadata_path': str,
                'metadata': {...}
            }
        """
        try:
            cls.initialize()

            # ── Versioning: detect existing entry for same prefix+file_type+generation_type ──
            existing = cls._find_existing(prefix, file_type, generation_type)
            version = (existing.get('version', 1) + 1) if existing else 1
            replaces = existing.get('ontology_id') if existing else None
            # Carry forward full version history
            prev_history = existing.get('previous_versions', []) if existing else []
            if existing:
                prev_entry = {k: v for k, v in existing.items() if k != 'previous_versions'}
                previous_versions = [prev_entry] + prev_history
            else:
                previous_versions = []

            # Mark old entry as superseded so list_ontologies can filter to latest only
            if existing:
                cls._mark_superseded(existing['ontology_id'])

            # Create ontology subdirectory
            # Normalize prefix to a filesystem-safe token
            safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', str(prefix or '').strip().lower()) or 'ontology'
            ontology_id = f"{safe_prefix}_{int(datetime.now().timestamp())}"
            ontology_dir = cls.ONTOLOGY_STORAGE_DIR / ontology_id
            ontology_dir.mkdir(parents=True, exist_ok=True)

            # Save file
            file_path = ontology_dir / filename
            with open(file_path, 'wb') as f:
                f.write(file_content)

            # Create metadata with version info
            metadata = {
                'ontology_id': ontology_id,
                'ontology_name': ontology_name,
                'prefix': prefix,
                'ontology_prefix': prefix,
                'file_type': file_type,
                'generation_type': generation_type,
                'description': description,
                'schema_type': schema_type or 'schema',
                'original_filename': filename,
                'stored_filename': filename,
                'file_path': str(file_path),
                'file_size': len(file_content),
                'uploaded_at': datetime.now().isoformat(),
                'status': 'uploaded',
                'version': version,
                'is_latest': True,
                'replaces': replaces,
                'previous_versions': previous_versions,
            }

            # Save metadata (no BOM)
            metadata_path = ontology_dir / 'metadata.json'
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Saved ontology {ontology_id} v{version} to {ontology_dir}")
            cls._invalidate_list_cache()

            return {
                'status': 'success',
                'ontology_id': ontology_id,
                'storage_path': str(file_path),
                'metadata_path': str(metadata_path),
                'metadata': metadata,
                'version': version,
                'is_new_version': existing is not None,
                'replaces': replaces,
            }

        except Exception as e:
            logger.exception("Error saving ontology file")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    @classmethod
    def get_ontology(cls, ontology_id: str) -> Dict[str, Any]:
        """Retrieve ontology metadata"""
        try:
            metadata_path = cls.ONTOLOGY_STORAGE_DIR / ontology_id / 'metadata.json'
            
            if not metadata_path.exists():
                return {'status': 'error', 'error': 'Ontology not found'}
            
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                metadata = json.load(f)
            
            return {
                'status': 'success',
                'metadata': metadata,
                'file_exists': Path(metadata.get('file_path', '')).exists()
            }
        except Exception as e:
            logger.exception("Error retrieving ontology")
            return {'status': 'error', 'error': str(e)}
    
    @classmethod
    def list_ontologies(cls) -> Dict[str, Any]:
        """List all uploaded ontologies — returns only the latest version of each."""
        try:
            cls.initialize()
            now = time.time()
            if cls._list_cache is not None and (now - cls._list_cache_ts) < cls._LIST_CACHE_TTL_SEC:
                return cls._list_cache
            
            all_ontologies = []
            if cls.ONTOLOGY_STORAGE_DIR.exists():
                for ontology_dir in sorted(cls.ONTOLOGY_STORAGE_DIR.iterdir()):
                    if ontology_dir.is_dir():
                        metadata_path = ontology_dir / 'metadata.json'
                        if metadata_path.exists():
                            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                                metadata = json.load(f)
                            all_ontologies.append(metadata)

            # Only show the latest version of each ontology.
            # Entries without is_latest key are treated as latest (legacy uploads).
            ontologies = [o for o in all_ontologies if o.get('is_latest', True)]
            # Strip heavyweight previous_versions array to keep the response small.
            for o in ontologies:
                o.pop('previous_versions', None)

            result = {
                'status': 'success',
                'ontologies': ontologies,
                'count': len(ontologies)
            }
            cls._list_cache = result
            cls._list_cache_ts = now
            return result
        except Exception as e:
            logger.exception("Error listing ontologies")
            return {'status': 'error', 'error': str(e)}

    @staticmethod
    def _query_configured_neo4j(cypher: str, params: Optional[Dict[str, Any]] = None, graph=None) -> list[dict]:
        """Run read queries using the app graph wrapper or the official Neo4j driver."""
        params = params or {}
        if graph is not None:
            try:
                return graph.query(cypher, params=params) or []
            except Exception as exc:
                logger.debug("Graph wrapper query unavailable; falling back to official driver: %s", exc)

        try:
            try:
                from backend.core.db_config import get_config, get_driver
            except Exception:
                from core.db_config import get_config, get_driver

            config = get_config()
            driver = get_driver()
            with driver.session(database=config.database) as session:
                result = session.run(cypher, params)
                return [dict(record) for record in result]
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    @classmethod
    def list_ontologies_with_neo4j_counts(cls, graph=None, include_neo4j_only: bool = True) -> Dict[str, Any]:
        """List registered ontology prefixes with runtime Neo4j counts.

        File metadata is the product registry. Neo4j is used only as the
        configured runtime validation source for node/relationship availability.
        """
        result = cls.list_ontologies()
        if result.get("status") != "success":
            return result

        ontologies = [dict(row) for row in result.get("ontologies", [])]
        by_prefix: Dict[str, Dict[str, Any]] = {}
        for row in ontologies:
            prefix = str(row.get("prefix") or row.get("ontology_prefix") or row.get("ontology_id") or "").strip()
            if not prefix:
                continue
            row["prefix"] = prefix
            row["ontology_prefix"] = row.get("ontology_prefix") or prefix
            row["source"] = row.get("source") or "registered"
            row.setdefault("node_count", row.get("neo4j_nodes_merged", 0) or 0)
            row.setdefault("relationship_count", row.get("neo4j_relationships_merged", 0) or 0)
            row["availability"] = "metadata_only"
            by_prefix[prefix.lower()] = row

        count_query = """
        MATCH (n)
        WHERE n.prefix = $prefix
           OR n.ontology_prefix = $prefix
           OR n.source_ontology = $ontology_id
        WITH collect(DISTINCT n) AS nodes
        UNWIND CASE WHEN size(nodes) = 0 THEN [NULL] ELSE nodes END AS a
        OPTIONAL MATCH (a)-[r]-(b)
        WHERE b IN nodes
        RETURN size(nodes) AS node_count,
               count(DISTINCT r) AS relationship_count
        """
        for row in by_prefix.values():
            try:
                counts = cls._query_configured_neo4j(count_query, params={
                    "prefix": row.get("prefix"),
                    "ontology_id": row.get("ontology_id") or row.get("prefix"),
                }, graph=graph)
                first = counts[0] if counts else {}
                node_count = int(first.get("node_count") or 0)
                relationship_count = int(first.get("relationship_count") or 0)
                row["node_count"] = node_count
                row["relationship_count"] = relationship_count
                if node_count > 0 and relationship_count > 0:
                    row["availability"] = "available"
                elif node_count > 0:
                    row["availability"] = "loaded_empty"
                else:
                    row["availability"] = "metadata_only"
            except Exception as exc:
                row["availability"] = "count_failed"
                row["count_error"] = str(exc)

        if include_neo4j_only:
            try:
                direct_rows = cls._query_configured_neo4j(
                    """
                    MATCH (n)
                    WHERE n.prefix IS NOT NULL
                      AND NOT (n:DatasheetChunk OR n:GraphChunk)
                    WITH n.prefix AS prefix, collect(DISTINCT n) AS nodes
                    UNWIND nodes AS a
                    OPTIONAL MATCH (a)-[r]-(b)
                    WHERE b IN nodes
                    WITH prefix, nodes, count(DISTINCT r) AS relationship_count
                    RETURN prefix,
                           coalesce(head([n IN nodes WHERE n.ontology_name IS NOT NULL | n.ontology_name]), prefix) AS ontology_name,
                           size(nodes) AS node_count,
                           relationship_count
                    ORDER BY prefix
                    """,
                    graph=graph,
                )
                for direct in direct_rows:
                    prefix = str(direct.get("prefix") or "").strip()
                    if not prefix or prefix.lower() in by_prefix:
                        continue
                    name = str(direct.get("ontology_name") or prefix).replace(" SPLM", "").replace("_splm", "").strip() or prefix.upper()
                    node_count = int(direct.get("node_count") or 0)
                    relationship_count = int(direct.get("relationship_count") or 0)
                    by_prefix[prefix.lower()] = {
                        "ontology_id": prefix,
                        "ontology_name": name,
                        "name": name,
                        "prefix": prefix,
                        "ontology_prefix": prefix,
                        "file_type": "neo4j",
                        "generation_type": "direct",
                        "schema_type": "schema",
                        "source": "neo4j",
                        "status": "discovered",
                        "node_count": node_count,
                        "relationship_count": relationship_count,
                        "availability": "available" if relationship_count > 0 else "loaded_empty",
                    }
            except Exception as exc:
                logger.warning("Neo4j ontology prefix discovery failed: %s", exc)

        rows = sorted(by_prefix.values(), key=lambda item: str(item.get("prefix") or ""))
        return {
            "status": "success",
            "ontologies": rows,
            "count": len(rows),
        }

    @classmethod
    def list_all_ontologies(cls) -> Dict[str, Any]:
        """List all ontology metadata entries, including superseded versions."""
        try:
            cls.initialize()
            ontologies = []

            if cls.ONTOLOGY_STORAGE_DIR.exists():
                for ontology_dir in sorted(cls.ONTOLOGY_STORAGE_DIR.iterdir()):
                    if not ontology_dir.is_dir():
                        continue
                    metadata_path = ontology_dir / 'metadata.json'
                    if not metadata_path.exists():
                        continue
                    with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                        metadata = json.load(f)
                    metadata.pop('previous_versions', None)
                    ontologies.append(metadata)

            return {
                'status': 'success',
                'ontologies': ontologies,
                'count': len(ontologies),
            }
        except Exception as e:
            logger.exception("Error listing all ontologies")
            return {'status': 'error', 'error': str(e)}

    @classmethod
    def clear_all_metadata(cls) -> Dict[str, Any]:
        """✅ NEW: Clear ALL ontology metadata files from storage.
        
        Used when Neo4j schema is completely wiped to remove orphaned metadata.
        This ensures that after schema cleanup, no ontology names appear in UI.
        """
        try:
            cls.initialize()
            deleted_dirs = 0
            # Remove entire ontology subdirectories to avoid leaving orphaned files
            if cls.ONTOLOGY_STORAGE_DIR.exists():
                for ontology_dir in list(cls.ONTOLOGY_STORAGE_DIR.iterdir()):
                    if ontology_dir.is_dir():
                        try:
                            shutil.rmtree(ontology_dir)
                            deleted_dirs += 1
                        except Exception as e:
                            logger.warning(f"Could not remove ontology directory {ontology_dir}: {e}")
            
            cls._invalidate_list_cache()
            logger.info(f"Removed {deleted_dirs} ontology directories from storage")
            return {'status': 'success', 'cleared': deleted_dirs}
        except Exception as e:
            logger.exception("Error clearing metadata")
            return {'status': 'error', 'error': str(e)}

    @classmethod
    def delete_ontology(cls, ontology_id: str) -> Dict[str, Any]:
        """Delete ontology metadata/files from local storage by ontology ID."""
        try:
            cls.initialize()
            ontology_dir = cls.ONTOLOGY_STORAGE_DIR / ontology_id
            metadata_path = ontology_dir / 'metadata.json'

            if not metadata_path.exists():
                return {'status': 'error', 'error': f'Ontology not found: {ontology_id}'}

            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                metadata = json.load(f)

            shutil.rmtree(ontology_dir, ignore_errors=False)
            cls._invalidate_list_cache()

            return {
                'status': 'success',
                'ontology_id': ontology_id,
                'prefix': metadata.get('prefix'),
                'file_type': metadata.get('file_type'),
            }
        except Exception as e:
            logger.exception("Error deleting ontology %s", ontology_id)
            return {'status': 'error', 'error': str(e)}
    
    @classmethod
    def get_file_for_reuse(cls, ontology_id: str) -> Optional[bytes]:
        """Retrieve file for reuse/reprocessing"""
        try:
            metadata_path = cls.ONTOLOGY_STORAGE_DIR / ontology_id / 'metadata.json'
            
            if not metadata_path.exists():
                return None
            
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                metadata = json.load(f)
            
            file_path = metadata['file_path']
            if Path(file_path).exists():
                with open(file_path, 'rb') as f:
                    return f.read()
            
            return None
        except Exception as e:
            logger.exception("Error retrieving file for reuse")
            return None

    # ──────────────────────────────────────────────────────────────
    # Version management helpers
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _find_existing(cls, prefix: str, file_type: str, generation_type: str) -> Optional[Dict[str, Any]]:
        """Return the current latest entry for the given prefix+file_type+generation_type, or None."""
        try:
            result = cls.list_ontologies()
            if result['status'] != 'success':
                return None
            matches = [
                o for o in result['ontologies']
                if o.get('prefix') == prefix
                and o.get('file_type') == file_type
                and o.get('generation_type') == generation_type
                and o.get('is_latest', True)  # only consider the current latest
            ]
            if not matches:
                return None
            return max(matches, key=lambda o: o.get('version', 1))
        except Exception as e:
            logger.exception("Unexpected error while finding existing ontology")
            return None

    @classmethod
    def _mark_superseded(cls, ontology_id: str) -> None:
        """Set is_latest=False on the given ontology entry (it has been replaced by a newer version)."""
        try:
            metadata_path = cls.ONTOLOGY_STORAGE_DIR / ontology_id / 'metadata.json'
            if not metadata_path.exists():
                return
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                meta = json.load(f)
            meta['is_latest'] = False
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
            cls._invalidate_list_cache()
        except Exception as e:
            logger.exception("Could not mark %s as superseded", ontology_id)

    @classmethod
    def list_latest_ontologies(cls) -> Dict[str, Any]:
        """Return only the latest version of each prefix+file_type combination."""
        result = cls.list_ontologies()
        if result['status'] != 'success':
            return result
        latest = [o for o in result['ontologies'] if o.get('is_latest', True)]
        return {'status': 'success', 'ontologies': latest, 'count': len(latest)}

    # ──────────────────────────────────────────────────────────────
    # Neo4j push
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _term_id(term) -> str:
        return str(term)

    @staticmethod
    def _local_name(term) -> str:
        text = str(term)
        if "#" in text:
            return text.rsplit("#", 1)[-1]
        return text.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _namespace(term) -> str:
        text = str(term)
        if "#" in text:
            return text.rsplit("#", 1)[0] + "#"
        return text.rstrip("/").rsplit("/", 1)[0] + "/"

    @classmethod
    def _rdf_labels(cls, rdf_graph: Any) -> Dict[str, str]:
        from rdflib import Literal, URIRef
        from rdflib.namespace import RDFS

        labels: Dict[str, str] = {}
        for s, _, o in rdf_graph.triples((None, RDFS.label, None)):
            if isinstance(s, URIRef) and isinstance(o, Literal):
                labels[cls._term_id(s)] = str(o)
        return labels

    @staticmethod
    def _parse_rdf_content(file_content: bytes, filename: str) -> Any:
        from rdflib import Graph as RDFGraph

        rdf_graph = RDFGraph()
        ext = Path(filename).suffix.lower()
        candidates = ["turtle", "n3", "xml"] if ext == ".ttl" else ["xml", "turtle", "n3"]
        last_error: Exception | None = None
        text = file_content.decode("utf-8", errors="replace")
        for fmt in candidates:
            try:
                rdf_graph.parse(data=text, format=fmt)
                return rdf_graph
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        return rdf_graph

    @classmethod
    def _generate_rdf_for_source(cls, file_content: bytes, filename: str, file_type: str, generation_type: str) -> tuple[Any, str, Dict[str, Any]]:
        if file_type == "xsd":
            from rdflib import Graph as RDFGraph
            from .owl_generation_service import OWLGenerationService
            ttl, metadata = OWLGenerationService.generate_owl_from_xsd(file_content, filename)
            rdf_graph = RDFGraph()
            rdf_graph.parse(data=ttl, format="turtle")
            return rdf_graph, ttl, metadata
        if file_type == "ontology":
            rdf_graph = cls._parse_rdf_content(file_content, filename)
            return rdf_graph, file_content.decode("utf-8", errors="replace"), {"format": "RDF", "generation_type": generation_type}
        raise ValueError(f"RDF semantic push is not available for file type: {file_type}")

    @classmethod
    def _push_rdf_graph_to_neo4j(
        cls,
        ontology_id: str,
        meta: Dict[str, Any],
        rdf_graph: Any,
        graph,
        owl_file_path: str = "",
    ) -> Dict[str, Any]:
        from rdflib import URIRef
        from rdflib.namespace import RDF, RDFS, OWL

        prefix = meta["prefix"]
        ontology_name = meta["ontology_name"]
        version = meta.get("version", 1)
        labels = cls._rdf_labels(rdf_graph)

        class_terms = {
            s for s in rdf_graph.subjects(RDF.type, OWL.Class)
            if isinstance(s, URIRef)
        }
        object_props = {
            s for s in rdf_graph.subjects(RDF.type, OWL.ObjectProperty)
            if isinstance(s, URIRef)
        }
        datatype_props = {
            s for s in rdf_graph.subjects(RDF.type, OWL.DatatypeProperty)
            if isinstance(s, URIRef)
        }

        class_rows = [
            {
                "uri": cls._term_id(term),
                "name": labels.get(cls._term_id(term)) or cls._local_name(term),
                "namespace": cls._namespace(term),
                "comment": str(next(rdf_graph.objects(term, RDFS.comment), "")),
            }
            for term in sorted(class_terms, key=str)
        ]
        object_rows = [
            {
                "uri": cls._term_id(term),
                "name": labels.get(cls._term_id(term)) or cls._local_name(term),
                "namespace": cls._namespace(term),
                "comment": str(next(rdf_graph.objects(term, RDFS.comment), "")),
            }
            for term in sorted(object_props, key=str)
        ]
        datatype_rows = [
            {
                "uri": cls._term_id(term),
                "name": labels.get(cls._term_id(term)) or cls._local_name(term),
                "namespace": cls._namespace(term),
                "comment": str(next(rdf_graph.objects(term, RDFS.comment), "")),
            }
            for term in sorted(datatype_props, key=str)
        ]

        subclass_rows = [
            {"child_uri": cls._term_id(s), "parent_uri": cls._term_id(o)}
            for s, _, o in rdf_graph.triples((None, RDFS.subClassOf, None))
            if isinstance(s, URIRef) and isinstance(o, URIRef) and s in class_terms
        ]

        domain_rows = []
        range_rows = []
        for prop in sorted(object_props | datatype_props, key=str):
            prop_uri = cls._term_id(prop)
            for domain in rdf_graph.objects(prop, RDFS.domain):
                if isinstance(domain, URIRef):
                    domain_rows.append({"prop_uri": prop_uri, "class_uri": cls._term_id(domain)})
            for range_term in rdf_graph.objects(prop, RDFS.range):
                if isinstance(range_term, URIRef):
                    range_rows.append({"prop_uri": prop_uri, "range_uri": cls._term_id(range_term)})

        def _run(cypher: str, rows: list[dict]) -> int:
            if not rows:
                return 0
            total = 0
            batch = 500
            for idx in range(0, len(rows), batch):
                result = graph.query(cypher, params={
                    "rows": rows[idx:idx + batch],
                    "prefix": prefix,
                    "ontology_id": ontology_id,
                    "ontology_name": ontology_name,
                    "version": version,
                    "owl_file_path": owl_file_path,
                })
                total += (result or [{"count": len(rows[idx:idx + batch])}])[0].get("count", len(rows[idx:idx + batch]))
            return total

        class_cypher = """
UNWIND $rows AS row
MERGE (c:OntologyClass {uri: row.uri, prefix: $prefix})
ON CREATE SET c.created_at = datetime()
SET c.name = row.name,
    c.concept_type = 'owl:Class',
    c.namespace = row.namespace,
    c.comment = row.comment,
    c.source_ontology = $ontology_id,
    c.ontology_name = $ontology_name,
    c.version = $version,
    c.ontology_prefix = $prefix,
    c.schema_type = 'schema',
    c.owl_file_path = $owl_file_path,
    c.updated_at = datetime()
RETURN count(c) AS count
"""
        object_prop_cypher = """
UNWIND $rows AS row
MERGE (p:ObjectProperty {uri: row.uri, prefix: $prefix})
ON CREATE SET p.created_at = datetime()
SET p.name = row.name,
    p.concept_type = 'owl:ObjectProperty',
    p.namespace = row.namespace,
    p.comment = row.comment,
    p.source_ontology = $ontology_id,
    p.ontology_name = $ontology_name,
    p.version = $version,
    p.ontology_prefix = $prefix,
    p.schema_type = 'schema',
    p.owl_file_path = $owl_file_path,
    p.updated_at = datetime()
RETURN count(p) AS count
"""
        datatype_prop_cypher = """
UNWIND $rows AS row
MERGE (p:DatatypeProperty {uri: row.uri, prefix: $prefix})
ON CREATE SET p.created_at = datetime()
SET p.name = row.name,
    p.concept_type = 'owl:DatatypeProperty',
    p.namespace = row.namespace,
    p.comment = row.comment,
    p.source_ontology = $ontology_id,
    p.ontology_name = $ontology_name,
    p.version = $version,
    p.ontology_prefix = $prefix,
    p.schema_type = 'schema',
    p.owl_file_path = $owl_file_path,
    p.updated_at = datetime()
RETURN count(p) AS count
"""
        subclass_cypher = """
UNWIND $rows AS row
MATCH (child:OntologyClass {uri: row.child_uri, prefix: $prefix})
MATCH (parent:OntologyClass {uri: row.parent_uri, prefix: $prefix})
MERGE (child)-[r:SUBCLASS_OF]->(parent)
RETURN count(r) AS count
"""
        domain_cypher = """
UNWIND $rows AS row
MATCH (p {uri: row.prop_uri, prefix: $prefix})
MATCH (c:OntologyClass {uri: row.class_uri, prefix: $prefix})
WHERE p:ObjectProperty OR p:DatatypeProperty
MERGE (p)-[r:DOMAIN]->(c)
RETURN count(r) AS count
"""
        range_cypher = """
UNWIND $rows AS row
MATCH (p {uri: row.prop_uri, prefix: $prefix})
WHERE p:ObjectProperty OR p:DatatypeProperty
MATCH (c:OntologyClass {uri: row.range_uri, prefix: $prefix})
MERGE (p)-[r:RANGE]->(c)
RETURN count(r) AS count
"""

        classes_created = _run(class_cypher, class_rows)
        object_props_created = _run(object_prop_cypher, object_rows)
        datatype_props_created = _run(datatype_prop_cypher, datatype_rows)
        subclass_created = _run(subclass_cypher, subclass_rows)
        domain_created = _run(domain_cypher, domain_rows)
        range_created = _run(range_cypher, range_rows)

        relationships_created = subclass_created + domain_created + range_created
        logger.info(
            "Ontology RDF push %s: classes=%s object_properties=%s datatype_properties=%s "
            "subclass=%s domain=%s range=%s neo4j_nodes=%s neo4j_relationships=%s",
            ontology_id,
            len(class_rows),
            len(object_rows),
            len(datatype_rows),
            len(subclass_rows),
            len(domain_rows),
            len(range_rows),
            classes_created + object_props_created + datatype_props_created,
            relationships_created,
        )
        return {
            "status": "success",
            "ontology_id": ontology_id,
            "version": version,
            "nodes_merged": classes_created + object_props_created + datatype_props_created,
            "relationships_merged": relationships_created,
            "parsed_class_count": len(class_rows),
            "parsed_object_property_count": len(object_rows),
            "parsed_datatype_property_count": len(datatype_rows),
            "parsed_subclass_relationship_count": len(subclass_rows),
            "parsed_domain_relationship_count": len(domain_rows),
            "parsed_range_relationship_count": len(range_rows),
        }

    @classmethod
    def push_to_neo4j(cls, ontology_id: str, graph, schema_type: str = "schema") -> Dict[str, Any]:
        """Parse the stored ontology file and MERGE its entities into Neo4j as OntologyClass or Instance nodes.

        Args:
            ontology_id: The ontology_id returned by save_ontology_file.
            graph: The langchain_neo4j GraphProxy (from core.graph).
            schema_type: "schema" creates OntologyClass nodes, "instance" creates Instance nodes.

        Returns:
            {'status': 'success', 'nodes_merged': int, 'ontology_id': str}
        """
        try:
            meta_result = cls.get_ontology(ontology_id)
            if meta_result['status'] != 'success':
                return {'status': 'error', 'error': f"Ontology not found: {ontology_id}"}

            meta = meta_result['metadata']
            file_path = Path(meta['file_path'])
            if not file_path.exists():
                return {'status': 'error', 'error': f"File missing: {file_path}"}

            file_content = file_path.read_bytes()
            prefix = meta['prefix']
            version = meta.get('version', 1)
            ontology_name = meta['ontology_name']
            file_type = meta['file_type']
            # Use schema_type from metadata or parameter override
            determined_schema_type = schema_type or meta.get('schema_type', 'schema')

            if determined_schema_type == "schema" and file_type in {"xsd", "ontology"}:
                rdf_graph, ttl_text, owl_metadata = cls._generate_rdf_for_source(
                    file_content=file_content,
                    filename=file_path.name,
                    file_type=file_type,
                    generation_type=meta.get("generation_type", ""),
                )
                owl_file_path = ""
                if file_type == "xsd":
                    owl_path = file_path.with_suffix(".generated.ttl")
                    owl_path.write_text(ttl_text, encoding="utf-8")
                    owl_file_path = str(owl_path)
                elif file_path.suffix.lower() in {".ttl", ".rdf", ".owl"}:
                    owl_file_path = str(file_path)

                rdf_result = cls._push_rdf_graph_to_neo4j(
                    ontology_id=ontology_id,
                    meta=meta,
                    rdf_graph=rdf_graph,
                    graph=graph,
                    owl_file_path=owl_file_path,
                )
                cls._update_status(ontology_id, 'pushed_to_neo4j', {
                    'neo4j_nodes_merged': rdf_result.get('nodes_merged', 0),
                    'neo4j_relationships_merged': rdf_result.get('relationships_merged', 0),
                    'owl_file_path': owl_file_path,
                    'owl_generation_metadata': owl_metadata,
                    'parsed_class_count': rdf_result.get('parsed_class_count', 0),
                    'parsed_object_property_count': rdf_result.get('parsed_object_property_count', 0),
                    'parsed_datatype_property_count': rdf_result.get('parsed_datatype_property_count', 0),
                    'parsed_subclass_relationship_count': rdf_result.get('parsed_subclass_relationship_count', 0),
                    'parsed_domain_relationship_count': rdf_result.get('parsed_domain_relationship_count', 0),
                    'parsed_range_relationship_count': rdf_result.get('parsed_range_relationship_count', 0),
                })
                return rdf_result

            # Parse entities
            rows: list = []
            xmi_relationships: list = []
            extracted_relationships: list = []
            if file_type == 'xsd':
                try:
                    from .ap239_parser import parse_ap239_xsd
                    rows, _ = parse_ap239_xsd(file_content)
                except Exception as e:
                    logger.warning(f"AP239 parse fallback: {e}")
                    from .unified_data_import import FileFormatDetector
                    rows, _ = FileFormatDetector.parse_xsd(file_content)
            elif file_type == 'xmi':
                from .unified_data_import import FileFormatDetector
                rows, stats = FileFormatDetector.parse_xmi(file_content)
                xmi_relationships = list((stats or {}).get("_xmi_relationships", []) or [])
            elif file_type == 'ontology':
                from .unified_data_import import FileFormatDetector
                rows, _ = FileFormatDetector.parse_rdf(file_content, file_path.name)
            elif file_type == '3dxml':
                try:
                    from .threedxml_ontology_extractor import ThreeDXMLExtractor
                except Exception:
                    from backend.Services.threedxml_ontology_extractor import ThreeDXMLExtractor

                with tempfile.TemporaryDirectory(prefix='threedxml_') as temp_dir:
                    temp_file_path = Path(temp_dir) / file_path.name
                    temp_file_path.write_bytes(file_content)
                    extractor = ThreeDXMLExtractor(temp_dir)
                    extracted = extractor.extract()
                    rows = list((extracted or {}).get('entities', {}).values())
                    extracted_relationships = list(extractor.relationships or [])
            else:
                return {'status': 'error', 'error': f"Unsupported file type for Neo4j push: {file_type}"}

            # Build valid row list (must have a name)
            # Also capture every non-empty property key from each row as an OntologyProperty.
            valid_rows = []
            property_rows: list = []   # [{class_name, prop_name}]

            _SKIP_KEYS = {"name", "concept_type", "namespace", "type", "id", "label"}

            def _resolve_row_name(row: Dict[str, Any]) -> str:
                name = str(row.get('name', '')).strip()
                if name:
                    return name
                raw_type = row.get('type') or row.get('label')
                if raw_type:
                    token = str(raw_type).split(':')[-1].strip()
                    if token:
                        return token
                for fallback_key in ('local_name', 'id'):
                    fallback = row.get(fallback_key)
                    if fallback:
                        return str(fallback).strip()
                return ''

            for r in rows:
                name = _resolve_row_name(r)
                if not name:
                    continue
                concept_type = str(
                    r.get('concept_type')
                    or r.get('entity_type')
                    or r.get('type')
                    or 'Unknown'
                )
                namespace = str(r.get('namespace', prefix))
                valid_rows.append({
                    'name': name,
                    'concept_type': concept_type,
                    'namespace': namespace,
                })
                attributes = r.get('attributes') if isinstance(r.get('attributes'), dict) else {}
                for attr_name in attributes.keys():
                    if attr_name and str(attr_name).strip():
                        property_rows.append({'class_name': name, 'prop_name': str(attr_name)})
                # Collect non-empty extra keys as OntologyProperty candidates
                for key, val in r.items():
                    if key in {'attributes', 'metadata', 'relationships'}:
                        continue
                    if key not in _SKIP_KEYS and val is not None and str(val).strip():
                        property_rows.append({'class_name': name, 'prop_name': str(key)})

            if not valid_rows:
                return {'status': 'success', 'nodes_merged': 0, 'ontology_id': ontology_id,
                        'message': 'No named entities found to push'}

            # MERGE into Neo4j — use dynamic node label based on schema_type
            # schema_type="schema" → OntologyClass nodes
            # schema_type="instance" → Instance nodes
            node_label = "OntologyClass" if determined_schema_type == "schema" else "Instance"
            
            cypher = f"""
UNWIND $rows AS row
MERGE (c:{node_label} {{name: row.name, prefix: $prefix}})
ON CREATE SET
    c.concept_type   = row.concept_type,
    c.namespace      = row.namespace,
    c.source_ontology = $ontology_id,
    c.ontology_name  = $ontology_name,
    c.version        = $version,
    c.ontology_prefix = $prefix,
    c.schema_type    = $schema_type,
    c.created_at     = datetime()
ON MATCH SET
    c.concept_type   = row.concept_type,
    c.source_ontology = $ontology_id,
    c.ontology_name  = $ontology_name,
    c.version        = $version,
    c.ontology_prefix = $prefix,
    c.schema_type    = $schema_type,
    c.updated_at     = datetime()
RETURN count(c) AS merged
"""
            result = graph.query(cypher, params={
                'rows': valid_rows,
                'prefix': prefix,
                'ontology_id': ontology_id,
                'ontology_name': ontology_name,
                'version': version,
                'schema_type': determined_schema_type,
            })
            merged = result[0]['merged'] if result else len(valid_rows)
            node_type_label = "OntologyClass" if determined_schema_type == "schema" else "Instance"
            logger.info(f"Neo4j push: {merged} {node_type_label} nodes merged for {ontology_id} v{version} (schema_type={determined_schema_type})")

            relationship_sources = []
            if xmi_relationships:
                relationship_sources.extend(
                    {
                        "from_label": (rel.get("from_label") or "").strip(),
                        "to_label": (rel.get("to_label") or "").strip(),
                        "type": (rel.get("type") or "RELATED_TO").strip() or "RELATED_TO",
                    }
                    for rel in xmi_relationships
                )
            if extracted_relationships:
                relationship_sources.extend(
                    {
                        "from_label": (rel.source or "").strip(),
                        "to_label": (rel.target or "").strip(),
                        "type": (rel.relation_type or "RELATED_TO").strip() or "RELATED_TO",
                    }
                    for rel in extracted_relationships
                )

            relationship_total = 0

            # For structured schema uploads, create class-to-class relationships from parsed links.
            if determined_schema_type == "schema" and relationship_sources:
                class_names = {row["name"] for row in valid_rows}
                rel_groups: Dict[str, set] = {}
                for rel in relationship_sources:
                    from_label = (rel.get("from_label") or "").strip()
                    to_label = (rel.get("to_label") or "").strip()
                    if not from_label or not to_label:
                        continue
                    if from_label not in class_names or to_label not in class_names:
                        continue
                    raw_type = (rel.get("type") or "RELATED_TO").strip() or "RELATED_TO"
                    rel_type = re.sub(r"[^A-Za-z0-9_]", "_", raw_type).upper()
                    rel_groups.setdefault(rel_type, set()).add((from_label, to_label))

                rel_total = 0
                for rel_type, pairs in rel_groups.items():
                    rel_rows = [{"from_label": f, "to_label": t} for (f, t) in pairs]
                    rel_cypher = f"""
UNWIND $rows AS row
MATCH (a:OntologyClass {{name: row.from_label, prefix: $prefix}})
MATCH (b:OntologyClass {{name: row.to_label, prefix: $prefix}})
MERGE (a)-[:{rel_type}]->(b)
"""
                    graph.query(rel_cypher, params={"rows": rel_rows, "prefix": prefix})
                    rel_total += len(rel_rows)
                if rel_total:
                    relationship_total = rel_total
                    logger.info(f"Neo4j push: {rel_total} OntologyClass relationships merged for {ontology_id}")

            # MERGE OntologyProperty nodes and link them to their OntologyClass
            # Deduplicate property rows to avoid repeated MERGE operations
            if property_rows:
                seen_props = set()
                deduped_props = []
                for pr in property_rows:
                    key = (pr['class_name'], pr['prop_name'])
                    if key in seen_props:
                        continue
                    seen_props.add(key)
                    deduped_props.append(pr)
                property_rows = deduped_props

            if property_rows:
                prop_cypher = """
UNWIND $rows AS row
MATCH (c:OntologyClass {name: row.class_name, prefix: $prefix})
MERGE (p:OntologyProperty {name: row.prop_name, prefix: $prefix})
ON CREATE SET p.ontology_prefix = $prefix
ON MATCH SET p.ontology_prefix = $prefix
MERGE (p)-[:PROPERTY_OF]->(c)
"""

                try:
                    _BATCH = 500
                    for _i in range(0, len(property_rows), _BATCH):
                        graph.query(prop_cypher, params={
                            'rows': property_rows[_i:_i + _BATCH],
                            'prefix': prefix,
                        })
                    logger.info(
                        f"Neo4j push: {len(property_rows)} OntologyProperty links merged "
                        f"for {ontology_id}"
                    )
                except Exception as prop_err:
                    logger.warning(f"OntologyProperty merge skipped: {prop_err}")

            # Update metadata status
            cls._update_status(ontology_id, 'pushed_to_neo4j', {
                'neo4j_nodes_merged': merged,
                'neo4j_relationships_merged': relationship_total,
            })

            return {
                'status': 'success',
                'nodes_merged': merged,
                'relationships_merged': relationship_total,
                'ontology_id': ontology_id,
                'version': version,
            }

        except Exception as e:
            logger.exception("Neo4j push error for %s", ontology_id)
            return {'status': 'error', 'error': str(e)}

    @classmethod
    def _update_status(cls, ontology_id: str, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Update the status field (and optional extra fields) in metadata.json."""
        try:
            metadata_path = cls.ONTOLOGY_STORAGE_DIR / ontology_id / 'metadata.json'
            if not metadata_path.exists():
                return
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                meta = json.load(f)
            meta['status'] = status
            if extra:
                meta.update(extra)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
            cls._invalidate_list_cache()
        except Exception as e:
            logger.exception("Could not update status for %s", ontology_id)

    @classmethod
    def update_metadata(cls, ontology_id: str, fields: Dict[str, Any]) -> None:
        """Merge arbitrary fields into an ontology's metadata.json (public helper)."""
        try:
            metadata_path = cls.ONTOLOGY_STORAGE_DIR / ontology_id / 'metadata.json'
            if not metadata_path.exists():
                return
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                meta = json.load(f)
            meta.update(fields)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
            cls._invalidate_list_cache()
        except Exception as e:
            logger.exception("Could not update metadata for %s", ontology_id)

