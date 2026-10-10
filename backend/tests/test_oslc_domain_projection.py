import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from backend.oslc_service.domain_properties import project_properties


class DomainProjectionTests(unittest.TestCase):
    def test_common_values_and_domain_status(self):
        for domain, resource in [('cm', 'ChangeRequest'), ('qm', 'TestResult')]:
            result = project_properties({'name': 'Review', 'description': 'Evidence', 'code': 'R1', 'status': 'approved'},
                                        [f'http://open-services.net/ns/{domain}#{resource}'])
            self.assertEqual(result['dcterms:title'], 'Review')
            self.assertEqual(result['dcterms:identifier'], 'R1')
            self.assertEqual(result[f'oslc_{domain}:status'], 'approved')

    def test_no_status_is_invented_or_assigned_to_other_domains(self):
        self.assertNotIn('oslc_cm:status', project_properties({}, ['http://open-services.net/ns/cm#ChangeRequest']))
        self.assertEqual(project_properties({'status': 'approved'}, ['http://open-services.net/ns/am#Resource']), {})

    def test_collection_members_require_link_identity(self):
        result = project_properties({'uses': ['urn:requirement:1', 'unresolved-id', None]},
                                    ['http://open-services.net/ns/rm#RequirementCollection'])
        self.assertEqual(result['oslc_rm:uses'], ['urn:requirement:1'])

    def test_each_advertised_service_has_only_its_domain_shapes(self):
        tree = ast.parse(Path('backend/Services/oslc_service.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OSLCService')
        members = [node for node in cls.body if isinstance(node, ast.Assign)]
        members.extend(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in {'service_provider', 'resource_domain_types', '_canonical_property_descriptor'})
        namespace = {'quote': quote, 'Dict': dict, 'Any': object, 'List': list, 'Optional': __import__('typing').Optional}
        module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Service', bases=[], keywords=[], body=members, decorator_list=[])], type_ignores=[]))
        exec(compile(module, '<actual discovery>', 'exec'), namespace)
        service = namespace['Service']
        service.config = classmethod(lambda cls: SimpleNamespace(base_url='http://oslc', provider_id='depo', provider_title='DEPO'))
        service._ontology_domains = classmethod(lambda cls: [{'ontology_id': 'qif', 'id': 'ontology:qif', 'title': 'QIF', 'prefix': 'qif'}])
        result = service.service_provider()
        for domain in result['services']:
            self.assertEqual(set(domain['resourceShapes']), {query['resourceShape'] for query in domain['queryCapabilities']})
        query = next(query for query in result['queryCapabilities'] if query['resourceType'] == 'ontology:qif')
        self.assertTrue(query['queryBase'].endswith('/ontology%3Aqif'))
        self.assertTrue(result['supportProfile']['read_only'])
        self.assertTrue(result['domainResources']['ontologies']['domains']['ontology:qif']['queryBase'].endswith('/ontology%3Aqif'))
        for name, expected in [('changerequest', service.CM_CHANGE_REQUEST_URI), ('testresult', service.QM_TEST_RESULT_URI), ('testcase', service.QM_TEST_CASE_URI)]:
            self.assertEqual(service.resource_domain_types([], {'entity_type': name}), [expected])
        self.assertEqual(service._canonical_property_descriptor({'name': 'dcterms:title', 'occurs': 'exactly-one'})['occurs'],
                         'http://open-services.net/ns/core#Exactly-one')


if __name__ == '__main__':
    unittest.main()
