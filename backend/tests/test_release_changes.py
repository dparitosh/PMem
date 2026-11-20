from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import Mock
import pytest
from fastapi import HTTPException,FastAPI
from fastapi.testclient import TestClient
from rdflib import Graph,URIRef
from rdflib.namespace import RDF
from backend.mesh_store import InMemoryRegistry,PostgresRegistry
from backend.artifact_store import ArtifactStore
from backend.depo_platform import release_chain as chain
from backend.oslc_service import release_changes as release
from backend.depo_platform.bridge_contract import digest
from backend.depo_platform.request_bodies import ReleaseChangeSubmission,ReleaseChangeCommand
from backend.depo_platform.authorization import graph_read_identity

class Store(InMemoryRegistry):
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))
    def put_many(self,values):return super().put_many(deepcopy(values))

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('ARTIFACT_STORAGE',str(tmp_path/'artifacts'))
    stores={name:Store(name) for name in [chain.NAMESPACE,*chain.FAMILIES.values()]}
    monkeypatch.setattr(chain,'registry',lambda:stores[chain.NAMESPACE]);monkeypatch.setattr(chain,'PostgresRegistry',lambda name:stores[name])
    tracking={'stream_id':'stream-a','order':1};monkeypatch.setattr(chain,'tracking_snapshot',lambda:deepcopy(tracking))
    artifact=ArtifactStore().ingest_bytes(b'{"entities":[],"relationships":[]}',filename='accepted.json',kind='accepted-semantic-partition',media_type='application/json')
    plan={'run_id':'run','intent':{'ontology_id':'parts','batch_digest':'sha256:batch'}}
    pipeline={'run_id':'run','job_id':'job','job_version':'1','status':'completed','job_type':'validate-semantic-batch',
        'input_manifest':{'payload_digest':'sha256:source'},'output_manifest':{'partition_artifacts':{'accepted':artifact['artifact_id']}},
        'change_request':{'request_id':'run','state':'submitted','plan':plan,'plan_digest':digest(plan),'revision':1,'order':None,'history':[]}}
    product={'kind':'release_change','request_id':'product:1','product_id':'product','version':'1','name':'Engineering release','plan_digest':'a'*64,
        'publication':{'sources':[{'run_id':'run'}],'artifacts':[{'artifact_id':artifact['artifact_id']}]},
        'change_request':{'request_id':'product:1','state':'submitted','plan_digest':'a'*64,'revision':1,'order':None,'history':[]}}
    stores['data_job_runs'].put('run',pipeline);stores['data_product_approvals'].put('request:product:1',product)
    monkeypatch.setattr(chain,'confirm',lambda step:chain.retained_receipt(step))
    body=ReleaseChangeSubmission(title='Engineering source to release',reason='Release retained engineering evidence',source_run_id='run',operations=[{'source_kind':'pipeline','identifier':'run'},{'source_kind':'product_changes','identifier':'product:1'}])
    return stores,body,tracking


def create(setup):return release.create(setup[1],'requester')
def act(identifier,action,reason=''):
    value=release.view(identifier)
    return release.transition(identifier,ReleaseChangeCommand(action=action,expected_revision=value['revision'],configuration_id=value['configuration_id'],reason=reason),'reviewer')

def complete_pipeline(stores):
    value=stores['data_job_runs'].get('run');c=value['change_request'];c['state']='executed'
    c['order']={'order_id':'run','plan_digest':c['plan_digest'],'operation':'publish_accepted_partition','publish':True,'authorized_by':'native-reviewer'}
    c['receipt']={'publication_id':'run','ontology_id':'parts','current':True}
    publication={'status':'published','ontology_id':'parts','publication_id':'run'}
    value['output_manifest'].update(publication_intent=c['plan']['intent'],publication=publication,publication_digest=__import__('backend.data_pipeline_service.run_records',fromlist=['_digest'])._digest(publication))
    stores['data_job_runs'].put('run',value)

def complete_product(stores):
    value=stores['data_product_approvals'].get('request:product:1');value['change_request']['state']='executed'
    value['change_request']['order']={'order_id':'product:1','plan_digest':'a'*64,'operation':'publish_product_version','publish':True,'authorized_by':'steward'}
    value['package_receipt']={'product_version':'product:1','publication_digest':'a'*64,'status':'published','catalog_registered_at':'retained-time'}
    stores['data_product_approvals'].put('request:product:1',value)


def test_one_cr_binds_scope_order_and_final_release_with_native_permissions_remaining(setup):
    stores,body,tracking=setup;value=create(setup);identifier=value['request_id']
    assert value['state']=='submitted' and not value['complete']
    with pytest.raises(HTTPException):chain.check('pipeline','run')
    act(identifier,'accept')
    with pytest.raises(HTTPException):chain.check('pipeline','run')
    act(identifier,'authorize');chain.check('pipeline','run')
    with pytest.raises(HTTPException):chain.check('product_changes','product:1')
    complete_pipeline(stores);chain.check('product_changes','product:1')
    with pytest.raises(HTTPException):act(identifier,'verify')
    complete_product(stores);assert act(identifier,'verify')['state']=='completed'
    assert create(setup)['request_id']==identifier  # Lost create response is idempotent even after completion.


def test_scope_change_and_parent_cancellation_block_native_execution(setup):
    stores,_,_=setup;identifier=create(setup)['request_id'];act(identifier,'accept');act(identifier,'authorize')
    value=stores['data_job_runs'].get('run');value['change_request']['plan_digest']='b'*64;stores['data_job_runs'].put('run',value)
    with pytest.raises(HTTPException):chain.check('pipeline','run')
    act(identifier,'cancel')
    with pytest.raises(HTTPException):chain.check('pipeline','run')


def test_native_guard_keeps_unlinked_compatibility_and_blocks_linked_bypass(setup,monkeypatch):
    # Preserve the production-type test independently of the in-memory native resolver.
    original_native=chain.native
    stores=setup[0]
    monkeypatch.setattr(chain,'native',lambda kind,identifier:stores[chain.FAMILIES[kind]].get('request:'+identifier if kind=='product_changes' else identifier))
    value=create(setup);called=[]
    @chain.guarded(lambda:('pipeline','run',PostgresRegistry('data_job_runs')))
    def execute():called.append(True)
    with pytest.raises(HTTPException):execute()
    assert not called


def test_stream_reset_regrown_counter_requires_rebase_and_new_authorization(setup):
    stores,_,tracking=setup;identifier=create(setup)['request_id'];act(identifier,'accept');act(identifier,'authorize')
    old=release.view(identifier)['configuration_id'];tracking.update(stream_id='stream-b',order=2000)
    assert release.view(identifier)['tracking_changed']
    with pytest.raises(HTTPException):chain.check('pipeline','run')
    rebased=act(identifier,'rebase','Review reset tracking generation')
    assert rebased['state']=='submitted' and rebased['configuration_id']!=old
    assert stores[chain.NAMESPACE].get('baseline:'+old)
    assert rebased['prior_orders'][0]['configuration_id']==old
    with pytest.raises(HTTPException):chain.check('pipeline','run')
    act(identifier,'accept');act(identifier,'authorize');chain.check('pipeline','run')


def test_source_or_operation_substitution_cannot_be_hidden_by_rebase(setup):
    stores,_,_=setup;identifier=create(setup)['request_id'];act(identifier,'accept');act(identifier,'authorize')
    value=stores['data_job_runs'].get('run');value['input_manifest']['payload_digest']='changed';stores['data_job_runs'].put('run',value)
    with pytest.raises(HTTPException):act(identifier,'rebase')
    with pytest.raises(HTTPException):chain.check('pipeline','run')


def test_stale_reviewer_and_configuration_context_are_rejected(setup):
    value=create(setup);identifier=value['request_id'];act(identifier,'accept')
    payload=ReleaseChangeCommand(action='authorize',expected_revision=value['revision'],configuration_id=value['configuration_id'])
    with pytest.raises(HTTPException):release.transition(identifier,payload,'other')
    current=release.view(identifier);payload=payload.model_copy(update={'expected_revision':current['revision']})
    with pytest.raises(HTTPException):release.transition(identifier,payload,'other','https://other/configuration')


def test_two_releases_cannot_claim_the_same_native_operation(setup):
    create(setup)
    with pytest.raises(HTTPException):release.create(setup[1].model_copy(update={'title':'Other change'}),'other')


def test_unrelated_product_and_retroactive_operations_are_rejected(setup):
    stores,_,_=setup;value=stores['data_product_approvals'].get('request:product:1');value['publication']['sources']=[];stores['data_product_approvals'].put('request:product:1',value)
    with pytest.raises(HTTPException):create(setup)
    assert not stores[chain.NAMESPACE].all()


def test_baseline_is_immutable_negotiated_and_context_scoped(setup):
    value=create(setup);app=FastAPI();app.include_router(release.router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    client=TestClient(app);uri=value['configuration_context']
    response=client.get(uri,headers={'Accept':'text/turtle'})
    assert response.status_code==200
    graph=Graph().parse(data=response.text,format='turtle')
    assert list(graph.subjects(RDF.type,URIRef('http://open-services.net/ns/config#Baseline')))
    assert client.get(uri,headers={'If-None-Match':response.headers['etag']}).status_code==304
    assert client.get(uri,headers={'Configuration-Context':'/wrong'}).status_code==409


def test_authenticated_parent_command_cannot_spoof_actor_or_approve_stale_etag(setup,monkeypatch):
    value=create(setup);app=FastAPI();app.include_router(release.router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    monkeypatch.setattr(release,'approval_identity',lambda *args,**kwargs:'verified-coordinator')
    client=TestClient(app);url='/api/v1/change-control/releases/'+value['request_id']
    body={'action':'accept','expected_revision':value['revision'],'configuration_id':value['configuration_id']}
    assert client.post(url,json={**body,'approved_by':'spoof'}).status_code==422
    assert client.post(url,json=body,headers={'If-Match':'W/"old"'}).status_code==412
    response=client.post(url,json=body)
    assert response.status_code==200 and response.json()['history'][-1]['actor']=='verified-coordinator'


def test_actual_source_bytes_cannot_change_under_a_frozen_configuration(setup):
    value=create(setup);act(value['request_id'],'accept');act(value['request_id'],'authorize')
    artifact=chain.baseline(load_record(setup,value))['selections']['source']['accepted_artifact_id']
    _,path=ArtifactStore().resolve(artifact);path.write_bytes(b'changed bytes')
    with pytest.raises(HTTPException):chain.check('pipeline','run')


def load_record(setup,value):return setup[0][chain.NAMESPACE].get(value['request_id'])


def test_parallel_evidence_reads_keep_request_context_and_order():
    from contextvars import ContextVar
    scope=ContextVar('release_test_scope');token=scope.set('retained-operation-deadline')
    try:assert chain.bounded_reads(lambda item:(item,scope.get()),[3,1,2])==[(3,'retained-operation-deadline'),(1,'retained-operation-deadline'),(2,'retained-operation-deadline')]
    finally:scope.reset(token)



def test_configuration_collection_advertises_only_retained_baselines(setup,monkeypatch):
    value=create(setup)
    app=FastAPI();app.include_router(release.router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    with TestClient(app) as client:
        response=client.get('/oslc/change-control/configurations',headers={'Accept':'application/json'})
        assert response.status_code==200
        body=response.json();assert body['total']==1 and len(body['members'])==1
        assert body['members'][0]['configuration_id']==value['configuration_id']
        assert body['members'][0]['type']=='oslc_config:Baseline'
        assert client.get('/oslc/change-control/configurations?limit=101').status_code==422



def test_configuration_uses_standard_selects_resource_links_in_rdf(setup):
    from backend.oslc_service.representation import rdf_graph
    value=create(setup)
    app=FastAPI();app.include_router(release.router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    with TestClient(app) as client:
        path='/oslc/change-control/configurations/'+value['configuration_id']
        baseline=client.get(path).json()
        selected=client.get(path+'/selections').json()
        assert len(selected['oslc_config:selects'])==3
        assert 'oslc_config:versionResource' not in selected
        graph=rdf_graph(selected)
        predicate=URIRef('http://open-services.net/ns/config#selects')
        assert len(list(graph.objects(URIRef(selected['uri']),predicate)))==3
        assert baseline['oslc_config:selections']['oslc_config:selects']==selected['oslc_config:selects']
        shape=client.get('/oslc/change-control/configuration-shape').json()
        assert shape['describes']==['http://open-services.net/ns/config#Baseline']
