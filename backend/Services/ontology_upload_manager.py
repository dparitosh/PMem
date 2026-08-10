"""
AP239 Ontology Upload Handler
Captures ontology metadata and stores files for reuse
"""

import os
import json
import time
import shutil
import tempfile
import copy
import threading
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

try:
    from backend.Services.ontology_identity import normalize_ontology_entry, normalize_ontology_entries
    from backend.Services.import_format_helpers import derive_prefix_from_namespace
except Exception:  # pragma: no cover - script mode fallback
    from Services.ontology_identity import normalize_ontology_entry, normalize_ontology_entries
    from Services.import_format_helpers import derive_prefix_from_namespace


class OntologyUploadManager:
    """Manages ontology file uploads and metadata"""
    
    # Storage directory for uploaded ontology files (configurable via env or defaults to ontology_uploads/)
    ONTOLOGY_STORAGE_DIR = Path(
        os.getenv('ONTOLOGY_STORAGE_DIR') or str(Path(__file__).parent.parent.parent / "ontology_uploads")
    )
    _LIST_CACHE_TTL_SEC = 5
    _LIST_CACHE_ENABLED = os.getenv('ONTOLOGY_LIST_CACHE_ENABLED', 'false').lower() == 'true'
    _list_cache: Optional[Dict[str, Any]] = None
    _list_cache_ts: float = 0.0
    _metadata_lock = threading.RLock()

    @classmethod
    def _invalidate_list_cache(cls) -> None:
        cls._list_cache = None
        cls._list_cache_ts = 0.0

    @classmethod
    def _atomic_write_json(cls, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _safe_upload_filename(filename: str) -> str:
        raw = str(filename or "").strip().replace("\\", "/")
        safe_name = Path(raw).name
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("A valid upload filename is required")
        return safe_name

    @staticmethod
    def _derive_ontology_namespace(file_content: bytes, filename: str, file_type: str) -> str:
        """Discover the ontology URI from XSD or RDF/OWL content."""
        if file_type == "xsd":
            try:
                root = ET.fromstring(file_content)
                return str(root.attrib.get("targetNamespace") or "").strip().rstrip("#/" )
            except Exception:
                return ""
        if file_type != "ontology":
            return ""
        try:
            from rdflib import Graph, URIRef
            from rdflib.namespace import OWL, RDF

            graph = Graph()
            suffix = Path(filename).suffix.lower()
            formats = {".ttl": ["turtle", "n3"], ".nt": ["nt"], ".jsonld": ["json-ld"]}.get(
                suffix, ["xml", "turtle", "n3"]
            )
            last_error = None
            for fmt in formats:
                try:
                    graph.parse(data=file_content, format=fmt)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
            if last_error:
                return ""
            ontology_subjects = list(graph.subjects(RDF.type, OWL.Ontology))
            for subject in ontology_subjects:
                if isinstance(subject, URIRef) and str(subject).strip():
                    return str(subject).strip().rstrip("#/")
            for subject, _, _ in graph:
                if isinstance(subject, URIRef) and str(subject).strip():
                    return str(subject).strip().rsplit("#", 1)[0].rstrip("/")
        except Exception:
            return ""
        return ""

    @classmethod
    def _ontology_dir(cls, ontology_id: str) -> Path:
        token = str(ontology_id or "").strip()
        if not token or token in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]+", token):
            raise ValueError("Invalid ontology_id")
        root = cls.ONTOLOGY_STORAGE_DIR.resolve()
        candidate = (root / token).resolve()
        if root not in candidate.parents:
            raise ValueError("Invalid ontology_id")
        return candidate
    
    @classmethod
    def initialize(cls):
        """Create storage directory if it doesn't exist"""
        cls.ONTOLOGY_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ontology storage initialized at: {cls.ONTOLOGY_STORAGE_DIR}")
    
    @classmethod
    def _materialize_semantic_artifacts(
        cls,
        ontology_dir: Path,
        file_path: Path,
        file_content: bytes,
        filename: str,
        file_type: str,
        generation_type: str,
    ) -> Dict[str, Any]:
        """Generate and persist semantic OWL/SHACL artifacts beside the uploaded source file."""
        result: Dict[str, Any] = {
            "owl_file_path": "",
            "rdf_file_path": "",
            "jsonld_file_path": "",
            "ontology_export_artifacts": [],
            "shacl_file_path": "",
            "shacl_report_path": "",
            "owl_generation_metadata": {},
            "shacl_report": {},
            "semantic_artifacts_status": "not_generated",
        }
        try:
            if file_type == "ontology":
                if file_path.suffix.lower() in {".ttl", ".rdf", ".owl", ".xml"}:
                    result["owl_file_path"] = str(file_path)
                    result["ontology_export_artifacts"] = [{
                        "format": file_path.suffix.lower().lstrip(".") or "source",
                        "path": str(file_path),
                        "source": True,
                    }]
                    result["semantic_artifacts_status"] = "source_registered"
                return result

            if file_type not in {"xsd", "xmi"}:
                return result

            from .owl_generation_service import OWLGenerationService
            from .shacl_service import ShaclValidationService

            ttl_text, owl_metadata = OWLGenerationService.generate_owl(file_content, filename)
            owl_path = ontology_dir / f"{Path(filename).stem}.generated.ttl"
            owl_path.write_text(ttl_text, encoding="utf-8")

            export_artifacts = [{
                "format": "ttl",
                "path": str(owl_path),
                "source": False,
            }]
            try:
                from rdflib import Graph as RDFGraph

                rdf_graph = RDFGraph()
                rdf_graph.parse(data=ttl_text, format="turtle")
                export_specs = (
                    ("rdf", "xml", ontology_dir / f"{Path(filename).stem}.generated.rdf"),
                    ("owl", "pretty-xml", ontology_dir / f"{Path(filename).stem}.generated.owl"),
                    ("jsonld", "json-ld", ontology_dir / f"{Path(filename).stem}.generated.jsonld"),
                )
                for export_format, rdflib_format, export_path in export_specs:
                    serialized = rdf_graph.serialize(format=rdflib_format)
                    export_path.write_text(str(serialized), encoding="utf-8")
                    export_artifacts.append({
                        "format": export_format,
                        "path": str(export_path),
                        "source": False,
                    })
            except Exception as export_exc:
                logger.warning("Ontology export serialization skipped for %s: %s", filename, export_exc)

            shacl_service = ShaclValidationService()
            shacl_ttl = shacl_service.create_default_shapes()
            shacl_path = ontology_dir / f"{Path(filename).stem}.shacl.ttl"
            shacl_path.write_text(shacl_ttl, encoding="utf-8")

            shacl_report = OWLGenerationService.validate_with_shacl(
                ttl_text,
                shacl_shapes=shacl_ttl,
                ontology_context=owl_metadata.get("owlready2"),
            )
            shacl_report_path = ontology_dir / f"{Path(filename).stem}.shacl_report.json"
            shacl_report_path.write_text(json.dumps(shacl_report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

            result.update({
                "owl_file_path": str(owl_path),
                "rdf_file_path": next((a["path"] for a in export_artifacts if a["format"] == "rdf"), ""),
                "jsonld_file_path": next((a["path"] for a in export_artifacts if a["format"] == "jsonld"), ""),
                "ontology_export_artifacts": export_artifacts,
                "shacl_file_path": str(shacl_path),
                "shacl_report_path": str(shacl_report_path),
                "owl_generation_metadata": owl_metadata,
                "shacl_report": shacl_report,
                "semantic_artifacts_status": "generated",
            })
            return result
        except Exception as exc:
            logger.warning("Semantic artifact generation skipped for %s: %s", filename, exc)
            result.update({
                "semantic_artifacts_status": "generation_failed",
                "semantic_artifacts_error": str(exc),
            })
            return result

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
        schema_type: str = "schema",
        source_namespace: str = "",
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
        lock_acquired = False
        try:
            cls._metadata_lock.acquire()
            lock_acquired = True
            cls.initialize()

            user_prefix = str(prefix or "").strip()
            if file_type == "xsd" and file_content:
                try:
                    root = ET.fromstring(file_content)
                    xsd_namespace = str(root.attrib.get("targetNamespace") or "").strip()
                    if xsd_namespace:
                        source_namespace = source_namespace or xsd_namespace
                except Exception as ns_exc:
                    logger.debug("Could not derive XSD targetNamespace for %s: %s", filename, ns_exc)

            if not source_namespace:
                source_namespace = cls._derive_ontology_namespace(file_content, filename, file_type)
            source_namespace = str(source_namespace or "").strip().rstrip("#/")
            derived_prefix = derive_prefix_from_namespace(source_namespace) if source_namespace else "ontology"
            prefix = user_prefix or derived_prefix

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

            # Create ontology subdirectory
            # Normalize prefix to a filesystem-safe token
            safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', str(prefix or '').strip().lower()) or 'ontology'
            ontology_id = f"{safe_prefix}_{uuid.uuid4().hex[:16]}"
            ontology_dir = cls._ontology_dir(ontology_id)
            ontology_dir.mkdir(parents=True, exist_ok=True)

            # Save file
            safe_filename = cls._safe_upload_filename(filename)
            file_path = ontology_dir / safe_filename
            with open(file_path, 'wb') as f:
                f.write(file_content)

            semantic_artifacts = cls._materialize_semantic_artifacts(
                ontology_dir=ontology_dir,
                file_path=file_path,
                file_content=file_content,
                filename=safe_filename,
                file_type=file_type,
                generation_type=generation_type,
            )
            generated_meta = semantic_artifacts.get("owl_generation_metadata") or {}
            if file_type == "xsd" and generated_meta:
                generated_namespace = str(generated_meta.get("target_namespace") or generated_meta.get("base_uri") or "").strip()
                if generated_namespace:
                    source_namespace = generated_namespace.rstrip("#/") if generated_namespace.endswith(("#", "/")) else generated_namespace
            if user_prefix:
                prefix = user_prefix

            ontology_uri = source_namespace or f"urn:depo-ontology:{prefix}"

            # Create metadata with version info
            metadata = {
                'ontology_id': ontology_id,
                'ontology_name': ontology_name,
                'prefix': prefix,
                'ontology_prefix': prefix,
                'namespace': source_namespace or '',
                'ontology_uri': ontology_uri,
                'target_namespace': source_namespace or '',
                'file_type': file_type,
                'generation_type': generation_type,
                'description': description,
                'schema_type': schema_type or 'schema',
                'source_namespace': source_namespace or '',
                'original_filename': safe_filename,
                'stored_filename': safe_filename,
                'file_path': str(file_path),
                'file_size': len(file_content),
                'uploaded_at': datetime.now().isoformat(),
                'status': 'uploaded',
                'version': version,
                'is_latest': True,
                'replaces': replaces,
                'previous_versions': previous_versions,
                **semantic_artifacts,
            }

            # Save metadata (no BOM)
            metadata_path = ontology_dir / 'metadata.json'
            cls._atomic_write_json(metadata_path, metadata)

            # Publish the new version before superseding the previous one so a
            # failed save never removes the last usable registry entry.
            if existing and existing.get('ontology_id') != ontology_id:
                cls._mark_superseded(existing['ontology_id'])

            logger.info(f"Saved ontology {ontology_id} v{version} to {ontology_dir}")
            cls._invalidate_list_cache()

            result = {
                'status': 'success',
                'ontology_id': ontology_id,
                'storage_path': str(file_path),
                'metadata_path': str(metadata_path),
                'metadata': metadata,
                'version': version,
                'is_new_version': existing is not None,
                'replaces': replaces,
            }
            cls._metadata_lock.release()
            lock_acquired = False
            return result

        except Exception as e:
            if lock_acquired:
                cls._metadata_lock.release()
            logger.exception("Error saving ontology file")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    @classmethod
    def get_ontology(cls, ontology_id: str) -> Dict[str, Any]:
        """Retrieve ontology metadata"""
        try:
            metadata_path = cls._ontology_dir(ontology_id) / 'metadata.json'
            
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
    def refresh_semantic_artifacts(cls, ontology_id: str) -> Dict[str, Any]:
        """Backfill generated OWL/SHACL artifacts for an already-registered ontology."""
        try:
            result = cls.get_ontology(ontology_id)
            if result.get('status') != 'success':
                return result
            meta = result['metadata']
            file_path = Path(meta.get('file_path', ''))
            if not file_path.exists():
                return {'status': 'error', 'error': f'Missing ontology source file: {file_path}'}
            ontology_dir = file_path.parent
            semantic_artifacts = cls._materialize_semantic_artifacts(
                ontology_dir=ontology_dir,
                file_path=file_path,
                file_content=file_path.read_bytes(),
                filename=file_path.name,
                file_type=str(meta.get('file_type') or '').strip(),
                generation_type=str(meta.get('generation_type') or '').strip(),
            )
            cls.update_metadata(ontology_id, semantic_artifacts)
            return {
                'status': 'success',
                'ontology_id': ontology_id,
                'semantic_artifacts': semantic_artifacts,
            }
        except Exception as exc:
            logger.exception('Could not refresh semantic artifacts for %s', ontology_id)
            return {'status': 'error', 'error': str(exc)}
    
    @classmethod
    def list_ontologies(cls) -> Dict[str, Any]:
        """List all uploaded ontologies — returns only the latest version of each."""
        try:
            cls.initialize()
            now = time.time()
            if cls._LIST_CACHE_ENABLED and cls._list_cache is not None and (now - cls._list_cache_ts) < cls._LIST_CACHE_TTL_SEC:
                return copy.deepcopy(cls._list_cache)
            
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
            ontologies = normalize_ontology_entries(
                o for o in all_ontologies if o.get('is_latest', True)
            )
            # Strip heavyweight previous_versions array to keep the response small.
            for o in ontologies:
                o.pop('previous_versions', None)

            result = {
                'status': 'success',
                'ontologies': ontologies,
                'count': len(ontologies)
            }
            if cls._LIST_CACHE_ENABLED:
                cls._list_cache = copy.deepcopy(result)
                cls._list_cache_ts = now
            return copy.deepcopy(result)
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

    @staticmethod
    def _availability(node_count: int, relationship_count: int, empty_state: str = "metadata_only") -> str:
        if node_count <= 0:
            return empty_state
        return "available" if relationship_count > 0 else "loaded_empty"

    @staticmethod
    def _registry_index(ontologies: list[dict]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for source_row in normalize_ontology_entries(ontologies):
            row = dict(source_row)
            prefix = str(row.get("prefix") or row.get("ontology_prefix") or row.get("ontology_id") or "").strip()
            if not prefix:
                continue
            row["prefix"] = prefix
            row["ontology_prefix"] = row.get("ontology_prefix") or prefix
            row["source"] = row.get("source") or "registered"
            row.setdefault("node_count", row.get("neo4j_nodes_merged", 0) or 0)
            row.setdefault("relationship_count", row.get("neo4j_relationships_merged", 0) or 0)
            row["availability"] = "metadata_only"
            indexed[prefix.lower()] = row
        return indexed

    @classmethod
    def _enrich_registry_counts(cls, by_prefix: Dict[str, Dict[str, Any]], graph=None) -> None:
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
                row.update({
                    "node_count": node_count,
                    "relationship_count": relationship_count,
                    "availability": cls._availability(node_count, relationship_count),
                })
                row.pop("count_error", None)
            except Exception as exc:
                row["availability"] = "count_failed"
                row["count_error"] = str(exc)

    @staticmethod
    def _neo4j_only_entry(direct: Dict[str, Any]) -> Dict[str, Any] | None:
        prefix = str(direct.get("prefix") or "").strip()
        if not prefix:
            return None
        name = str(direct.get("ontology_name") or prefix).replace(" SPLM", "").replace("_splm", "").strip() or prefix.upper()
        node_count = int(direct.get("node_count") or 0)
        relationship_count = int(direct.get("relationship_count") or 0)
        return {
            "ontology_id": prefix, "ontology_name": name, "name": name,
            "prefix": prefix, "ontology_prefix": prefix,
            "namespace": "", "source_namespace": "", "file_type": "neo4j",
            "generation_type": "direct", "schema_type": "schema", "source": "neo4j",
            "status": "discovered", "node_count": node_count,
            "relationship_count": relationship_count,
            "availability": OntologyUploadManager._availability(node_count, relationship_count, "loaded_empty"),
        }

    @classmethod
    def _merge_neo4j_only_entries(cls, by_prefix: Dict[str, Dict[str, Any]], graph=None) -> None:
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
            entry = cls._neo4j_only_entry(direct)
            if entry and entry["prefix"].lower() not in by_prefix:
                by_prefix[entry["prefix"].lower()] = entry

    @classmethod
    def list_ontologies_with_neo4j_counts(cls, graph=None, include_neo4j_only: bool = True) -> Dict[str, Any]:
        """List registered ontology prefixes with runtime Neo4j counts.

        File metadata is the product registry. Neo4j is used only as the
        configured runtime validation source for node/relationship availability.
        """
        result = cls.list_ontologies()
        if result.get("status") != "success":
            return result

        by_prefix = cls._registry_index(result.get("ontologies", []))
        cls._enrich_registry_counts(by_prefix, graph=graph)

        if include_neo4j_only:
            try:
                cls._merge_neo4j_only_entries(by_prefix, graph=graph)
            except Exception as exc:
                logger.warning("Neo4j ontology prefix discovery failed: %s", exc)

        rows = [normalize_ontology_entry(row) for row in sorted(by_prefix.values(), key=lambda item: str(item.get("prefix") or ""))]
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
            ontology_dir = cls._ontology_dir(ontology_id)
            metadata_path = ontology_dir / 'metadata.json'

            if not metadata_path.exists():
                return {'status': 'error', 'error': f'Ontology not found: {ontology_id}'}

            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                metadata = json.load(f)

            shutil.rmtree(ontology_dir, ignore_errors=False)
            if metadata.get('is_latest', True) and metadata.get('replaces'):
                cls._mark_latest(str(metadata.get('replaces')))
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
            metadata_path = cls._ontology_dir(ontology_id) / 'metadata.json'
            
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
            metadata_path = cls._ontology_dir(ontology_id) / 'metadata.json'
            if not metadata_path.exists():
                return
            with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                meta = json.load(f)
            meta['is_latest'] = False
            cls._atomic_write_json(metadata_path, meta)
            cls._invalidate_list_cache()
        except Exception as e:
            logger.exception("Could not mark %s as superseded", ontology_id)

    @classmethod
    def _mark_latest(cls, ontology_id: str) -> None:
        """Promote a retained previous version after deleting its replacement."""
        try:
            metadata_path = cls._ontology_dir(ontology_id) / 'metadata.json'
            if not metadata_path.exists():
                return
            with cls._metadata_lock:
                with open(metadata_path, 'r', encoding='utf-8-sig') as handle:
                    meta = json.load(handle)
                meta['is_latest'] = True
                cls._atomic_write_json(metadata_path, meta)
            cls._invalidate_list_cache()
        except Exception:
            logger.exception("Could not promote %s as latest", ontology_id)

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
        if file_type in {"xsd", "xmi"}:
            from rdflib import Graph as RDFGraph
            from .owl_generation_service import OWLGenerationService
            ttl, metadata = OWLGenerationService.generate_owl(file_content, filename)
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
    def _parse_source_rows(cls, file_type: str, file_content: bytes, file_path: Path) -> tuple[list, list, list]:
        """Parse a stored source without performing metadata or Neo4j writes."""
        rows: list = []
        xmi_relationships: list = []
        extracted_relationships: list = []
        if file_type == "xsd":
            try:
                from .ap239_parser import parse_ap239_xsd
                rows, _ = parse_ap239_xsd(file_content)
            except Exception as exc:
                logger.warning("AP239 parse fallback: %s", exc)
                from .unified_data_import import FileFormatDetector
                rows, _ = FileFormatDetector.parse_xsd(file_content)
        elif file_type == "xmi":
            from .unified_data_import import FileFormatDetector
            rows, stats = FileFormatDetector.parse_xmi(file_content)
            xmi_relationships = list((stats or {}).get("_xmi_relationships", []) or [])
        elif file_type == "ontology":
            from .unified_data_import import FileFormatDetector
            rows, _ = FileFormatDetector.parse_rdf(file_content, file_path.name)
        elif file_type == "3dxml":
            from .threedxml_ontology_extractor import ThreeDXMLExtractor
            with tempfile.TemporaryDirectory(prefix="threedxml_") as temp_dir:
                temp_file_path = Path(temp_dir) / file_path.name
                temp_file_path.write_bytes(file_content)
                extractor = ThreeDXMLExtractor(temp_dir)
                extracted = extractor.extract()
                rows = list((extracted or {}).get("entities", {}).values())
                extracted_relationships = list(extractor.relationships or [])
        else:
            raise ValueError(f"Unsupported file type for Neo4j push: {file_type}")
        return list(rows or []), xmi_relationships, extracted_relationships

    @staticmethod
    def _normalize_source_rows(rows: list, prefix: str) -> tuple[list[dict], list[dict]]:
        """Normalize parsed entities and derive deduplicated class properties."""
        skip_keys = {
            "name", "concept_type", "entity_type", "namespace",
            "type", "id", "label", "local_name",
        }
        valid_rows: list[dict] = []
        property_pairs: set[tuple[str, str]] = set()

        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                raw_type = row.get("type") or row.get("label")
                name = str(raw_type).split(":")[-1].strip() if raw_type else ""
            if not name:
                name = str(row.get("local_name") or row.get("id") or "").strip()
            if not name:
                continue

            valid_rows.append({
                "name": name,
                "concept_type": str(row.get("concept_type") or row.get("entity_type") or row.get("type") or "Unknown"),
                "namespace": str(row.get("namespace", prefix)),
            })
            attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            property_pairs.update((name, str(key)) for key in attributes if str(key).strip())
            for key, value in row.items():
                if key in {"attributes", "metadata", "relationships"} or key in skip_keys:
                    continue
                if value is not None and str(value).strip():
                    property_pairs.add((name, str(key)))

        property_rows = [
            {"class_name": class_name, "prop_name": prop_name}
            for class_name, prop_name in sorted(property_pairs)
        ]
        return valid_rows, property_rows

    @staticmethod
    def _relationship_groups(valid_rows: list[dict], xmi_relationships: list, extracted_relationships: list) -> dict[str, list[dict]]:
        """Validate, sanitize, and deduplicate parsed class relationships."""
        class_names = {row["name"] for row in valid_rows}
        grouped: dict[str, set[tuple[str, str]]] = {}

        def add(source: Any, target: Any, relation_type: Any) -> None:
            source_name = str(source or "").strip()
            target_name = str(target or "").strip()
            if source_name not in class_names or target_name not in class_names:
                return
            safe_type = re.sub(r"[^A-Za-z0-9_]", "_", str(relation_type or "RELATED_TO").strip()).upper()
            safe_type = safe_type or "RELATED_TO"
            grouped.setdefault(safe_type, set()).add((source_name, target_name))

        for relationship in xmi_relationships:
            if isinstance(relationship, dict):
                add(relationship.get("from_label"), relationship.get("to_label"), relationship.get("type"))
        for relationship in extracted_relationships:
            add(
                getattr(relationship, "source", None),
                getattr(relationship, "target", None),
                getattr(relationship, "relation_type", None),
            )

        return {
            relation_type: [
                {"from_label": source, "to_label": target}
                for source, target in sorted(pairs)
            ]
            for relation_type, pairs in sorted(grouped.items())
        }

    @staticmethod
    def _merge_relationship_groups(graph, prefix: str, groups: dict[str, list[dict]]) -> int:
        total = 0
        for relation_type, rows in groups.items():
            cypher = f"""
UNWIND $rows AS row
MATCH (a:OntologyClass {{name: row.from_label, prefix: $prefix}})
MATCH (b:OntologyClass {{name: row.to_label, prefix: $prefix}})
MERGE (a)-[:{relation_type}]->(b)
"""
            graph.query(cypher, params={"rows": rows, "prefix": prefix})
            total += len(rows)
        return total

    @staticmethod
    def _merge_property_rows(graph, prefix: str, property_rows: list[dict], batch_size: int = 500) -> int:
        if not property_rows:
            return 0
        cypher = """
UNWIND $rows AS row
MATCH (c:OntologyClass {name: row.class_name, prefix: $prefix})
MERGE (p:OntologyProperty {name: row.prop_name, prefix: $prefix})
ON CREATE SET p.ontology_prefix = $prefix
ON MATCH SET p.ontology_prefix = $prefix
MERGE (p)-[:PROPERTY_OF]->(c)
"""
        try:
            for offset in range(0, len(property_rows), batch_size):
                graph.query(cypher, params={
                    "rows": property_rows[offset:offset + batch_size],
                    "prefix": prefix,
                })
            return len(property_rows)
        except Exception as exc:
            logger.warning("OntologyProperty merge skipped: %s", exc)
            return 0

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

            if determined_schema_type == "schema" and file_type in {"xsd", "xmi", "ontology"}:
                owl_file_path = str(meta.get("owl_file_path") or "").strip()
                owl_metadata = dict(meta.get("owl_generation_metadata") or {})
                ttl_text = ""
                if owl_file_path and Path(owl_file_path).exists():
                    ttl_text = Path(owl_file_path).read_text(encoding="utf-8")
                    rdf_graph = cls._parse_rdf_content(ttl_text.encode("utf-8"), Path(owl_file_path).name)
                else:
                    rdf_graph, ttl_text, owl_metadata = cls._generate_rdf_for_source(
                        file_content=file_content,
                        filename=file_path.name,
                        file_type=file_type,
                        generation_type=meta.get("generation_type", ""),
                    )
                    if file_type in {"xsd", "xmi"}:
                        owl_path = file_path.with_suffix(".generated.ttl")
                        owl_path.write_text(ttl_text, encoding="utf-8")
                        owl_file_path = str(owl_path)
                    elif file_path.suffix.lower() in {".ttl", ".rdf", ".owl", ".xml"}:
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

            try:
                rows, xmi_relationships, extracted_relationships = cls._parse_source_rows(
                    file_type, file_content, file_path
                )
            except ValueError as exc:
                return {"status": "error", "error": str(exc)}

            valid_rows, property_rows = cls._normalize_source_rows(rows, prefix)

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

            relationship_total = 0
            if determined_schema_type == "schema":
                relationship_groups = cls._relationship_groups(
                    valid_rows, xmi_relationships, extracted_relationships
                )
                relationship_total = cls._merge_relationship_groups(graph, prefix, relationship_groups)
                if relationship_total:
                    logger.info(
                        "Neo4j push: %s OntologyClass relationships merged for %s",
                        relationship_total,
                        ontology_id,
                    )

            property_total = cls._merge_property_rows(graph, prefix, property_rows)
            if property_total:
                logger.info(
                    "Neo4j push: %s OntologyProperty links merged for %s",
                    property_total,
                    ontology_id,
                )

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
            metadata_path = cls._ontology_dir(ontology_id) / 'metadata.json'
            if not metadata_path.exists():
                return
            with cls._metadata_lock:
                with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                    meta = json.load(f)
                meta['status'] = status
                if extra:
                    meta.update(extra)
                cls._atomic_write_json(metadata_path, meta)
            cls._invalidate_list_cache()
        except Exception as e:
            logger.exception("Could not update status for %s", ontology_id)

    @classmethod
    def update_metadata(cls, ontology_id: str, fields: Dict[str, Any]) -> None:
        """Merge arbitrary fields into an ontology's metadata.json (public helper)."""
        try:
            metadata_path = cls._ontology_dir(ontology_id) / 'metadata.json'
            if not metadata_path.exists():
                return
            with cls._metadata_lock:
                with open(metadata_path, 'r', encoding='utf-8-sig') as f:
                    meta = json.load(f)
                meta.update(fields)
                cls._atomic_write_json(metadata_path, meta)
            cls._invalidate_list_cache()
        except Exception as e:
            logger.exception("Could not update metadata for %s", ontology_id)

