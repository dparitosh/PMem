"""XSD bounds remain independent OWL restrictions, not discarded annotations."""
from lxml import etree
from rdflib import Graph,OWL,RDF,RDFS
from backend.Services.owl_xsd_engine import OntologyConfig,parse_complex_type
from backend.ontology_service import owl_dl


def generated():
    cfg=OntologyConfig(base_uri='urn:test:cardinality:',prefix='test',title='Bounds',description='Bounds test')
    node=etree.fromstring(b'''<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema" name="Assembly"><xs:sequence><xs:element name="serial" type="xs:string" minOccurs="1" maxOccurs="3"/></xs:sequence><xs:attribute name="code" type="xs:string" use="required"/></xs:complexType>''')
    graph=Graph();parse_complex_type(graph,node,'bounds',set(),cfg,{}, {})
    return graph


def test_element_and_required_attribute_keep_both_bounds_on_separate_nodes():
    graph=generated()
    minimum=set(graph.subjects(OWL.minCardinality,None));maximum=set(graph.subjects(OWL.maxCardinality,None))
    assert len(minimum)==2 and len(maximum)==2
    assert not minimum.intersection(maximum)
    assert sorted(int(value) for value in graph.objects(None,OWL.maxCardinality))==[1,3]
    for restriction in minimum|maximum:
        assert (restriction,RDF.type,OWL.Restriction) in graph
        assert len(list(graph.objects(restriction,OWL.onProperty)))==1
        assert list(graph.subjects(RDFS.subClassOf,restriction))


def test_generated_cardinality_axioms_are_parsed_and_reasoned_without_loss():
    source=generated();logical=Graph()
    # This fixture isolates generated cardinality axioms, not a production projection.
    for node in source.subjects(RDF.type,OWL.Restriction):
        for triple in source.triples((node,None,None)):logical.add(triple)
        for parent in source.subjects(RDFS.subClassOf,node):
            logical.add((parent,RDF.type,OWL.Class));logical.add((parent,RDFS.subClassOf,node))
        for prop in source.objects(node,OWL.onProperty):
            logical.add((prop,RDF.type,OWL.DatatypeProperty))
    assert owl_dl.capabilities()['available'],'Bundled offline reasoner must be available'
    result=owl_dl.inspect_graph(logical,artifact_sha256='cardinality-fixture',include_foundation=False)
    assert result['status']=='consistent',result
    assert result['consistency_verified'] and result['deductive_reasoner_executed']
    assert result['unparsed_statement_count']==0


def test_complete_conversion_declares_only_valid_generated_metadata(tmp_path):
    from backend.Services.owl_xsd_engine import convert_xsd_to_owl
    from rdflib.namespace import DC,DCTERMS
    schema=tmp_path/'source.xsd'
    schema.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:bounds"><xs:complexType name="Assembly"><xs:sequence><xs:element name="serial" type="xs:string" minOccurs="1" maxOccurs="3"/></xs:sequence></xs:complexType></xs:schema>',encoding='utf-8')
    output=tmp_path/'converted.ttl'
    cfg=OntologyConfig(base_uri='urn:test:complete:',prefix='complete',title='Complete conversion',description='Conversion regression',schema_dir=str(tmp_path),target_files=['source'],output_ttl=str(output))
    convert_xsd_to_owl(cfg)
    graph=Graph().parse(output,format='turtle')
    from rdflib import Namespace
    assert (cfg.ns.hasSchemaFile,RDF.type,OWL.AnnotationProperty) in graph
    assert (Namespace("http://www.w3.org/ns/prov#").wasDerivedFrom,RDF.type,OWL.AnnotationProperty) in graph
    assert (DC.source,RDF.type,OWL.AnnotationProperty) in graph
    assert (DCTERMS.license,RDF.type,OWL.AnnotationProperty) in graph
    assert not set(graph.subjects(OWL.minCardinality,None)).intersection(graph.subjects(OWL.maxCardinality,None))
