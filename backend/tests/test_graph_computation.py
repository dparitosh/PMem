import copy
from contextlib import nullcontext
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from backend.graph_service.computation import ComputationRequest, calculate, snapshot

BASE={'ontology_id':'scope','publication_id':'published','algorithm':'pagerank','predicates':['urn:uses']}
NODES=[{'id':n,'iri':'urn:'+n,'name':n,'labels':['Part'],'rdf_types':[]} for n in ('a','b','c','d')]
EDGES=[{'source':'a','target':'b','predicate':'urn:uses'},{'source':'c','target':'b','predicate':'urn:uses'},{'source':'c','target':'d','predicate':'urn:uses'}]
RECEIPT={'publication_id':'published','artifact_sha256':'f'*64}

@pytest.mark.parametrize('change',[{'algorithm':'svd++'},{'algorithm':[]},{'predicates':[]},{'predicates':['p','p']},{'top_n':True},{'top_n':51},{'cypher':'MATCH(n) DELETE n'},{'node_id':'a'},{'algorithm':'node-similarity'}])
def test_strict_selected_contract(change):
 with pytest.raises(ValidationError): ComputationRequest(**{**BASE,**change})

def test_pagerank_is_bounded_deterministic_and_advisory():
 request=ComputationRequest(**{**BASE,'top_n':2})
 result=calculate(request,NODES,EDGES,RECEIPT)
 assert len(result['results'])==2 and result['results'][0]['node_id']=='b'
 assert result['approval_granted'] is False and result['advisory_only'] is True
 assert result['coverage']['whole_enterprise_complete'] is False
 assert result['projection_digest']==calculate(request,NODES,EDGES,RECEIPT)['projection_digest']
 assert result['projection_digest']!=calculate(request,NODES,EDGES,{**RECEIPT,'artifact_sha256':'e'*64})['projection_digest']

def test_similarity_preserves_direction_and_predicate():
 request=ComputationRequest(**{**BASE,'algorithm':'node-similarity','node_id':'a'})
 edges=[*EDGES,{'source':'d','target':'b','predicate':'urn:different'}]
 result=calculate(request,NODES,edges,RECEIPT)
 assert [r['node_id'] for r in result['results']]==['c']
 assert result['results'][0]['score']==0.5
 assert result['results'][0]['shared_features']==[['out','urn:uses','b']]

def test_personalized_rank_and_no_invented_triangle_requirement():
 request=ComputationRequest(**{**BASE,'algorithm':'personalized-pagerank','node_id':'a'})
 assert calculate(request,NODES,EDGES,RECEIPT)['results']
 request=ComputationRequest(**{**BASE,'algorithm':'traceability','node_id':'a'})
 result=calculate(request,NODES,EDGES,RECEIPT)
 assert result['results'][0]['edges'][0]['source']=='a'
 assert 'satisfaction' in result['interpretation'] and result['approval_granted'] is False

def test_unknown_types_do_not_become_traceability_roles():
 request=ComputationRequest(**{**BASE,'algorithm':'traceability','node_id':'a'})
 nodes=[{**n,'labels':[]} for n in NODES]
 assert calculate(request,nodes,EDGES,RECEIPT)['results']==[]

class Tx:
 def __init__(self,receipts=None,nodes=None,edges=None):self.responses=iter([receipts if receipts is not None else [RECEIPT],nodes if nodes is not None else NODES,edges if edges is not None else EDGES]);self.calls=[];self.rolled=False
 def run(self,query,**params):self.calls.append((query,params));return Mock(data=lambda:next(self.responses))
 def commit(self):pass
 def rollback(self):self.rolled=True

def publisher(tx):
 session=Mock();session.begin_transaction.return_value=tx
 return Mock(database='test',_driver=lambda:nullcontext(Mock(session=lambda **_:nullcontext(session))))

@pytest.mark.parametrize('receipts',[[],[RECEIPT,RECEIPT],[{**RECEIPT,'publication_id':'changed'}]])
def test_stale_or_ambiguous_publications_fail_closed(receipts):
 tx=Tx(receipts=receipts)
 with pytest.raises(ValueError):snapshot(publisher(tx),ComputationRequest(**BASE))
 assert tx.rolled

def test_projection_caps_fail_instead_of_silent_sampling():
 tx=Tx(nodes=NODES*251)
 with pytest.raises(ValueError):snapshot(publisher(tx),ComputationRequest(**BASE))
 tx=Tx(edges=EDGES*1667)
 with pytest.raises(ValueError):snapshot(publisher(tx),ComputationRequest(**BASE))
 assert tx.rolled

def test_queries_bind_user_values_and_require_business_scope():
 tx=Tx();request=ComputationRequest(**{**BASE,'predicates':["urn:malicious' DELETE n"]})
 snapshot(publisher(tx),request)
 assert all("DELETE n" not in query for query,_ in tx.calls)
 assert 'n.ontology_id=$scope' in tx.calls[1][0]
 assert 'StagedOntologyResource' in tx.calls[1][0]
 assert tx.calls[2][1]['predicates']==request.predicates


def test_retained_evidence_is_idempotent_and_time_does_not_change_identity():
 from backend.graph_service.computation import retain
 from backend.mesh_store import InMemoryRegistry
 result=calculate(ComputationRequest(**BASE),NODES,EDGES,RECEIPT)
 store=InMemoryRegistry()
 first=retain(result,store)
 assert retain({**result,'computed_at':'later'},store)==first
 assert len(first['evidence_id'])==64
 assert first['currentness'].startswith('retained snapshot')


def test_gds_adapter_passes_nested_parameters_and_cleans_up():
 from backend.graph_service.gds_computation import pagerank
 calls=[]
 class Session:
  def run(self,query,parameters=None,**kwargs):
   text=str(query);params=parameters or kwargs;calls.append((text,params))
   if 'SHOW FUNCTIONS' in text:return Mock(data=lambda:[{'name':'gds.version'}])
   if 'gds.version()' in text:return Mock(data=lambda:[{'version':'test'}])
   if 'project.cypher' in text:
    assert params['parameters']['ids']==['a','b','c','d']
    assert '$ids' in params['nodes']
    return Mock(data=lambda:[{'nodeCount':4,'relationshipCount':3}])
   if 'estimate' in text:return Mock(data=lambda:[{'bytesMax':1000}])
   if 'pageRank.stream' in text:return Mock(data=lambda:[{'node_id':'b','score':0.5}])
   return Mock(consume=lambda:None)
 session=Session();p=Mock(database='test',_driver=lambda:nullcontext(Mock(session=lambda **_:nullcontext(session))))
 ranked,engine=pagerank(p,ComputationRequest(**BASE),NODES)
 assert engine['name']=='neo4j-gds' and ranked[0]['node_id']=='b'
 assert 'gds.graph.drop' in calls[-1][0]
 assert all('SET ' not in query and 'DELETE ' not in query for query,_ in calls)


def test_catalog_exposes_only_read_graph_computation():
 import json
 from pathlib import Path
 from backend.agentic_service.catalog_contract import validate_catalog
 data=validate_catalog(json.loads((Path(__file__).parents[1]/'agentic_service/catalog.json').read_text()))
 tool=next(t for t in data['tools'] if t['id']=='graph.computation')
 assert tool['service']=='graph' and tool['mutates'] is False and tool['path']=='/graph/computation'
 assert tool['id'] in next(a for a in data['agents'] if a['id']=='graph-analyst')['tools']


@pytest.mark.parametrize('fail_phase',['estimate','pageRank.stream'])
def test_gds_failures_still_drop_private_projection(fail_phase):
 from backend.graph_service.gds_computation import pagerank
 calls=[]
 class Session:
  def run(self,query,parameters=None,**kwargs):
   text=str(query);calls.append(text)
   if 'SHOW FUNCTIONS' in text:return Mock(data=lambda:[{'name':'gds.version'}])
   if 'gds.version()' in text:return Mock(data=lambda:[{'version':'test'}])
   if fail_phase in text:raise RuntimeError('controlled algorithm failure')
   if 'estimate' in text:return Mock(data=lambda:[{'bytesMax':1000}])
   return Mock(data=lambda:[{}],consume=lambda:None)
 p=Mock(database='test',_driver=lambda:nullcontext(Mock(session=lambda **_:nullcontext(Session()))))
 with pytest.raises(RuntimeError):pagerank(p,ComputationRequest(**BASE),NODES)
 assert 'gds.graph.drop' in calls[-1]


def test_rest_contract_rejects_extra_query_and_requires_read_access(monkeypatch):
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from backend.graph_service.router import router
 from backend.depo_platform.authorization import graph_read_identity
 app=FastAPI();app.include_router(router,prefix='/api/v1')
 def denied():
  from fastapi import HTTPException
  raise HTTPException(403,'read grant required')
 app.dependency_overrides[graph_read_identity]=denied
 client=TestClient(app)
 assert client.post('/api/v1/graph/computation',json=BASE).status_code==403
 app.dependency_overrides[graph_read_identity]=lambda:'test-reader'
 assert client.post('/api/v1/graph/computation',json={**BASE,'cypher':'MATCH(n)'}).status_code==422
 schema=app.openapi()['components']['schemas']['ComputationRequest']
 assert schema['additionalProperties'] is False
 assert set(schema['required'])=={'ontology_id','publication_id','algorithm','predicates'}


def test_triangle_count_uses_simple_undirected_structure_without_business_claims():
 request=ComputationRequest(**{**BASE,'algorithm':'triangle-count','top_n':2})
 edges=[{'source':'a','target':'b','predicate':'urn:uses'},
        {'source':'b','target':'c','predicate':'urn:uses'},
        {'source':'c','target':'a','predicate':'urn:uses'},
        {'source':'b','target':'a','predicate':'urn:uses'},
        {'source':'a','target':'a','predicate':'urn:uses'}]
 result=calculate(request,NODES,edges,RECEIPT)
 assert result['global_triangle_count']==1
 assert result['orientation']=='undirected'
 assert [row['triangle_count'] for row in result['results']]==[1,1]
 assert result['results_limited'] is True
 assert result['engine']['name']=='networkx'
 assert result['approval_granted'] is False
 assert 'not traceability completeness' in result['interpretation']
 assert result['projection_digest']==calculate(request,NODES,edges,RECEIPT)['projection_digest']


def test_triangle_free_graph_and_isolates_have_zero_counts():
 request=ComputationRequest(**{**BASE,'algorithm':'triangle-count'})
 result=calculate(request,NODES,EDGES,RECEIPT)
 assert result['global_triangle_count']==0
 assert all(row['triangle_count']==0 for row in result['results'])
 with pytest.raises(ValidationError):ComputationRequest(**{**BASE,'algorithm':'triangle-count','node_id':'a'})


def test_named_options_are_publication_scoped_and_bounded():
 from backend.graph_service.computation import options
 tx=Tx(receipts=[{'ontology_id':'scope','publication_id':'published','name':'Drive assembly'}],nodes=[{'node_id':'a','name':'Bearing'}],edges=[{'predicate':'urn:uses'}])
 result=options(publisher(tx),'scope')
 assert result['nodes'][0]['name']=='Bearing' and result['predicates']==['urn:uses']
 assert all(params['scope']=='scope' for _,params in tx.calls)
 assert 'LIMIT 1001' in tx.calls[1][0] and 'LIMIT 101' in tx.calls[2][0]


def test_named_options_reject_ambiguous_publication():
 from backend.graph_service.computation import options
 tx=Tx(receipts=[RECEIPT,RECEIPT])
 with pytest.raises(ValueError,match='one current published'):options(publisher(tx),'scope')
 assert tx.rolled
