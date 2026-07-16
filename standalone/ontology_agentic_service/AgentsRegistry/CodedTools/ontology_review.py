"""Self-contained IIF coded tool: ontology_review."""

from pathlib import Path
from typing import Any, Literal
from llama_index.core.tools import FunctionTool

_FORMATS = {".owl": "xml", ".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".nt": "nt", ".n3": "n3", ".jsonld": "json-ld"}


def _summary(path_value: str) -> dict[str, Any]:
    from rdflib import BNode, Graph, OWL, RDF, RDFS
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    if path.suffix.lower() not in _FORMATS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")
    formats = [_FORMATS[path.suffix.lower()]]
    if path.suffix.lower() in {".owl", ".rdf", ".xml"}:
        formats.extend(value for value in ("turtle", "n3", "nt", "json-ld") if value not in formats)
    graph = None
    errors = []
    for rdf_format in formats:
        candidate = Graph()
        try:
            candidate.parse(path, format=rdf_format)
            graph = candidate
            break
        except Exception as exc:
            errors.append(exc)
    if graph is None:
        raise ValueError(f"Could not parse {path.name}; attempted: {', '.join(formats)}") from errors[-1]
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if object_type in classes and not isinstance(subject, BNode) and subject not in classes and subject not in object_properties and subject not in datatype_properties and subject not in annotation_properties:
            individuals.add(subject)
    return {
        "path": str(path), "engine": "rdflib", "scope": "asserted_graph", "triples": len(graph),
        "classes": len(classes), "object_properties": len(object_properties),
        "datatype_properties": len(datatype_properties), "annotation_properties": len(annotation_properties),
        "individuals": len(individuals),
        "subclass_edges": sum(1 for _ in graph.triples((None, RDFS.subClassOf, None))),
        "domain_edges": sum(1 for _ in graph.triples((None, RDFS.domain, None))),
        "range_edges": sum(1 for _ in graph.triples((None, RDFS.range, None))),
        "ontology_iris": sorted(str(value) for value in graph.subjects(RDF.type, OWL.Ontology)),
    }


def run_ontology_review(path: str, profile: Literal["schema", "schema_and_instances"] = "schema") -> dict[str, Any]:
    """Review asserted ontology structure under an explicit profile."""
    if profile not in {"schema", "schema_and_instances"}:
        raise ValueError("profile must be 'schema' or 'schema_and_instances'")
    summary = _summary(path)
    issues = []
    if summary["classes"] == 0:
        issues.append({"code": "NO_CLASSES", "severity": "high", "message": "No OWL classes were detected."})
    if summary["object_properties"] + summary["datatype_properties"] == 0:
        issues.append({"code": "NO_PROPERTIES", "severity": "high", "message": "No object or datatype properties were detected."})
    if profile == "schema_and_instances" and summary["individuals"] == 0:
        issues.append({"code": "NO_INDIVIDUALS", "severity": "low", "message": "No individuals were detected."})
    observations = []
    if summary["subclass_edges"] == 0:
        observations.append("No asserted subclass hierarchy was detected.")
    if summary["domain_edges"] == 0 or summary["range_edges"] == 0:
        observations.append("Some properties may not declare asserted domain/range axioms.")
    return {"status": "ok" if not issues else "review_required", "profile": profile, "summary": summary, "issues": issues, "observations": observations}


ontology_review = FunctionTool.from_defaults(name="ontology_review", fn=run_ontology_review)
__all__ = ["ontology_review"]
