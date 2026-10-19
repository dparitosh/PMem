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
