import unittest
from types import SimpleNamespace
from unittest.mock import patch
from rdflib import Graph, BNode, URIRef, Literal, RDF
from rdflib.namespace import SH
from rdflib.compare import isomorphic
from pyshacl import validate
from backend.ontology_service.merge_reporting import validate_shacl, MergeReportValidator


def core_results(report):
    result = Graph()
    roots = set(report.subjects(RDF.type, SH.ValidationReport))
    nodes = set(report.objects(None, SH.result))
    for subject in roots | nodes:
        for triple in report.triples((subject,None,None)): result.add(triple)
    return result


class MergeReportingTests(unittest.TestCase):
    def test_same_conformance_text_and_core_results_as_standard_reporter(self):
        shapes = Graph().parse(data='''@prefix sh:<http://www.w3.org/ns/shacl#> .
            <urn:shape> a sh:NodeShape; sh:targetNode <urn:x>;
            sh:property [sh:path <urn:name>; sh:minCount 1] ;
            sh:property [sh:path <urn:code>; sh:maxCount 1; sh:severity sh:Warning] .''',format='turtle')
        for valid in (False, True):
            with self.subTest(valid=valid):
                data = Graph()
                if valid: data.add((URIRef('urn:x'),URIRef('urn:name'),Literal('Name')))
                else:
                    data.add((URIRef('urn:x'),URIRef('urn:code'),Literal('one')))
                    data.add((URIRef('urn:x'),URIRef('urn:code'),Literal('two')))
                expected = validate(data,shacl_graph=shapes,inference='none',inplace=True,
                                    allow_infos=False,allow_warnings=False,advanced=False,do_owl_imports=False)
                actual = validate_shacl(data,shacl_graph=shapes)
                self.assertEqual(actual[0], expected[0])
                self.assertEqual(actual[2], expected[2][:20000])
                self.assertTrue(isomorphic(core_results(actual[1]),core_results(expected[1])))
                self.assertEqual(actual[3]['total_results'],len(list(expected[1].objects(None,SH.result))))

    def test_report_builder_never_traverses_anonymous_focus_context(self):
        data = Graph(); focus = BNode('focus')
        data.add((focus,URIRef('urn:self'),focus))
        shape = Graph(); result_node=BNode()
        triples = [(result_node,RDF.type,SH.ValidationResult),
                   (result_node,SH.focusNode,(data,focus)),
                   (result_node,SH.resultSeverity,SH.Violation),
                   (result_node,SH.sourceConstraintComponent,(shape,SH.MinCountConstraintComponent))]
        validator = object.__new__(MergeReportValidator)
        with patch.object(data,'predicates',side_effect=AssertionError('Data context must not be copied')), \
             patch.object(data,'objects',side_effect=AssertionError('Data context must not be copied')):
            report,text=validator.create_validation_report(SimpleNamespace(graph=shape),False,[('Finding\n',result_node,triples)])
        self.assertIn((result_node,SH.focusNode,focus),report)
        self.assertEqual(validator.report_summary['total_results'],1)
        self.assertIn('Finding',text)

    def test_text_limit_does_not_limit_validation_results_or_counts(self):
        shape=Graph(); results=[]
        for index in range(120):
            node=BNode()
            results.append((f'{index:04d} '+('x'*300)+'\n',node,
                [(node,RDF.type,SH.ValidationResult),(node,SH.resultSeverity,SH.Warning),
                 (node,SH.sourceConstraintComponent,(shape,SH.MinCountConstraintComponent))]))
        validator=object.__new__(MergeReportValidator)
        graph,text=validator.create_validation_report(SimpleNamespace(graph=shape),False,results)
        self.assertEqual(len(text),20000)
        self.assertEqual(len(list(graph.objects(None,SH.result))),120)
        self.assertEqual(validator.report_summary['total_results'],120)
        self.assertEqual(validator.report_summary['by_severity'][str(SH.Warning)],120)
        self.assertEqual(len(validator.report_summary['results_sample']),100)
        self.assertTrue(validator.report_summary['text_truncated'])

    def test_custom_shape_failure_is_not_converted_to_conformance(self):
        shapes=Graph().parse(data='''@prefix sh:<http://www.w3.org/ns/shacl#> .
            <urn:custom> a sh:NodeShape; sh:targetNode <urn:x>;
            sh:property [sh:path <urn:required>; sh:minCount 1; sh:message "Required custom value"] .''',format='turtle')
        actual=validate_shacl(Graph(),shacl_graph=shapes)
        self.assertFalse(actual[0])
        self.assertIn('Required custom value',actual[2])
        self.assertEqual(actual[3]['total_results'],1)
