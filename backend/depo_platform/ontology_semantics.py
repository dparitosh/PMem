"""Semantic inventory and explicit declarations for generator-owned metadata.
Inventory classification is read-only; generation helpers affect new graphs only.
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


def declare_generated_metadata(graph, custom_annotations=()):
    """Declare only metadata predicates whose role is fixed by our generators.

    No arbitrary source predicate is retyped and no source assertion is removed.
    This is declaration completeness, not OWL-DL certification.
    """
    from rdflib import Literal, Namespace
    from rdflib.namespace import DC, DCTERMS, SKOS
    annotations = [ns[name] for ns in (DC, DCTERMS) for name in
                   ('creator','source','identifier','format','title','description','license','subject','created','modified','conformsTo') if name in ns]
    annotations += [SKOS[name] for name in ('prefLabel','altLabel','hiddenLabel','definition','note','scopeNote','editorialNote','changeNote','historyNote','example','notation')]
    annotations += list(custom_annotations)
    for predicate in annotations:
        if not any(graph.triples((None,predicate,None))): continue
        types = set(graph.objects(predicate,RDF.type))
        if types & {OWL.ObjectProperty,OWL.DatatypeProperty}: continue
        graph.add((predicate,RDF.type,OWL.AnnotationProperty))
        if not any(graph.objects(predicate,RDFS.label)):
            graph.add((predicate,RDFS.label,Literal(str(predicate).rsplit('#',1)[-1].rstrip('/').rsplit('/',1)[-1])))
    prov = Namespace('http://www.w3.org/ns/prov#')
    if any(graph.subjects(RDF.type,prov.Entity)):
        graph.add((prov.Entity,RDF.type,OWL.Class))
        graph.add((prov.Entity,RDFS.label,Literal('Provenance entity')))
