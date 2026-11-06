"""Read-only semantic inventory shared by catalog and graph projections.
Derived classifications never add assertions to the submitted RDF graph.
"""
from rdflib import BNode, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

PROPERTY_TYPES = {OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property}
CLASS_TYPES = {OWL.Class, RDFS.Class}
META_TYPES = CLASS_TYPES | PROPERTY_TYPES | {OWL.Ontology, OWL.Restriction, OWL.Axiom, OWL.NamedIndividual,
    RDFS.Datatype, OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.TransitiveProperty,
    OWL.SymmetricProperty, OWL.AsymmetricProperty, OWL.ReflexiveProperty, OWL.IrreflexiveProperty}

def semantic_types(graph, subject):
    return set(graph.objects(subject, RDF.type))

def is_individual(graph, subject):
    types = semantic_types(graph, subject)
    return OWL.NamedIndividual in types or any(t not in META_TYPES and any((t, RDF.type, cls) in graph for cls in CLASS_TYPES) for t in types)

def kind(graph, subject):
    types = semantic_types(graph, subject)
    if types & CLASS_TYPES: return 'class'
    if types & PROPERTY_TYPES: return 'property'
    if OWL.Restriction in types: return 'restriction'
    if OWL.Axiom in types: return 'axiom'
    if str(subject).startswith(str(XSD)) or RDFS.Datatype in types: return 'datatype'
    if is_individual(graph, subject): return 'individual'
    if any(str(t).startswith('http://www.w3.org/2003/11/swrl#') for t in types): return 'rule'
    if isinstance(subject, BNode): return 'expression'
    return 'resource'

def inventory(graph):
    subjects = set(graph.subjects())
    declared = lambda *types: set().union(*(set(graph.subjects(RDF.type, t)) for t in types))
    return {'triples': len(graph), 'classes': len(declared(OWL.Class, RDFS.Class)),
        'object_properties': len(declared(OWL.ObjectProperty)),
        'datatype_properties': len(declared(OWL.DatatypeProperty)),
        'annotation_properties': len(declared(OWL.AnnotationProperty)),
        'named_individuals': len(declared(OWL.NamedIndividual)),
        'individuals': sum(isinstance(s, URIRef) and is_individual(graph, s) for s in subjects),
        'inverse_axioms': len(list(graph.triples((None, OWL.inverseOf, None)))),
        'axiom_annotations': len(declared(OWL.Axiom)),
        'swrl_rules': len(declared(URIRef('http://www.w3.org/2003/11/swrl#Imp')))}
