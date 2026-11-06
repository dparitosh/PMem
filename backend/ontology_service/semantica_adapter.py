"""Required Semantica implementation for the DEPO ontology service."""
from __future__ import annotations

import tempfile
import dataclasses
import json
import uuid
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from backend.mesh_store import PostgresRegistry

try:
    from semantica import __version__ as SEMANTICA_VERSION
    from semantica.ontology import OntologyEngine
    from semantica.ontology import NamespaceManager
    from semantica.reasoning import Reasoner
except ModuleNotFoundError as exc:  # pragma: no cover - startup guard
    raise RuntimeError(
        "Semantica is required for the ontology service. Install backend/requirements.txt before starting DEPO."
    ) from exc


def _result_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {"value": value}


def _json_value(value: Any) -> Any:
    """Convert Semantica model values into the JSONB control-plane contract."""
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump())
    if dataclasses.is_dataclass(value):
        return _json_value(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class SemanticaAdapter:
    """One required engine for ontology lifecycle, SHACL and quality checks."""

    def capabilities(self) -> dict[str, Any]:
        from .owl_dl import capabilities as dl_capabilities
        dl = dl_capabilities()
        return {
            "provider": "Semantica", "version": SEMANTICA_VERSION, "available": True, "mode": "required",
            "rdf_backend": "rdflib",
            "validation_scope": "structural_and_shacl",
            "owl_dl_consistency_supported": dl['available'],
            "semantica_builtin_owl_dl_supported": False,
            "external_owl_dl": dl,
            "embedded_foundation": "IDO 4.2 + DEPO business core 1.0.0",
            "capabilities": ["knowledge_graph_to_ontology", "class_and_property_inference", "ontology_validation",
                             "shacl_generation_and_graph_validation", "owl_rdf_jsonld_export", "namespace_management",
                             "ontology_evaluation", "ontology_alignment", "llm_bootstrap_when_configured"],
        }

    @staticmethod
    def _engine(base_uri: str) -> OntologyEngine:
        return OntologyEngine(base_uri=base_uri.rstrip("#/") + "/", min_occurrences=1)

    def generate(self, *, data: dict[str, Any], name: str, base_uri: str, persist: bool = False) -> dict[str, Any]:
        engine = self._engine(base_uri)
        ontology = engine.from_data(data, name=name, build_hierarchy=True, validate=True)
        validation = _result_dict(engine.validate(ontology))
        evaluation = _result_dict(engine.evaluate(ontology))
        with tempfile.TemporaryDirectory(prefix="depo_semantica_") as directory:
            root = Path(directory)
            ttl_path, owl_path, jsonld_path, shacl_path = root / "ontology.ttl", root / "ontology.owl", root / "ontology.jsonld", root / "shapes.ttl"
            engine.export_owl(ontology, str(ttl_path), format="turtle")
            engine.export_owl(ontology, str(owl_path), format="xml")
            engine.export_owl(ontology, str(jsonld_path), format="json-ld")
            engine.export_shacl(ontology, str(shacl_path), format="turtle")
            # A review preview is intentionally ephemeral.  Persisting it here
            # would make an unapproved XSD upload a durable ontology version.
            version_id = self.workspace.store(ontology) if persist else None
            return {"ontology": ontology, "version_id": version_id, "validation": validation, "evaluation": evaluation,
                    "artifacts": {"turtle": ttl_path.read_bytes(), "owl_xml": owl_path.read_bytes(),
                                  "json_ld": jsonld_path.read_bytes(), "shacl": shacl_path.read_bytes()}}

    def generate_from_xsd_inspection(self, inspection: dict[str, Any], prefix: str) -> tuple[bytes, dict[str, Any]]:
        """Project declared XSD semantics without inferring duplicate schema terms."""
        from backend.qif.rdf_projection import project_schema_ontology
        return project_schema_ontology(inspection, prefix)

    def __init__(self) -> None:
        self.workspace = SemanticWorkspace()


class SemanticWorkspace:
    """PostgreSQL-backed semantic control plane for versions and cross-ontology links."""
    _STATE_KEY = "workspace"
    _ONTOLOGY_PREFIX = "ontology:"
    _ALIGNMENT_PREFIX = "alignment:"

    def __init__(self, root: Path | None = None, registry: Any | None = None) -> None:
        self.engine = OntologyEngine(base_uri="https://depo.local/ontology/", min_occurrences=1)
        self.namespaces = NamespaceManager(base_uri="https://depo.local/ontology/")
        # root remains a compatibility argument for callers that use it as a
        # Semantica artifact root; persistent control-plane state is PostgreSQL.
        self.root = root or Path(os.getenv("ONTOLOGY_SERVICE_STORAGE") or Path(__file__).resolve().parents[2] / "data" / "ontology_service")
        self.registry = registry or PostgresRegistry("ontology_semantic_workspace")
        self.legacy_workspace_path = self.root / "semantic_workspace.json"
        self.ontologies: dict[str, dict[str, Any]] = {}
        self.alignments: list[dict[str, str]] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._migrate_legacy_state()
        self._refresh()
        self._loaded = True

    def _migrate_legacy_state(self) -> None:
        state = self.registry.get(self._STATE_KEY)
        if state is None and self.legacy_workspace_path.is_file():
            try:
                candidate = json.loads(self.legacy_workspace_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Legacy semantic workspace is unreadable: {exc}") from exc
            if isinstance(candidate, dict):
                self.registry.put(self._STATE_KEY, _json_value(candidate))
                state = candidate
        if state is not None and not isinstance(state, dict):
            raise RuntimeError("Semantic workspace has an invalid structure")
        if not isinstance(state, dict) or state.get("migrated"):
            return
        values: dict[str, dict[str, Any]] = {}
        for version_id, ontology in state.get("ontologies", {}).items():
            if isinstance(ontology, dict):
                values[f"{self._ONTOLOGY_PREFIX}{version_id}"] = _json_value(ontology)
        for index, alignment in enumerate(state.get("alignments", [])):
            if isinstance(alignment, dict):
                values[f"{self._ALIGNMENT_PREFIX}{uuid.uuid4().hex}"] = _json_value(alignment)
        if values:
            self.registry.put_many(values)
        self.registry.put(self._STATE_KEY, {"migrated": True})

    def _refresh(self) -> None:
        values = self.registry.all()
        self.ontologies = {
            key.removeprefix(self._ONTOLOGY_PREFIX): value
            for key, value in values.items()
            if key.startswith(self._ONTOLOGY_PREFIX) and isinstance(value, dict)
        }
        self.alignments = [
            value for key, value in values.items()
            if key.startswith(self._ALIGNMENT_PREFIX) and isinstance(value, dict)
        ]

    def store(self, ontology: dict[str, Any]) -> str:
        self._ensure_loaded()
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", str(ontology.get("name", "ontology"))).strip("-").lower() or "ontology"
        version_id = f"{name}:{uuid.uuid4().hex}"
        self.registry.put(f"{self._ONTOLOGY_PREFIX}{version_id}", _json_value(ontology))
        self._refresh()
        return version_id

    def get(self, version_id: str) -> dict[str, Any]:
        self._ensure_loaded()
        ontology = self.registry.get(f"{self._ONTOLOGY_PREFIX}{version_id}")
        if ontology is None:
            raise KeyError(f"Unknown ontology version '{version_id}'")
        return ontology

    def validate_graph(self, *, data_graph: str, ontology: dict[str, Any]) -> dict[str, Any]:
        return _result_dict(self.engine.validate_graph(data_graph, ontology=ontology, data_graph_format="turtle"))

    def reason(self, *, facts: list[Any], rules: list[str]) -> list[dict[str, Any]]:
        results = Reasoner().infer_with_results(facts, rules)
        return [_result_dict(item) for item in results]

    def align(self, *, source_uri: str, target_uri: str, predicate: str) -> dict[str, str]:
        self._ensure_loaded()
        record = {
            "source_uri": source_uri, "target_uri": target_uri, "predicate": predicate,
            "storage": "postgres", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.registry.put(f"{self._ALIGNMENT_PREFIX}{uuid.uuid4().hex}", record)
        self._refresh()
        return record

    def list_alignments(self) -> list[dict[str, str]]:
        self._ensure_loaded()
        return list(self.alignments)


semantica = SemanticaAdapter()
