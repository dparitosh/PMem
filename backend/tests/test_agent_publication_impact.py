import ast
import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.agentic_service.tool_timeouts import tool_timeout_seconds
from backend.agentic_service.workflow_receipts import verify_ontology_publication

class ImpactTests(unittest.TestCase):
    def receipt(self):
        return {'status':'published','ontology_id':'merged','publication_id':'digest','artifact_sha256':'digest',
                'receipt':{'status':'published','ontology_id':'merged','publication_id':'digest','current':True,'resources':10,'relationships':4}}

    def test_merge_publication_has_time_for_preparation_and_dispatch(self):
        with patch.dict('os.environ',{'AGENTIC_TOOL_TIMEOUT_SECONDS':'30','GRAPH_PUBLICATION_TIMEOUT_SECONDS':'180'}):
            self.assertEqual(tool_timeout_seconds({'id':'ontology.merge.apply'},{'publish':True}),390)
            self.assertEqual(tool_timeout_seconds({'id':'ontology.merge.apply'},{'publish':False}),30)
            self.assertEqual(tool_timeout_seconds({'id':'ontology.export'},{}),30)

    def test_current_receipt_passes(self):
        self.assertEqual(verify_ontology_publication('merged',self.receipt())['status'],'published')

    def test_stale_wrong_or_missing_receipt_fails(self):
        for field, value in [('current',False),('ontology_id','other'),('publication_id','other'),('resources',True),('relationships',-1),('status','publishing')]:
            record=self.receipt(); record['receipt'][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): verify_ontology_publication('merged',record)
        with self.assertRaises(ValueError): verify_ontology_publication('merged',{'status':'published','ontology_id':'merged'})
        record=self.receipt(); record['artifact_sha256']='different'
        with self.assertRaises(ValueError): verify_ontology_publication('merged',record)

    def test_stale_bridge_target_aborts_before_link_writes(self):
        tree=ast.parse(Path('backend/graph_service/bridge_publication.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_publish_transaction')
        scope={'json':json,'datetime':datetime,'timezone':timezone}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<bridge>','exec'),scope)
        calls=[]
        def run(query,**kwargs):
            calls.append(query)
            if len(calls)==1: return SimpleNamespace(single=lambda:{'receipt':None})
            return SimpleNamespace(data=lambda:[{'candidate_id':'c','sources':1,'targets':0}])
        command={'publication_id':'p','request_digest':'d','rows':[{'candidate_id':'c'}]}
        with self.assertRaises(ValueError): scope['_publish_transaction'](SimpleNamespace(run=run),command)
        self.assertEqual(len(calls),2)
        self.assertIn('NOT target:RetainedOntologyIdentity',calls[1])
        self.assertIn('row.target_ontology_type',calls[1])
        write_query=next(node.value for node in ast.walk(fn) if isinstance(node,ast.Constant) and isinstance(node.value,str) and 'MERGE (n)-[bridge' in node.value)
        self.assertIn('NOT target:RetainedOntologyIdentity',write_query)
