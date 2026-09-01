"""Required Semantica implementation for the DEPO ontology service."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, XSD
from semantica import __version__ as SEMANTICA_VERSION
from semantica.ontology import OntologyEngine


def _result_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {"value": value}


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

    def generate(self, *, data: dict[str, Any], name: str, base_uri: str) -> dict[str, Any]:
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
            return {"ontology": ontology, "validation": validation, "evaluation": evaluation,
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
        generated = self.generate(data={"entities": entities, "relationships": relationships}, name=f"{prefix} QIF ontology", base_uri=namespace)
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


semantica = SemanticaAdapter()
