"""Self-contained IIF coded tool: ontology_inspect."""

from pathlib import Path
from typing import Any
from llama_index.core.tools import FunctionTool

_FORMATS = {".owl": "xml", ".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".nt": "nt", ".n3": "n3", ".jsonld": "json-ld"}


def _load(path_value: str):
    from rdflib import Graph
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    if path.suffix.lower() not in _FORMATS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")
    formats = [_FORMATS[path.suffix.lower()]]
    if path.suffix.lower() in {".owl", ".rdf", ".xml"}:
        formats.extend(value for value in ("turtle", "n3", "nt", "json-ld") if value not in formats)
    errors = []
    for rdf_format in formats:
        graph = Graph()
        try:
            graph.parse(path, format=rdf_format)
            return path, graph
        except Exception as exc:
            errors.append(exc)
    raise ValueError(f"Could not parse {path.name}; attempted: {', '.join(formats)}") from errors[-1]


def run_ontology_inspect(path: str) -> dict[str, Any]:
    """Inspect asserted ontology structure locally with RDFLib."""
    from rdflib import BNode, OWL, RDF, RDFS
    ontology_path, graph = _load(path)
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if object_type in classes and not isinstance(subject, BNode) and subject not in classes and subject not in object_properties and subject not in datatype_properties and subject not in annotation_properties:
            individuals.add(subject)
    return {
        "path": str(ontology_path), "engine": "rdflib", "scope": "asserted_graph",
        "triples": len(graph), "classes": len(classes), "object_properties": len(object_properties),
        "datatype_properties": len(datatype_properties), "annotation_properties": len(annotation_properties),
        "individuals": len(individuals),
        "subclass_edges": sum(1 for _ in graph.triples((None, RDFS.subClassOf, None))),
        "domain_edges": sum(1 for _ in graph.triples((None, RDFS.domain, None))),
        "range_edges": sum(1 for _ in graph.triples((None, RDFS.range, None))),
        "ontology_iris": sorted(str(value) for value in graph.subjects(RDF.type, OWL.Ontology)),
    }


ontology_inspect = FunctionTool.from_defaults(name="ontology_inspect", fn=run_ontology_inspect)
__all__ = ["ontology_inspect"]
