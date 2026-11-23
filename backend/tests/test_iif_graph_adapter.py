import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock
import pytest

PATH=Path(__file__).resolve().parents[2]/'integrations/iif/AgentsRegistry/CodedTools/eif_dt_graph.py'
spec=importlib.util.spec_from_file_location('nexus_iif_test',PATH);adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
BASE={'ontology_id':'scope','publication_id':'receipt','algorithm':'pagerank','predicates':['urn:uses']}

@pytest.fixture
def intent(tmp_path,monkeypatch):
 p=tmp_path/'intent.json';p.write_text(json.dumps(BASE));monkeypatch.setenv('NEXUS_GRAPH_INTENT_FILE',str(p));monkeypatch.setenv('NEXUS_GRAPH_READ_TOKEN','test-only');return p

@pytest.mark.parametrize('change',[{'algorithm':'svd++'},{'top_n':True},{'predicates':[]},{'predicates':['p','p']},{'ontology_id':[]},{'query':'MATCH(n)'},{'algorithm':'traceability'}])
def test_iif_intent_cannot_expand_to_arbitrary_tools(intent,change):
 intent.write_text(json.dumps({**BASE,**change}))
 with pytest.raises((ValueError,TypeError)):adapter.selected_intent()

def test_model_cannot_supply_arguments_or_credentials(intent):
 with pytest.raises(TypeError):adapter.eif_dt_compute_selected_graph(ontology_id='other')
 with pytest.raises(TypeError):adapter.eif_dt_compute_selected_graph(token='secret')

@pytest.mark.parametrize('url',['http://example.org/api/v1','https://user:pass@example.org/api/v1','https://example.org/api/v1?token=bad','file:///api/v1','https://example.org/arbitrary'])
def test_remote_transport_security(intent,monkeypatch,url):
 monkeypatch.setenv('NEXUS_GRAPH_SERVICE_URL',url)
 with pytest.raises(ValueError):adapter.eif_dt_compute_selected_graph()

def test_response_identity_is_checked_and_only_fixed_post_is_used(intent,monkeypatch):
 selected=adapter.selected_intent()
 response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock()
 body={'parameters':selected,'ontology_id':'scope','publication_id':'receipt','advisory_only':True,'approval_granted':False,'projection_digest':'f'*64}
 response.read.return_value=json.dumps(body).encode()
 opener=Mock();opener.open.return_value=response;monkeypatch.setattr(adapter,'build_opener',lambda *_:opener)
 assert adapter.eif_dt_compute_selected_graph()['controller']=='IIF'
 request=opener.open.call_args.args[0]
 assert request.full_url=='http://127.0.0.1:8013/api/v1/graph/computation' and request.method=='POST'
 assert json.loads(request.data)==selected
 response.read.return_value=json.dumps({**body,'publication_id':'other'}).encode()
 with pytest.raises(ValueError):adapter.eif_dt_compute_selected_graph()

def test_duplicate_keys_rejected(intent):
 intent.write_text('{"algorithm":"pagerank","algorithm":"node-similarity"}')
 with pytest.raises(ValueError):adapter.selected_intent()


def test_iif_triangle_count_uses_operator_intent_without_a_seed(intent):
 intent.write_text(json.dumps({**BASE,'algorithm':'triangle-count'}))
 assert adapter.selected_intent()['algorithm']=='triangle-count'
 intent.write_text(json.dumps({**BASE,'algorithm':'triangle-count','node_id':'a'}))
 with pytest.raises(ValueError):adapter.selected_intent()
