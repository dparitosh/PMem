"""Fail-closed syntax, SHACL and bounded OWL consistency checks."""
from pathlib import Path


def validate_semantic_artifact(metadata):
    from backend.ontology_service.catalog import OntologyCatalog
    from backend.Services.shacl_service import ShaclValidationService
    from rdflib import Graph
    from rdflib.namespace import OWL, RDF
    from pyshacl import validate
    from backend.depo_platform.upload_limits import ontology_upload_limit

    path = Path(metadata.get("owl_file_path") or metadata.get("file_path") or metadata.get("artifact_path") or "")
    if not path.is_file():
        raise ValueError("A retained RDF/OWL artifact is required for semantic validation")
    limit = ontology_upload_limit()
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Ontology artifact exceeds the validation size limit")
    parsed = OntologyCatalog._parse_ontology(content, path.name)
    graph = Graph().parse(data=content, format=parsed["rdf_format"])
    shape_path = metadata.get("shacl_file_path")
    shape_id = (metadata.get("engineering_artifacts") or {}).get("shacl")
    shape_source = "retained" if shape_path or shape_id else "default"
    if shape_id:
        from backend.artifact_store import ArtifactStore
        shape_metadata, shape_path = ArtifactStore().resolve(shape_id)
    if shape_path:
        with Path(shape_path).open("rb") as stream:
            shapes_content = stream.read(limit + 1)
        if len(shapes_content) > limit:
            raise ValueError("SHACL artifact exceeds the validation size limit")
        shape_format = OntologyCatalog._parse_ontology(shapes_content, shape_metadata.get("filename", "shapes.ttl") if shape_id else Path(shape_path).name)
        shapes = Graph().parse(data=shapes_content, format=shape_format["rdf_format"])
    else:
        shapes = Graph().parse(data=ShaclValidationService().create_default_shapes(), format="turtle")
    conforms, _, report = validate(graph, shacl_graph=shapes, inference="owlrl", inplace=True,
                                  allow_infos=False, allow_warnings=False)
    if not isinstance(conforms, bool):
        raise ValueError("SHACL validator did not return a conformance result")
    inconsistent = set(graph.subjects(RDF.type, OWL.Nothing))
    for left, right in graph.subject_objects(OWL.disjointWith):
        inconsistent.update(set(graph.subjects(RDF.type, left)) & set(graph.subjects(RDF.type, right)))
    return {"syntax": {"status": "passed", **parsed},
            "shacl": {"conforms": conforms, "report": str(report)[:20000], "shape_source": shape_source, "shape_artifact_id": shape_id, "scope": metadata.get("shacl_scope") or "Default ontology checks; complete XSD instance validation is not established"},
            "consistency": {"status": "failed" if inconsistent else "passed", "conflicting_individuals": len(inconsistent),
                            "scope": "OWL-RL inferred disjoint-class membership and owl:Nothing; full OWL DL consistency is not established"}}
