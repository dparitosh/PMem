import ast
import asyncio
import json
import logging
import os
import re
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch
from unittest.mock import MagicMock
from urllib.parse import urlsplit


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    async def aiter_bytes(self): yield json.dumps(self.payload).encode()


class Client:
    payload = {}
    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def stream(self, *args, **kwargs):
        class Context:
            async def __aenter__(_): return Response(Client.payload)
            async def __aexit__(_, *args): pass
        return Context()


def load_class(path, name, scope):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),path,'exec'),scope)
    return scope[name]


class TransportBoundaryTests(unittest.TestCase):
    def scope(self):
        from backend.agentic_service.response_limits import read_bounded_response
        return dict(__name__='backend.agentic_service.companion',__package__='backend.agentic_service',
                    os=os,re=re,json=json,asyncio=asyncio,logging=logging,Any=Any,urlsplit=urlsplit,
                    httpx=SimpleNamespace(AsyncClient=Client,HTTPError=RuntimeError),
                    bounded_timeout_seconds=lambda *args,**kwargs:15,read_bounded_response=read_bounded_response)

    def test_oslc_empty_or_unidentified_resources_are_not_evidence(self):
        service=load_class('backend/agentic_service/oslc_graph_rag.py','OSLCGraphRAG',self.scope())()
        Client.payload={'results':[{}, {'title':'Missing ID'}, {'id':'urn:p','title':'Pump'}]}
        with patch.dict(os.environ,{'OSLC_REMOTE_BASE_URL':'https://oslc.example'}):
            result=asyncio.run(service.retrieve('pump'))
        self.assertEqual(result['resource_ids'],['urn:p'])
        self.assertEqual(len(result['evidence']),1)
        Client.payload={'results':[{}]}
        with patch.dict(os.environ,{'OSLC_REMOTE_BASE_URL':'https://oslc.example'}):
            self.assertFalse(asyncio.run(service.retrieve('pump'))['answerable'])

    def test_oslc_rejects_credentials_in_url(self):
        service=load_class('backend/agentic_service/oslc_graph_rag.py','OSLCGraphRAG',self.scope())()
        with patch.dict(os.environ,{'OSLC_REMOTE_BASE_URL':'https://user:password@oslc.example'}), self.assertRaises(RuntimeError):
            service._base()

    def test_embedding_reader_advances_bounded_pages_lazily(self):
        tree=ast.parse(Path('backend/Services/graph_embeddings.py').read_text())
        names={'VISIBLE_SOURCE','FETCH_QUERY'}
        nodes=[n for n in tree.body if (isinstance(n,ast.FunctionDef) and n.name=='fetch_graph_nodes')
               or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets))]
        scope=dict(NEO4J_DATABASE='neo4j',MAX_RELS_PER_CHUNK=40,Query=lambda text,timeout:SimpleNamespace(text=text,timeout=timeout))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<embedding-reader>','exec'),scope)
        driver=MagicMock()
        session=driver.session.return_value.__enter__.return_value
        session.run.side_effect=[[{'eid':'a'},{'eid':'b'}],[{'eid':'c'}],[]]
        rows=scope['fetch_graph_nodes'](driver)
        self.assertEqual(next(rows)['eid'],'a')
        self.assertEqual(session.run.call_count,1)
        self.assertEqual([row['eid'] for row in rows],['b','c'])
        self.assertEqual([call.kwargs['after'] for call in session.run.call_args_list],['','b','c'])
        for call in session.run.call_args_list:
            self.assertEqual(call.args[0].timeout,30)
            self.assertEqual(call.kwargs['page_size'],100)
            for label in ('StagedOntologyResource','RetainedOntologyIdentity','OntologyPublication'):
                self.assertIn('NOT n:'+label,call.args[0].text)
                self.assertIn('NOT m:'+label,call.args[0].text)

    def test_companion_preserves_predicates_and_closed_evidence_edges(self):
        service=load_class('backend/agentic_service/companion.py','KnowledgeCompanion',self.scope())()
        service._graph_root=lambda:'http://graph/api/v1'
        Client.payload={'nodes':[{'elementId':str(i),'properties':{'label':'Pump','search_score':10-i}} for i in range(9)],
                        'relationships':[{'start':'0','end':'8','type':'SEMANTIC_RELATION'},
                                         {'start':'0','end':'1','type':'SEMANTIC_RELATION','properties':{'predicate':'urn:hasPart'}}]}
        with patch.dict(os.environ,{'COMPANION_LLM_ENABLED':'false'}):
            # Descriptive property helper is defined outside the production class.
            service_scope=service.ask.__func__.__globals__
            service_scope['descriptive_properties']=lambda properties:{}
            result=asyncio.run(service.ask('pump',headers={}))
        edges=[e for e in result['evidence'] if e['evidence_type']=='graph_relationship']
        self.assertEqual(len(edges),1)
        self.assertEqual(edges[0]['relationship'],'urn:hasPart')

    def test_missing_graph_index_does_not_disable_document_index_and_can_recover(self):
        tree=ast.parse(Path('backend/chains/vector.py').read_text())
        fn=next(n for n in tree.body if getattr(n,'name','')=='_initialize_vectors')
        clock=SimpleNamespace(monotonic=lambda:0)
        scope=dict(LLM_AVAILABLE=True,EMBEDDER_AVAILABLE=True,time=clock,_vector_retry_at=0,
                   _vector_init_lock=threading.Lock(),logger=Mock(),embeddings=object(),graph=object(),
                   GRAPH_VECTOR_INDEX='graph',GRAPH_KEYWORD_INDEX='graph-keyword',DATASHEET_VECTOR_INDEX='docs',
                   DATASHEET_KEYWORD_INDEX='docs-keyword',llm=object(),general_prompt=object(),data_prompt=object(),
                   create_stuff_documents_chain=Mock(return_value=Mock()),create_retrieval_chain=Mock(return_value=Mock()))
        for key in ('general_vector','general_retriever','general_qa_chain','general_retrieval_chain','datasheet_vector','datasheet_retriever','data_qa_chain','data_retrieval_chain'): scope[key]=None
        store=Mock()
        def build(*args,**kwargs):
            if kwargs['index_name']=='graph' and clock.monotonic()==0: raise RuntimeError('missing')
            return store
        scope['Neo4jVector']=SimpleNamespace(from_existing_index=build)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<vector-init>','exec'),scope)
        scope['_initialize_vectors']()
        self.assertIsNone(scope['general_qa_chain'])
        documents=scope['data_qa_chain']
        self.assertIsNotNone(documents)
        clock.monotonic=lambda:31
        scope['_initialize_vectors']()
        self.assertIsNotNone(scope['general_qa_chain'])
        self.assertIs(scope['data_qa_chain'],documents)
