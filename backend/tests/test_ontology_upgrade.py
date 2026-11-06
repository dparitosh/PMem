import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from backend.depo_platform.ontology_upgrade import proposed_update, run, detect_deployment

TTL = b'@prefix owl:<http://www.w3.org/2002/07/owl#>. <https://example.org/Product#> a owl:Ontology.'

class Response:
    status_code = 200
    def __init__(self, value): self.value = value
    def json(self): return self.value
    def raise_for_status(self): pass

class Client:
    def __init__(self, metadata, root): self.metadata=metadata; self.root=root; self.posts=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def get(self,url,**kwargs):
        if url.endswith('/ontologies'): return Response({'ontologies':[self.metadata], 'next_offset':None})
        return Response({'ontology_id':'new-draft','upgrade_from':'old'})
    def post(self,url,**kwargs):
        # All recovery evidence must exist before the write boundary is called.
        self.assert_backup = list(self.root.glob('logs/installation/ontology-upgrade-v2/*/source'))
        if not self.assert_backup: raise AssertionError('Backup missing before registration')
        self.posts.append((url,kwargs))
        return Response({'ontology_id':'new-draft','lifecycle_status':'draft'})

class OntologyUpgradeTests(unittest.TestCase):
    def test_prefix_plan_keeps_source_identity(self):
        item=proposed_update({'ontology_id':'old','prefix':'ontology'},'source.ttl',TTL)
        self.assertEqual(item['prefix'],'product')
        self.assertEqual(item['old_prefix'],'ontology')
        self.assertEqual(item['status'],'review_required')
        self.assertIsNone(proposed_update({'ontology_id':'new','prefix':'product'},'source.ttl',TTL))
        self.assertIsNone(proposed_update({'ontology_id':'new','ontology_upgrade_revision':2},'source.ttl',TTL))

    def test_namespace_ambiguity_requires_manual_review(self):
        with self.assertRaises(ValueError):
            proposed_update({'ontology_id':'old'}, 'source.ttl', TTL+b'<urn:second> a owl:Ontology.')

    def test_xsd_regeneration_is_flagged_even_without_prefix_change(self):
        item=proposed_update({'ontology_id':'old','prefix':'product'},'source.xsd',b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="https://example.org/Product#"/>')
        self.assertEqual(item['status'],'review_required')

    def test_stage_is_backed_up_and_idempotent_without_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); metadata={'ontology_id':'old','prefix':'ontology','original_filename':'source.ttl'}
            client=Client(metadata,root)
            with patch('httpx.Client',return_value=client), patch('backend.depo_platform.network.service_bearer_headers',return_value={}), patch('backend.depo_platform.ontology_upgrade.read_source',return_value=('source.ttl',TTL)), patch.dict('os.environ',{'ONTOLOGY_STORAGE_DIR':str(root/'legacy')}):
                first=run(root,stage=True)
                second=run(root,stage=True)
            self.assertEqual(len(client.posts),1)
            self.assertEqual(first['items'][0]['draft_id'],second['items'][0]['draft_id'])
            url,request=client.posts[0]
            self.assertTrue(url.endswith('/ontologies/register'))
            self.assertNotIn('approved_by',request['data'])
            self.assertEqual(json.loads(request['data']['extra_metadata'])['upgrade_from'],'old')
            self.assertNotIn('publish',request['data'])

    def test_database_detection_is_read_only(self):
        for record, mode in [(None,'new'),('semantic.depo_schema_migrations','existing')]:
            connect=MagicMock()
            with self.subTest(mode=mode), patch.dict('sys.modules', {'psycopg':SimpleNamespace(connect=connect)}), patch.dict('os.environ',{'DEPO_DATABASE_URL':'postgresql://test@localhost/test'}):
                cursor=connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
                cursor.fetchone.return_value=(record,)
                self.assertEqual(detect_deployment()['mode'],mode)
                self.assertEqual(cursor.execute.call_count,1)
                self.assertTrue(cursor.execute.call_args.args[0].startswith('SELECT'))

if __name__=='__main__': unittest.main()


class InventoryConnectivityTests(unittest.TestCase):
    def test_endpoint_uses_bind_address_and_preserves_explicit_routing(self):
        from backend.depo_platform.ontology_upgrade import inventory_endpoint
        cases = [({'DEPO_SERVICE_HOST':'10.0.2.16'},'http://10.0.2.16:8011/api/v1'),
                 ({'DEPO_SERVICE_HOST':'0.0.0.0'},'http://127.0.0.1:8011/api/v1'),
                 ({'DEPO_SERVICE_HOST':'::'},'http://[::1]:8011/api/v1'),
                 ({'ONTOLOGY_SERVICE_URL':'https://gateway.example/ontology'},'https://gateway.example/ontology/api/v1')]
        for env, expected in cases:
            with self.subTest(env=env), patch.dict('os.environ',env,clear=True):
                self.assertEqual(inventory_endpoint(),expected)

    def test_production_does_not_guess_a_peer_url(self):
        from backend.depo_platform.ontology_upgrade import inventory_endpoint
        with patch.dict('os.environ',{'DEPO_ENV':'production','DEPO_SERVICE_HOST':'10.0.2.16'},clear=True):
            with self.assertRaises(RuntimeError): inventory_endpoint()

    def test_transient_inventory_connection_is_retried_without_writes(self):
        import httpx
        from backend.depo_platform.ontology_upgrade import inventory_page
        client=MagicMock()
        client.get.side_effect=[httpx.ConnectError('refused'),Response({'ontologies':[]})]
        with patch('backend.depo_platform.ontology_upgrade.time.sleep'):
            result=inventory_page(client,'http://10.0.2.16:8011/api/v1',{},0)
        self.assertEqual(result,{'ontologies':[]})
        self.assertEqual(client.get.call_count,2)
        client.post.assert_not_called()
        self.assertLessEqual(client.get.call_args.kwargs['timeout'].read,10)

    def test_refusal_preserves_previous_plan_and_explains_service_logs(self):
        import httpx
        from backend.depo_platform.ontology_upgrade import UpgradeInventoryUnavailable
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); plan=root/'logs/installation/ontology-upgrade-v2/plan.json'
            plan.parent.mkdir(parents=True); plan.write_text('previous review')
            client=MagicMock(); client.__enter__.return_value=client
            client.get.side_effect=httpx.ConnectError('private connection details')
            with patch('httpx.Client',return_value=client),patch('backend.depo_platform.network.service_bearer_headers',return_value={}),patch('backend.depo_platform.ontology_upgrade.time.sleep'),patch.dict('os.environ',{'ONTOLOGY_SERVICE_URL':'http://10.0.2.16:8011/api/v1'},clear=True):
                with self.assertRaises(UpgradeInventoryUnavailable) as error: run(root)
            self.assertEqual(client.get.call_count,3)
            self.assertIn('ontology.err.log',str(error.exception))
            self.assertNotIn('private connection details',str(error.exception))
            self.assertEqual(plan.read_text(),'previous review')
            client.post.assert_not_called()

    def test_auth_rejection_is_not_retried(self):
        from backend.depo_platform.ontology_upgrade import inventory_page, UpgradeInventoryUnavailable
        response=Response({}); response.status_code=403
        client=MagicMock(); client.get.return_value=response
        with self.assertRaises(UpgradeInventoryUnavailable) as error:
            inventory_page(client,'http://service:8011/api/v1',{},0)
        self.assertIn('GRAPH_READ_TOKEN',str(error.exception))
        self.assertEqual(client.get.call_count,1)


class CeimUpgradeReviewTests(unittest.TestCase):
    def test_review_reports_old_and_unknown_mapping_without_writes(self):
        from backend.ceim.contract import contract
        from backend.depo_platform.ontology_upgrade import review_ceim_mappings
        registry=MagicMock()
        rows=[{'run_id':'old','status':'completed','source_standard':'ap242','output_manifest':{'mapping_digest':'sha256:old'}},
              {'run_id':'current','status':'completed','source_standard':'ap242','output_manifest':{'mapping_digest':contract.mapping_pack('ap242')['digest']}},
              {'run_id':'unknown','status':'completed','output_manifest':{'source_standard':'ap242'}},
              {'run_id':'active','status':'running','source_standard':'ap242'},
              {'run_id':'qif','status':'completed','source_standard':'qif'},
              {'run_id':'failed','status':'failed','source_standard':'ap242'}]
        registry.page.return_value=(len(rows),rows)
        with tempfile.TemporaryDirectory() as folder:
            report=review_ceim_mappings(folder,store=registry)
            self.assertTrue((Path(folder)/'logs/installation/ceim-upgrade-review/plan.json').is_file())
        self.assertEqual({item['run_id']:item['status'] for item in report['items']},{'old':'regeneration_required','unknown':'manual_review_required'})
        self.assertFalse(report['published'])
        self.assertEqual(report['coverage']['active_ap242_runs_skipped'],1)
        self.assertEqual(report['coverage']['unsuccessful_ap242_runs_skipped'],1)
        registry.put.assert_not_called();registry.delete.assert_not_called()

    def test_inventory_cap_is_explicit(self):
        from backend.depo_platform.ontology_upgrade import review_ceim_mappings
        registry=MagicMock();registry.page.return_value=(1000,[{'run_id':'a','source_standard':'qif'}])
        with tempfile.TemporaryDirectory() as folder:
            report=review_ceim_mappings(folder,store=registry,limit=1)
        self.assertTrue(report['coverage']['truncated'])
        self.assertEqual(report['coverage']['scanned_runs'],1)
