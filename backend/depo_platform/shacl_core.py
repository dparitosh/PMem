"""Shared bounded SHACL core checks; no imports or executable extensions."""
from rdflib import URIRef
from rdflib.namespace import RDF, OWL, RDFS
from .ontology_semantics import subclass_type_resolver

SH = 'http://www.w3.org/ns/shacl#'


def check_shacl_core(data, shapes):
    if len(shapes) > 250000:
        raise ValueError('SHACL graph exceeds the assessment budget')
    forbidden={'sparql','js','rule','select','ask','construct','function','sparqlconstraint','sparqlfunction','jsconstraint','jsfunction'}
    if any(isinstance(term,URIRef) and ((str(term).startswith(SH) and str(term)[len(SH):].lower() in forbidden) or term==OWL.imports)
           for triple in shapes for term in triple):
        raise ValueError('Only retained SHACL core constraints are supported; executable extensions and imports are blocked')
    nodes=set(shapes.subjects(RDF.type,URIRef(SH+'NodeShape')))
    if not nodes:
        return {'status':'not_assessed','conforms':None,'reason':'No retained SHACL node shapes','shape_count':0,'targeted_subjects':0}
    # Count actual targets rather than presenting a vacuous conformance result
    # as proof that inspection instances were checked.
    declared={subject:set(data.objects(subject,RDF.type)) for subject in set(data.subjects(RDF.type,None))}
    resolve=subclass_type_resolver(data)
    targets=set()
    for shape in nodes:
        classes=set(shapes.objects(shape,URIRef(SH+'targetClass')))
        if (shape,RDF.type,RDFS.Class) in shapes: classes.add(shape)
        targets.update(subject for subject,types in declared.items() if classes.intersection(types | resolve(types)))
        targets.update(shapes.objects(shape,URIRef(SH+'targetNode')))
        for predicate in shapes.objects(shape,URIRef(SH+'targetSubjectsOf')):targets.update(data.subjects(predicate,None))
        for predicate in shapes.objects(shape,URIRef(SH+'targetObjectsOf')):targets.update(data.objects(None,predicate))
    if not targets:
        return {'status':'no_targets','conforms':None,'reason':'Retained shapes select no data subjects','shape_count':len(nodes),'targeted_subjects':0}
    from semantica.ontology import OntologyEngine
    report=OntologyEngine().validate_graph(data,shacl=shapes.serialize(format='turtle'),explain=False)
    return {'status':'conforms' if report.conforms else 'violations','conforms':bool(report.conforms),
            'provider':'Semantica','shape_count':len(nodes),'targeted_subjects':len(targets),
            'scope':'Retained SHACL core shapes; product acceptance and full OWL-DL consistency are separate'}
