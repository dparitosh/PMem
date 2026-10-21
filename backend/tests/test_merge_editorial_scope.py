import tempfile
import unittest
from pathlib import Path
from rdflib import Graph, BNode, URIRef, Literal, RDF, RDFS, OWL, XSD
from backend.ontology_service.merge_semantics import _validate_merge
from backend.Services.shacl_service import ShaclValidationService


class MergeEditorialScopeTests(unittest.TestCase):
    def test_embedded_constraints_do_not_disable_standard_metadata_checks(self):
        graph=Graph().parse(data='''@prefix sh:<http://www.w3.org/ns/shacl#> .
            @prefix owl:<http://www.w3.org/2002/07/owl#> .
            @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
            <urn:Owner> a owl:Class; rdfs:label "Owner" .
            <urn:custom> a sh:NodeShape; sh:targetNode <urn:Owner>;
                sh:property [sh:path rdfs:label; sh:minCount 1] .''',format='turtle')
        result=_validate_merge(graph,[])
        profiles={item['profile']:item['conforms'] for item in result['report_summary']['profiles']}
        self.assertTrue(profiles['custom_inferred'])
        self.assertFalse(profiles['editorial_asserted'])
        self.assertFalse(result['shacl_conforms'])

    def source(self, direct_expression=False):
        graph=Graph(); owner=URIRef('urn:Owner'); prop=URIRef('urn:property'); restriction=BNode()
        graph.add((owner,RDF.type,OWL.Class))
        graph.add((prop,RDF.type,OWL.DatatypeProperty))
        for node in (owner,prop):
            graph.add((node,RDFS.label,Literal('Name')))
            graph.add((node,RDFS.comment,Literal('Description')))
            graph.add((node,URIRef('http://purl.org/dc/elements/1.1/source'),Literal('fixture')))
        graph.add((restriction,RDF.type,OWL.Restriction))
        graph.add((restriction,OWL.onProperty,prop))
        graph.add((restriction,OWL.maxCardinality,Literal(1,datatype=XSD.nonNegativeInteger)))
        graph.add((owner,RDFS.subClassOf,restriction))
        graph.add((prop,RDFS.domain,restriction if direct_expression else owner))
        graph.add((prop,RDFS.range,XSD.string))
        return graph,prop

    def test_inferred_metadata_is_not_an_additional_authoring_requirement(self):
        graph,_=self.source()
        result=_validate_merge(graph,[])
        self.assertTrue(result['shacl_conforms'],result['report'][:1200])
        self.assertTrue(result['owl_rl_performed'])
        self.assertEqual(result['report_summary']['profiles'][0]['profile'],'editorial_asserted')

    def test_asserted_anonymous_restriction_is_a_valid_domain_class_expression(self):
        graph,_=self.source(direct_expression=True)
        result=_validate_merge(graph,[])
        self.assertTrue(result['shacl_conforms'],result['report'][:1200])

    def test_literal_domain_remains_invalid(self):
        graph,prop=self.source()
        graph.remove((prop,RDFS.domain,None)); graph.add((prop,RDFS.domain,Literal('invalid domain')))
        result=_validate_merge(graph,[])
        self.assertFalse(result['shacl_conforms'])

    def test_custom_rules_still_see_inferred_metadata(self):
        graph,_=self.source()
        graph.parse(data='''@prefix sh:<http://www.w3.org/ns/shacl#> .
            @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
            <urn:custom> a sh:NodeShape; sh:targetNode <urn:property>;
            sh:property [sh:path rdfs:domain; sh:nodeKind sh:IRI] .''',format='turtle')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'generated.ttl'
            path.write_text(ShaclValidationService().create_default_shapes(),encoding='utf-8')
            result=_validate_merge(graph,[{'shacl_file_path':str(path)}])
        self.assertFalse(result['shacl_conforms'])
        profiles={item['profile']:item['conforms'] for item in result['report_summary']['profiles']}
        self.assertFalse(profiles['custom_inferred'])
        self.assertTrue(profiles['editorial_asserted'])

    def test_generated_checks_do_not_reject_inferred_datatype_disjointness(self):
        graph=Graph()
        graph.add((URIRef('urn:x'),URIRef('urn:p'),Literal(True,datatype=XSD.boolean)))
        graph.add((URIRef('urn:y'),URIRef('urn:p'),Literal(1,datatype=XSD.integer)))
        self.assertTrue(_validate_merge(graph,[])['shacl_conforms'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'custom.ttl'
            path.write_text('''@prefix sh:<http://www.w3.org/ns/shacl#> .
                @prefix owl:<http://www.w3.org/2002/07/owl#> .
                <urn:strict> a sh:PropertyShape; sh:targetSubjectsOf owl:disjointWith;
                sh:path owl:disjointWith; sh:class owl:Class .''',encoding='utf-8')
            self.assertFalse(_validate_merge(graph,[{'shacl_file_path':str(path)}])['shacl_conforms'])
