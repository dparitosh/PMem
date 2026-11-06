"""
3DXML ontology import service aligned with the shared ontology registry flow.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

from .ontology_upload_manager import OntologyUploadManager
from .threedxml_ontology_extractor import ThreeDXMLExtractor

logger = logging.getLogger(__name__)

DEFAULT_3DXML_PREFIX = "ds3dx"
MAX_3DXML_SIZE = 500 * 1024 * 1024


class ThreeDXMLImportService:
    """Thin orchestration layer for 3DXML uploads, extraction, and status lookup."""

    @staticmethod
    def _safe_filename(filename: str) -> str:
        safe_name = Path(filename or "").name
        if not safe_name:
            raise ValueError("File must have a name")
        return safe_name

    @staticmethod
    def supported_formats() -> Dict[str, Any]:
        return {
            "status": "success",
            "formats": [
                {
                    "format": "3DXML",
                    "extension": ".3dxml",
                    "description": "3DEXPERIENCE CAD product structures",
                },
                {
                    "format": "SPLM_SCHEMA",
                    "extension": "folder structure",
                    "description": "SPLM schema with Business/Objects/Relationships folders",
                },
            ],
        }

    @staticmethod
    def validate_upload(filename: str, file_content: bytes) -> None:
        safe_name = ThreeDXMLImportService._safe_filename(filename)
        if not safe_name.lower().endswith(".3dxml"):
            raise ValueError("File must have .3dxml extension")
        if not file_content:
            raise ValueError("File is empty")
        if len(file_content) > MAX_3DXML_SIZE:
            raise ValueError("File too large. Maximum size: 500 MB")

    @staticmethod
    def summarize(filename: str, file_content: bytes) -> Dict[str, Any]:
        safe_name = ThreeDXMLImportService._safe_filename(filename)
        with tempfile.TemporaryDirectory(prefix="threedxml_extract_") as temp_dir:
            temp_file = Path(temp_dir) / safe_name
            temp_file.write_bytes(file_content)
            extractor = ThreeDXMLExtractor(temp_dir)
            extractor.extract()
            return {
                "entities_extracted": len(extractor.entities),
                "relationships_extracted": len(extractor.relationships),
                "entity_types": sorted(list(extractor.entity_types)),
            }

    @classmethod
    def register_upload(
        cls,
        filename: str,
        file_content: bytes,
        ontology_name: str,
        prefix: str = DEFAULT_3DXML_PREFIX,
        load_to_neo4j: bool = True,
    ) -> Dict[str, Any]:
        cls.validate_upload(filename, file_content)
        safe_name = cls._safe_filename(filename)
        summary = cls.summarize(filename, file_content)

        save_result = OntologyUploadManager.save_ontology_file(
            file_content=file_content,
            filename=safe_name,
            ontology_name=ontology_name,
            prefix=prefix,
            file_type="3dxml",
            generation_type="as_is",
            description="3DXML extracted ontology",
            schema_type="schema",
        )
        if save_result.get("status") != "success":
            raise RuntimeError(save_result.get("error") or "Could not save 3DXML upload")

        ontology_id = save_result["ontology_id"]
        OntologyUploadManager.update_metadata(
            ontology_id,
            {
                "extracted_entities": summary["entities_extracted"],
                "extracted_relationships": summary["relationships_extracted"],
                "entity_types": summary["entity_types"],
                "status": "uploaded" if load_to_neo4j else "extracted",
            },
        )

        return {
            "ontology_id": ontology_id,
            "prefix": prefix,
            "load_to_neo4j": load_to_neo4j,
            **summary,
        }

    @staticmethod
    def push_to_neo4j(ontology_id: str) -> Dict[str, Any]:
        try:
            from ..core.graph import graph as neo4j_graph
        except Exception:
            from backend.core.graph import graph as neo4j_graph

        result = OntologyUploadManager.push_to_neo4j(
            ontology_id=ontology_id,
            graph=neo4j_graph,
            schema_type="schema",
        )
        if result.get("status") != "success":
            OntologyUploadManager.update_metadata(
                ontology_id,
                {
                    "status": "failed",
                    "error": result.get("error") or "Neo4j push failed",
                },
            )
        return result

    @staticmethod
    def get_status(task_id: str) -> Dict[str, Any]:
        meta_result = OntologyUploadManager.get_ontology(task_id)
        if meta_result.get("status") != "success":
            raise FileNotFoundError(f"Task {task_id} not found")

        metadata = meta_result.get("metadata") or {}
        internal_status = str(metadata.get("status") or "uploaded")
        status_map = {
            "uploaded": ("processing", 0.25),
            "queued": ("processing", 0.4),
            "processing": ("processing", 0.7),
            "extracted": ("completed", 1.0),
            "pushed_to_neo4j": ("completed", 1.0),
            "failed": ("failed", 0.0),
        }
        public_status, progress = status_map.get(internal_status, ("processing", 0.5))
        return {
            "task_id": task_id,
            "status": public_status,
            "progress": progress,
            "ontology_id": metadata.get("ontology_id", task_id),
            "prefix": metadata.get("prefix") or metadata.get("ontology_prefix"),
            "entities_extracted": metadata.get("extracted_entities"),
            "relationships_extracted": metadata.get("extracted_relationships"),
            "entity_types": metadata.get("entity_types") or [],
            "error": metadata.get("error"),
        }
