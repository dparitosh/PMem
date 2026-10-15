"""Build deterministic Neo4j rows inside the terminable RDF preparation worker."""
from typing import Any
import json
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS


def build_projection(rdf_graph):
    # Stable preference: English, then untagged labels, then other languages.
    # Sorting also resolves multiple labels in the same language predictably.
    label_rows = sorted(rdf_graph.subject_objects(RDFS.label), key=lambda pair: (
        str(pair[0]), 0 if (getattr(pair[1], 'language', None) or '').lower().split('-')[0] == 'en'
        else 1 if not getattr(pair[1], 'language', None) else 2,
        (getattr(pair[1], 'language', None) or '').lower(), str(pair[1])))
    labels = {}
    for subject, label in label_rows:
        labels.setdefault(str(subject), str(label))
    class_iris = {str(subject) for subject in rdf_graph.subjects(RDF.type, OWL.Class)}
    property_iris = {
        str(subject) for subject in rdf_graph.subjects(RDF.type, OWL.ObjectProperty)
    } | {str(subject) for subject in rdf_graph.subjects(RDF.type, OWL.DatatypeProperty)}
    resource_iris = {str(value) for triple in rdf_graph for value in (triple[0], triple[2]) if not isinstance(value, Literal)}
    literal_properties: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for subject, predicate, value in rdf_graph:
        if isinstance(value, Literal):
            literal_properties.setdefault(str(subject), {}).setdefault(str(predicate), []).append({
                "value": str(value), "datatype": str(value.datatype) if value.datatype else None,
                "language": value.language,
            })
    for predicates in literal_properties.values():
        for values in predicates.values():
            values.sort(key=lambda value: (value['value'], value['datatype'] or '', value['language'] or ''))
    resources = [
        {"iri": iri, "label": labels.get(iri, iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]),
         "requirement": (URIRef(iri), RDF.type, URIRef('https://depo.example.org/ceim/0.1/Requirement')) in rdf_graph,
         "source": min((str(value) for value in rdf_graph.objects(URIRef(iri), URIRef('https://depo.example.org/ceim/0.1/sourceStandard'))), default=None),
         "description": min((str(value) for value in rdf_graph.objects(URIRef(iri), RDFS.comment)), default=None),
         "kind": "class" if iri in class_iris else "property" if iri in property_iris else "resource",
         "rdf_properties": json.dumps(literal_properties.get(iri, {}), sort_keys=True)}
        for iri in sorted(resource_iris)
    ]
    ceim_relationships = {
        "hasPart": "HAS_PART", "hasGeometry": "HAS_GEOMETRY", "hasFeature": "HAS_FEATURE",
        "hasCharacteristic": "HAS_CHARACTERISTIC", "usesDatum": "USES_DATUM",
        "usesReferenceFrame": "USES_REFERENCE_FRAME", "realizes": "REALIZES",
        "satisfies": "SATISFIES", "traceTo": "TRACE_TO", "derivedFrom": "DERIVED_FROM",
        "verifiedBy": "VERIFIED_BY", "validatedBy": "VALIDATED_BY", "impacts": "IMPACTS",
        "produces": "PRODUCES", "consumes": "CONSUMES",
    }
    relationships: dict[str, list[dict[str, str]]] = {
        "SUBCLASS_OF": [], "DOMAIN": [], "RANGE": [], "SEMANTIC_RELATION": [],
    }
    relationships.update({relationship: [] for relationship in ceim_relationships.values()})
    # Preserve arbitrary RDF predicates as SEMANTIC_RELATION, but promote
    # CEIM containment and engineering-structure links for graph traversal.
    ceim = "https://depo.example.org/ceim/0.1/"
    special_predicates = {
        str(RDFS.subClassOf): "SUBCLASS_OF", str(RDFS.domain): "DOMAIN", str(RDFS.range): "RANGE",
        **{f"{ceim}{predicate}": relationship for predicate, relationship in ceim_relationships.items()},
    }
    for subject, predicate, obj in rdf_graph:
        if isinstance(obj, Literal):
            continue
        relation_type = special_predicates.get(str(predicate), "SEMANTIC_RELATION")
        relationships[relation_type].append({"source": str(subject), "target": str(obj), "predicate": str(predicate)})
    for rows in relationships.values():
        rows.sort(key=lambda row: (row['source'], row['predicate'], row['target']))

    return resources, relationships, ceim_relationships
