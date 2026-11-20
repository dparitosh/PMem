"""Offline regression checks. No customer server, DB or credentials required."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from rdflib import Graph, RDF, Literal, XSD
import nexus_ods as ods


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = ods.configuration(ods.ROOT / 'config.example.json')
        self.config['output'] = Path(self.tmp.name) / 'out'
        self.scenario = ods.read_json(self.config['scenario'])

    def generated(self):
        return ods.generate(self.config)

    def make_loader(self, handler):
        loader = ods.Loader(self.config, transport=httpx.MockTransport(handler))
        self.addCleanup(loader.close)
        return loader

    def state(self, manifest):
        ods.save(self.config['output'] / 'load-state.json', {
            'ontology_id': 'customer-fixture', 'ontology_api': self.config['ontology_api'],
            'oslc_api': self.config['oslc_api'], 'artifact_sha256': manifest['artifact_sha256']})

    def test_generation_keeps_historical_options_and_current_evidence_separate(self):
        manifest = self.generated()
        self.assertEqual((manifest['records'], manifest['historical_records'], manifest['relationships']), (45, 5, 70))
        g = Graph().parse(self.config['output'] / 'engineering-ods.ttl')
        people = set(g.subjects(RDF.type, ods.OWL.NamedIndividual))
        self.assertEqual(len(people), 45)
        self.assertTrue(all(g.value(s, ods.ENG.engineeringApproved) == Literal(False) for s in people))
        self.assertEqual(len(list(g.triples((None, ods.CEIM.derivedFrom, None)))), 5)
        self.assertEqual(len(list(g.triples((None, ods.CEIM.verifiedBy, None)))), 4)
        self.assertTrue(manifest['shacl_conforms'])

    def test_stable_golden_ids_and_isolated_case_copies(self):
        self.generated()
        first = ods.read_json(self.config['output'] / 'identities.json')
        self.generated()
        self.assertEqual(first, ods.read_json(self.config['output'] / 'identities.json'))
        result = ods.generate(self.config, 2)
        ids = ods.read_json(self.config['output'] / 'identities.json')
        self.assertEqual(len(set(x['golden_id'] for x in ids)), 90)
        self.assertEqual(result['historical_records'], 10)

    def test_decision_fixture_really_has_only_b_feasible(self):
        rows = {r['id']: r for r in self.scenario['records']}
        def val(key, prop):
            return float(rows[key]['properties'][str(ods.ENG[prop])]['value'])
        feasible = []
        for letter in 'ABCD':
            k = 'VALIDATE-' + letter
            if (val(k, 'temperature') <= 80 and val(k, 'vibration') <= 2.8 and val(k, 'speed') >= 1500
                and val(k, 'outerDiameter') <= 62 and val('OPT-' + letter, 'leadTime') <= 10):
                feasible.append(letter)
        self.assertEqual(feasible, ['B'])

    def test_duplicate_ids_fail(self):
        self.scenario['records'].append(copy.deepcopy(self.scenario['records'][0]))
        p = Path(self.tmp.name) / 'scenario.json'
        ods.save(p, self.scenario)
        self.config['scenario'] = p
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.generated()

    def test_broken_relationship_fails(self):
        self.scenario['links'][0]['to'] = 'MISSING'
        p = Path(self.tmp.name) / 'scenario.json'
        ods.save(p, self.scenario)
        self.config['scenario'] = p
        with self.assertRaisesRegex(ValueError, 'endpoint'):
            self.generated()

    def test_history_must_precede_current_context(self):
        self.scenario['history_date'] = '2099-01-01'
        p = Path(self.tmp.name) / 'scenario.json'
        ods.save(p, self.scenario)
        self.config['scenario'] = p
        with self.assertRaisesRegex(ValueError, 'Historical date'):
            self.generated()

    def test_remote_urls_require_https_and_no_inline_credentials(self):
        for url in ['http://customer.example/api', 'https://user:password@customer.example/api', 'https://customer.example/api?key=test']:
            with self.assertRaises(ValueError): ods.endpoint(url)
        self.assertEqual(ods.endpoint('https://customer.example/api/'), 'https://customer.example/api')

    @patch.dict(os.environ, {'ONTOLOGY_APPROVAL_TOKEN': 'test-only-not-a-real-key', 'GRAPH_READ_TOKEN': 'test-read'})
    def test_register_does_not_approve_or_publish_and_can_resume(self):
        self.generated()
        methods = []
        def handler(request):
            methods.append((request.method, request.url.path))
            return httpx.Response(200, json={'ontology_id': 'customer-fixture'})
        loader = self.make_loader(handler)
        loader.register()
        loader.register()
        self.assertEqual(methods, [('POST', '/api/v1/ontologies/register'), ('GET', '/api/v1/ontologies/customer-fixture')])
        with self.assertRaisesRegex(ValueError, 'registration state'): self.generated()

    @patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'test-read'})
    def test_registration_cannot_reuse_another_environment_or_changed_artifact(self):
        manifest = self.generated()
        self.state(manifest)
        loader = self.make_loader(lambda request: httpx.Response(200, json={}))
        other = self.config['oslc_api']
        self.config['oslc_api'] = 'https://another.example/api/v1/change-control'
        with self.assertRaisesRegex(ValueError, 'another environment'): loader.state()
        self.config['oslc_api'] = other
        with (self.config['output'] / 'engineering-ods.ttl').open('a') as f: f.write('\n# changed')
        with self.assertRaisesRegex(ValueError, 'Artifact changed'): loader.state()

    @patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'test-read'})
    def test_verify_requires_matching_current_artifact_receipt(self):
        manifest = self.generated()
        self.state(manifest)
        result = {'status': 'published', 'receipt': {'status': 'published', 'current': True,
                  'ontology_id': 'customer-fixture', 'publication_id': 'wrong-hash', 'resources': 45, 'relationships': 70}}
        loader = self.make_loader(lambda request: httpx.Response(200, json=result))
        self.assertFalse(loader.verify()['verified'])
        result['receipt']['publication_id'] = manifest['artifact_sha256']
        self.assertTrue(loader.verify()['verified'])
        result['receipt']['current'] = False
        self.assertFalse(loader.verify()['verified'])

    @patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'test-read', 'ONTOLOGY_APPROVAL_TOKEN': 'test-write'})
    def test_change_is_exactly_one_requested_action_with_revision_and_digest(self):
        self.state(self.generated())
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'current_plan_digest': 'plan-v3', 'change_request': {'state': 'submitted', 'revision': 3}})
        loader = self.make_loader(handler)
        loader.change('accept', 'Owner reviewed the authored fixture')
        self.assertEqual([r.method for r in requests], ['GET', 'POST'])
        body = json.loads(requests[-1].content)
        self.assertEqual((body['action'], body['expected_revision'], body['expected_plan_digest']), ('accept', 3, 'plan-v3'))
        self.assertNotIn('approved_by', body)

    @patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'test-read', 'TEST_APIM_KEY': 'test-subscription'})
    def test_gateway_subscription_header_uses_operator_environment(self):
        self.config['subscription_key_env'] = 'TEST_APIM_KEY'
        observed = []
        def handler(request):
            observed.append(request)
            return httpx.Response(200, json={'ready': True})
        loader = self.make_loader(handler)
        loader.call('GET', self.config['ontology_api'])
        self.assertEqual(observed[0].headers['Ocp-Apim-Subscription-Key'], 'test-subscription')
        self.assertEqual(observed[0].headers['Authorization'], 'Bearer test-read')

    @patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'test-read'})
    def test_redirect_is_not_followed_with_credentials(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': 'https://other.example'})
        loader = self.make_loader(handler)
        with self.assertRaisesRegex(ValueError, 'HTTP 302'): loader.call('GET', self.config['ontology_api'])
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
