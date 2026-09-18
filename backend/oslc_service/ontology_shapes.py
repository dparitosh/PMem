"""Draft-aware OSLC shape projection from retained RDF, never graph publication."""
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL
from backend.ontology_service.catalog import OntologyCatalog


def catalog_shape(identifier: str, base_url: str) -> dict:
    record, content = OntologyCatalog().read_artifact(identifier)
    suffix = record["original_filename"].lower().rsplit(".", 1)[-1]
    formats = {"ttl": "turtle", "rdf": "xml", "owl": "xml", "jsonld": "json-ld"}
    graph = Graph().parse(data=content, format=formats.get(suffix, "turtle"))
    properties = sorted({str(subject) for kind in (OWL.ObjectProperty, OWL.DatatypeProperty)
                         for subject in graph.subjects(RDF.type, kind) if isinstance(subject, URIRef)})
    return {"uri": f"{base_url}/oslc/shapes/{identifier}", "type": "oslc:ResourceShape",
            "ontology_id": identifier, "lifecycle_status": record.get("lifecycle_status"),
            "semantic_completeness": record.get("semantic_completeness", "unverified"),
            "validation_scope": "OWL declaration projection; not SHACL execution or approval",
            "describes": sorted(str(s) for s in graph.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)),
            "properties": [{"propertyDefinition": iri, "name": str(graph.value(URIRef(iri), RDFS.label) or iri),
                            "readOnly": True} for iri in properties]}
