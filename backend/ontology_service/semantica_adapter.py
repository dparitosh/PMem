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
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, XSD
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
        return {
            "provider": "Semantica", "version": SEMANTICA_VERSION, "available": True, "mode": "required",
            "capabilities": ["knowledge_graph_to_ontology", "class_and_property_inference", "ontology_validation",
                             "shacl_generation_and_graph_validation", "owl_rdf_jsonld_export", "namespace_management",
                             "ontology_evaluation", "ontology_alignment", "llm_bootstrap_when_configured"],
        }

    @staticmethod
    def _engine(base_uri: str) -> OntologyEngine:
        return OntologyEngine(base_uri=base_uri.rstrip("#/") + "/", min_occurrences=1)

    def generate(self, *, data: dict[str, Any], name: str, base_uri: str, persist: bool = True) -> dict[str, Any]:
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
        """Generate QIF ontology through Semantica while retaining XSD hierarchy."""
        namespace = f"https://depo.local/ontology/{quote(prefix)}"
        terms = inspection["terms"]
        class_terms = [term for term in terms if term.kind in {"complex_type", "simple_type", "element"}]
        known_names = {term.name for term in class_terms}
        entities = [{"id": f"{term.kind}:{term.name}", "type": term.name, "name": term.name,
                     "source_file": term.source, "schema_namespace": term.namespace or "", "documentation": term.documentation or ""}
                    for term in class_terms]
        relationships = [{"source": term.name, "target": term.base, "type": "extends"}
                         for term in class_terms if term.base in known_names]
        generated = self.generate(
            data={"entities": entities, "relationships": relationships},
            name=f"{prefix} QIF ontology", base_uri=namespace, persist=False,
        )
        graph = Graph()
        graph.parse(data=generated["artifacts"]["turtle"], format="turtle")
        depo = Namespace(namespace.rstrip("/") + "#")
        graph.bind(prefix, depo)
        ontology_uri = URIRef(namespace)
        graph.set((ontology_uri, RDF.type, OWL.Ontology))
        graph.set((ontology_uri, RDFS.label, Literal(f"{prefix} consolidated QIF ontology")))
        class_uris = {term.name: depo[quote(term.name, safe="")] for term in class_terms}
        for term in class_terms:
            uri = class_uris[term.name]
            graph.add((uri, RDF.type, OWL.Class)); graph.set((uri, RDFS.label, Literal(term.name)))
            graph.set((uri, depo.sourceFile, Literal(term.source)))
            if term.namespace: graph.set((uri, depo.schemaNamespace, Literal(term.namespace)))
            if term.documentation: graph.set((uri, RDFS.comment, Literal(term.documentation)))
            parent = term.base if term.base in class_uris else term.value_type if term.kind == "element" and term.value_type in class_uris and term.value_type != term.name else ""
            if parent: graph.add((uri, RDFS.subClassOf, class_uris[parent]))
        for term in (term for term in terms if term.kind == "property"):
            uri = depo[f"property/{quote(term.base or 'global', safe='')}/{quote(term.name, safe='')}" ]
            graph.add((uri, RDF.type, OWL.DatatypeProperty)); graph.set((uri, RDFS.label, Literal(term.name)))
            graph.set((uri, depo.sourceFile, Literal(term.source)))
            if term.base in class_uris: graph.add((uri, RDFS.domain, class_uris[term.base]))
            if term.value_type in class_uris:
                graph.add((uri, RDF.type, OWL.ObjectProperty)); graph.add((uri, RDFS.range, class_uris[term.value_type]))
            else: graph.add((uri, RDFS.range, getattr(XSD, term.value_type, XSD.string) if term.value_type else XSD.string))
            graph.add((uri, depo.minOccurs, Literal(term.min_occurs or "1"))); graph.add((uri, depo.maxOccurs, Literal(term.max_occurs or "1")))
        artifact = graph.serialize(format="turtle")
        summary = {"engine": "Semantica", "engine_version": SEMANTICA_VERSION,
                   "files_processed": len(inspection["source_files"]), "terms_created": len(terms),
                   "classes_created": len(class_terms), "properties_created": sum(term.kind == "property" for term in terms),
                   "references_found": len(inspection["references"]), "parse_errors": inspection["errors"],
                   "validation": generated["validation"], "evaluation": generated["evaluation"]}
        return (artifact.encode("utf-8") if isinstance(artifact, str) else artifact), summary

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
