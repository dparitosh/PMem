from rdflib import Graph, RDF, RDFS
from rdflib.namespace import DC, OWL, SKOS

from backend.Services.owl_generation_service import OWLGenerationService


def test_generated_associations_retain_provenance_and_source_version():
    data = b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:metadata:test" targetNamespace="urn:metadata:test" version="source-2026.1">
      <xs:complexType name="Part"/>
      <xs:complexType name="Assembly"><xs:sequence><xs:element name="parts" type="t:Part" maxOccurs="unbounded"/></xs:sequence></xs:complexType>
    </xs:schema>'''
    content, _ = OWLGenerationService.generate_owl_from_xsd(data, 'Source.xsd')
    graph = Graph().parse(data=content, format='turtle')
    associations = [node for node in graph.subjects(RDF.type, OWL.Class) if str(node).endswith('__Association')]
    assert len(associations) == 1
    association = associations[0]
    assert 'projection construct' in str(graph.value(association, RDFS.comment))
    assert graph.value(association, DC.source)
    assert str(graph.value(association, DC.source)) == 'Source.xsd'
    targets = [node for node in graph.subjects(RDFS.domain, association)
               if str(graph.value(node, RDFS.label)) == 'target parts']
    assert len(targets) == 1
    assert graph.value(targets[0], DC.source)
    assert str(graph.value(targets[0], DC.source)) == 'Source.xsd'
    assert 'Generated target edge' in str(graph.value(targets[0], RDFS.comment))
    assert graph.value(SKOS.Concept, DC.source) == SKOS.Concept
    header = next(graph.subjects(RDF.type, OWL.Ontology))
    assert str(graph.value(header, OWL.versionInfo)) == 'source-2026.1'
