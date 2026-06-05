"""
AP239 Ontology Upload Handler
Captures ontology metadata and stores files for reuse
"""

import os
import json
import time
import shutil
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

            # Parse entities
            rows: list = []
            xmi_relationships: list = []
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
                concept_type = str(r.get('concept_type') or r.get('type') or 'Unknown')
                namespace = str(r.get('namespace', prefix))
                valid_rows.append({
                    'name': name,
                    'concept_type': concept_type,
                    'namespace': namespace,
                })
                # Collect non-empty extra keys as OntologyProperty candidates
                for key, val in r.items():
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

            # For XMI schema uploads, create class-to-class relationships from parsed XMI links.
            if determined_schema_type == "schema" and xmi_relationships:
                class_names = {row["name"] for row in valid_rows}
                rel_groups: Dict[str, set] = {}
                for rel in xmi_relationships:
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
            cls._update_status(ontology_id, 'pushed_to_neo4j', {'neo4j_nodes_merged': merged})

            return {
                'status': 'success',
                'nodes_merged': merged,
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

