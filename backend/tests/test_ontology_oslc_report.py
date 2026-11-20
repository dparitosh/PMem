import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.graph_service.ontology_reports import ontology_report


class OntologyReportTests(unittest.TestCase):
    def test_unknown_registry_scope_does_not_query_graph(self):
        service = SimpleNamespace(_ontology_domain_scope=lambda value: None)
        graph = SimpleNamespace(_run=lambda *args: self.fail('Unregistered scope queried'))
        with patch.dict('sys.modules', {
            'backend.Services.oslc_service': SimpleNamespace(OSLCService=service),
            'backend.Services.graph_view_service': SimpleNamespace(GraphViewService=graph),
        }), self.assertRaises(ValueError):
            ontology_report('unknown')

    def test_scope_is_bound_and_all_categories_come_from_aggregation(self):
        calls = []
        service = SimpleNamespace(_ontology_domain_scope=lambda value: {'ontology_id': "qif'", 'prefix': 'qif'},
                                  _resource_type_predicate=lambda kind: 'n:Mapped')
        def run(query, params):
            calls.append((query, params))
            return [{'resources': 12, 'unmapped': 7, 'outgoing_links': 9,
                     **{f'c{i}': i for i in range(6)}}]
        with patch.dict('sys.modules', {
            'backend.Services.oslc_service': SimpleNamespace(OSLCService=service),
            'backend.Services.graph_view_service': SimpleNamespace(GraphViewService=SimpleNamespace(_run=run)),
        }):
            report = ontology_report("qif'")
        self.assertNotIn("qif'", calls[0][0])
        self.assertIn("$ontology_prefix <> ''", calls[0][0])
        self.assertEqual(calls[0][1]['ontology_id'], "qif'")
        self.assertEqual([row['count'] for row in report['categories']], list(range(6)))
        self.assertEqual(report['unmapped'], 7)
        self.assertFalse(report['sampled'])


if __name__ == '__main__':
    unittest.main()


class PublishedScopeResolutionTests(unittest.TestCase):
    def test_published_scope_resolves_without_legacy_upload_registration(self):
        from backend.Services.oslc_service import OSLCService
        from backend.Services.graph_view_service import GraphViewService
        with patch.object(OSLCService,'_ontology_domains',return_value=[]), patch.object(GraphViewService,'_run',return_value=[{'prefix':'plmxml'}]) as read:
            self.assertEqual(OSLCService._ontology_domain_scope('ontology:ceim-version-a'), {'ontology_id':'ceim-version-a','prefix':'plmxml'})
            self.assertEqual(read.call_args.args[1], {'ontology_id':'ceim-version-a'})
            self.assertNotIn('ceim-version-a', read.call_args.args[0])
            self.assertIn('RetainedOntologyIdentity', read.call_args.args[0])

    def test_unknown_published_scope_does_not_become_a_prefix(self):
        from backend.Services.oslc_service import OSLCService
        from backend.Services.graph_view_service import GraphViewService
        with patch.object(OSLCService,'_ontology_domains',return_value=[]), patch.object(GraphViewService,'_run',return_value=[]):
            self.assertIsNone(OSLCService._ontology_domain_scope('ontology:unknown'))

    def test_report_prefix_fallback_excludes_records_with_other_scope_ids(self):
        service=SimpleNamespace(_ontology_domain_scope=lambda value:{'ontology_id':'version-a','prefix':'shared'}, _resource_type_predicate=lambda kind:'n:Mapped')
        row={'resources':0,'unmapped':0,'outgoing_links':0,**{f'c{i}':0 for i in range(6)}}
        from unittest.mock import Mock
        read=Mock(return_value=[row])
        with patch.dict('sys.modules',{'backend.Services.oslc_service':SimpleNamespace(OSLCService=service), 'backend.Services.graph_view_service':SimpleNamespace(GraphViewService=SimpleNamespace(_run=read))}):
            ontology_report('version-a')
        query=read.call_args.args[0]
        self.assertIn('n.ontology_id IS NULL AND n.source_ontology IS NULL',query)
        self.assertIn('n:RetainedOntologyIdentity',query)


    def test_oslc_page_and_count_scope_cannot_follow_another_source_prefix(self):
        from backend.Services.oslc_service import OSLCService
        from backend.Services.oslc_query_service import OSLCQueryService
        params=OSLCQueryService.parse({})
        for build in (OSLCService._build_resource_query,OSLCService._build_count_query):
            query, values=build(params,OSLCService.DEFAULT_RESOURCE_TYPE,{'ontology_id':'version-a','prefix':'shared'})
            self.assertIn('n.source_ontology = $ontology_id',query)
            self.assertIn('n.ontology_id IS NULL AND n.source_ontology IS NULL',query)
            self.assertEqual(values['ontology_id'],'version-a')

class DeclaredRdfDomainTests(unittest.TestCase):
    def test_supported_declared_types_are_not_lost_in_generic_resource_projections(self):
        from backend.Services.oslc_service import OSLCService as service
        for kind, types in service.DOMAIN_RDF_TYPES.items():
            predicate=service._resource_type_predicate(kind)
            self.assertIn('n.rdf_types',predicate)
            for rdf_type in types:
                self.assertIn(rdf_type,predicate)
                self.assertTrue(service.resource_domain_types(['OntologyResource'],{'rdf_types':[rdf_type]}))
        self.assertEqual(service.resource_domain_types([],{'rdf_types':['https://example.org/Requirement']}),[])
        self.assertEqual(service.resource_domain_types([],{'rdf_types':['http://www.w3.org/2002/07/owl#Class']}),[])
        self.assertEqual(service.resource_domain_types([],{'rdf_types':['https://depo.example.org/ceim/0.1/Part']}),[])
    def test_supported_xmi_instances_use_the_existing_architecture_adapter(self):
        from backend.Services.oslc_service import OSLCService as service
        self.assertEqual(service.resource_domain_types([],{'rdf_types':['http://depo-onto.local/xmi#Plant/Component']}),[service.AM_TYPE_URI])
        self.assertEqual(service.resource_domain_types([],{'rdf_types':['https://unrelated.org/Component']}),[])
