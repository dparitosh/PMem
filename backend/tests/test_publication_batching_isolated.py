import ast
import json
import logging
import time
import uuid
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from backend.depo_platform.network import bounded_timeout_seconds

class BatchTests(unittest.TestCase):
    def test_batches_remain_in_one_transaction_and_stale_cleanup_uses_revision(self):
        triples=[('urn:source'+str(i), 'urn:relation', 'urn:target'+str(i)) for i in range(1201)]
        class Graph:
            def parse(self, **kw): return self
            def __iter__(self): return iter(triples)
            def __len__(self): return len(triples)
            def __contains__(self, value): return False
            def subject_objects(self, *a): return []
            def subjects(self, *a): return []
            def objects(self, *a): return []
        calls=[]
        transactions=[]
        tx=SimpleNamespace(run=lambda query,**kw: (calls.append((query,kw)) or SimpleNamespace(consume=lambda:None)))
        def write(fn): transactions.append(fn); fn(tx)
        driver=SimpleNamespace(session=lambda **kw:nullcontext(SimpleNamespace(execute_write=write)))
        publisher=SimpleNamespace(auth_mode='none', _driver=lambda:nullcontext(driver), database='test')
        scope=dict(graph_publication=lambda fn:fn, ontology_writer=lambda fn:fn, unit_of_work=lambda **kw:lambda fn:fn,
            bounded_timeout_seconds=bounded_timeout_seconds, prepare_rdf=lambda *a,**kw:Graph(), Graph=Graph, Literal=type('Literal',(),{}), URIRef=str,
            to_canonical_graph=lambda graph:graph, RDF=SimpleNamespace(type='type'),
            OWL=SimpleNamespace(Class='class',ObjectProperty='op',DatatypeProperty='dp'),
            RDFS=SimpleNamespace(label='label',comment='comment',subClassOf='subclass',domain='domain',range='range'),
            Any=object, json=json, logging=logging,time=time,uuid=uuid,datetime=datetime,timezone=timezone)
        tree=ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='publish_turtle')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<publisher>','exec'),scope)
        with self.assertLogs(level='WARNING'):
            result=scope['publish_turtle'](publisher,content=b'ttl',ontology_id='demo',prefix='d',publication_id='receipt')
        self.assertEqual(len(transactions),1)
        self.assertEqual(result['resources'],2402)
        self.assertEqual(result['relationships'],1201)
        batches=[params['rows'] for query,params in calls if 'rows' in params]
        self.assertEqual([len(rows) for rows in batches],[1000,1000,402,1000,201])
        cleanup=next((query,params) for query,params in calls if 'REMOVE node:OntologyResource' in query)
        self.assertNotIn('$iris',cleanup[0])
        self.assertIn('publication_revision',cleanup[0])
        markers={params['projection_revision'] for query,params in calls if 'projection_revision' in params}
        self.assertEqual(len(markers),1)
