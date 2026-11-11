"""Build deterministic Neo4j rows inside the terminable RDF preparation worker."""
from typing import Any
import json
from rdflib import Literal, URIRef, BNode
from .ontology_semantics import CLASS_TYPES, PROPERTY_TYPES, META_TYPES
from rdflib.namespace import OWL, RDF, RDFS, XSD


def build_projection(rdf_graph):
    # Index once instead of repeatedly querying RDF types for each resource.
    terms_by_id, labels, types, comments, sources = {}, {}, {}, {}, {}
    source_predicate = URIRef('https://depo.example.org/ceim/0.1/sourceStandard')
    literal_properties: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for subject, predicate, value in rdf_graph:
        identity = str(subject)
        terms_by_id[identity] = subject
        if not isinstance(value, Literal):
            terms_by_id[str(value)] = value
        if predicate == RDF.type:
            types.setdefault(subject, set()).add(value)
        if predicate == RDFS.label:
            language = (getattr(value, 'language', None) or '').lower()
            rank = (0 if language.split('-')[0] == 'en' else 1 if not language else 2, language, str(value))
            if identity not in labels or rank < labels[identity]: labels[identity] = rank
        if predicate == RDFS.comment:
            comments[identity] = min(comments.get(identity, str(value)), str(value))
        if predicate == source_predicate:
            sources[identity] = min(sources.get(identity, str(value)), str(value))
        if isinstance(value, Literal):
            literal_properties.setdefault(identity, {}).setdefault(str(predicate), []).append({
                "value": str(value), "datatype": str(value.datatype) if value.datatype else None,
                "language": value.language,
            })
    for predicates in literal_properties.values():
        for values in predicates.values():
            values.sort(key=lambda value: (value['value'], value['datatype'] or '', value['language'] or ''))
    declared_classes = {term for term, values in types.items() if values & CLASS_TYPES}
    def indexed_kind(subject):
        values = types.get(subject, set())
        if values & CLASS_TYPES: return 'class'
        if values & PROPERTY_TYPES: return 'property'
        if OWL.Restriction in values: return 'restriction'
        if OWL.Axiom in values: return 'axiom'
        if str(subject).startswith(str(XSD)) or RDFS.Datatype in values: return 'datatype'
        if OWL.NamedIndividual in values or any(t not in META_TYPES and t in declared_classes for t in values): return 'individual'
        if any(str(t).startswith('http://www.w3.org/2003/11/swrl#') for t in values): return 'rule'
        return 'expression' if isinstance(subject, BNode) else 'resource'
    resources = [
        {"iri": iri, "label": labels[iri][2] if iri in labels else iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1],
         "requirement": URIRef('https://depo.example.org/ceim/0.1/Requirement') in types.get(terms_by_id[iri], set()),
         "source": sources.get(iri), "description": comments.get(iri),
         "kind": indexed_kind(terms_by_id[iri]),
         "rdf_types": sorted(str(t) for t in types.get(terms_by_id[iri], set())),
         "rdf_properties": json.dumps(literal_properties.get(iri, {}), sort_keys=True)}
        for iri in sorted(terms_by_id)
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
