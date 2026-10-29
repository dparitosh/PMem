import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Graph, URIRef
from rdflib.namespace import RDF
from backend.oslc_service.change_control import collect, normalize, router
from backend.depo_platform.authorization import graph_read_identity
from backend.mesh_store import InMemoryRegistry, PostgresRegistry


@pytest.mark.parametrize('kind,record',[
    ('pipeline',{'run_id':'r','job_id':'definition','status':'completed'}),
    ('bridges',{'job_id':'b','status':'completed','governance':{'overall_verdict':'APPROVED'}}),
    ('merges',{'preview_id':'p','publish_recommended':True}),
])
def test_success_or_policy_pass_never_implies_authorization(kind,record):
    result=normalize(kind,record)
    assert result['review_state']!='Authorization retained'
    assert result['delivery_state']=='Not verified'
    assert 'token' not in str(result)


def test_pipeline_identity_is_run_not_definition_and_secrets_are_not_projected():
    value=normalize('pipeline',{'run_id':'run-1','job_id':'job-definition','status':'failed',
                              'approval_token':'PRIVATE','error':'password=PRIVATE','turtle':'PRIVATE'})
    assert value['identifier']=='run-1' and value['workspace']=='#/data-flow/run-1'
    assert value['needs_attention'] and 'PRIVATE' not in str(value)


def test_merge_application_does_not_imply_graph_delivery():
    value=normalize('merges',{'preview_id':'p','approved_by':'service-actor','applied_result':{'ontology_id':'o'}})
    assert value['review_state']=='Authorization retained'
    assert value['execution_state']=='Applied to registry' and value['delivery_state']=='Not verified'


def test_mismatched_publication_receipt_is_not_reported_as_retained_delivery():
    record={'ontology_id':'a','artifact_sha256':'sha','approved_by':'actor','status':'published',
            'result':{'ontology_id':'b','publication_id':'sha'}}
    assert normalize('publications',record)['delivery_state']=='Not verified'
    record['result']['ontology_id']='a'
    assert normalize('publications',record)['receipt_retained'] is True


def test_product_pending_catalog_is_distinct_from_authorization():
    value=normalize('products',{'product_id':'p','version':'1','approved_by':'actor','status':'pending_catalog_registration'})
    assert value['review_state']=='Authorization retained' and value['delivery_state']=='Catalog delivery pending'


def test_approved_lesson_is_advisory_not_publication_authority():
    value=normalize('learning',{'lesson_id':'lesson-1','status':'approved','reviewed_by':'steward'})
    assert value['review_state']=='Advisory lesson approved'
    assert value['authorization_kind']=='Advisory review; no publication authority'
    assert value['delivery_state']=='Not verified'


def test_history_paging_keeps_older_records_accessible():
    store=InMemoryRegistry()
    for i in range(3):store.put(str(i),{'run_id':str(i)})
    result=collect('pipeline',limit=1,registry_factory=lambda namespace:store)
    next_page=collect('pipeline',limit=1,offset=1,registry_factory=lambda namespace:store)
    assert result['has_more'] and result['records'][0]['record_key']!=next_page['records'][0]['record_key']


def test_partial_sources_are_visible_and_reads_do_not_write():
    stores={}
    def factory(namespace):
        if namespace=='data_products': raise RuntimeError('secret DSN')
        stores.setdefault(namespace,InMemoryRegistry())
        return stores[namespace]
    factory('data_job_runs').put('r',{'run_id':'r','status':'completed'})
    result=collect(registry_factory=factory)
    assert result['partial'] and result['read_only'] and len(result['records'])==1
    assert 'secret DSN' not in str(result)
    assert stores['data_job_runs'].get('r')=={'run_id':'r','status':'completed'}


def client(monkeypatch,authorized=True):
    app=FastAPI();app.include_router(router)
    if authorized:app.dependency_overrides[graph_read_identity]=lambda:'reader'
    monkeypatch.setattr(PostgresRegistry,'page',lambda self,**kwargs:(1,[{'preview_id':'p','ontology_name':'Merge'}]) if self.namespace=='ontology_merge_previews' else (0,[]))
    monkeypatch.setattr(PostgresRegistry,'get',lambda self,key:{'preview_id':'p','ontology_name':'Merge'} if key=='p' else None)
    return TestClient(app)


def test_http_json_rdf_and_input_contract(monkeypatch):
    monkeypatch.setenv('OSLC_ENABLED','true')
    c=client(monkeypatch)
    response=c.get('/api/v1/change-control/records');assert response.status_code==200
    assert response.json()['records'][0]['review_state']=='No authorization recorded'
    assert c.get('/api/v1/change-control/records?source=unknown').status_code==422
    assert c.get('/api/v1/change-control/records?limit=500').status_code==422
    assert c.post('/api/v1/change-control/records',json={}).status_code==405
    rdf=c.get('/oslc/change-control/records/merges/p',headers={'Accept':'text/turtle'})
    assert rdf.status_code==200
    graph=Graph().parse(data=rdf.text,format='turtle')
    assert list(graph.subjects(RDF.type,URIRef('http://open-services.net/ns/cm#ChangeRequest')))
    assert c.get('/api/v1/change-control/records/merges/missing').status_code==404


def test_missing_credentials_are_rejected(monkeypatch):
    monkeypatch.setenv('GRAPH_READ_TOKEN','configured-read-token')
    monkeypatch.setenv('DEPO_ALLOW_DEMO_APPROVAL','false')
    assert client(monkeypatch,False).get('/api/v1/change-control/records').status_code in {401,403}


def test_disabled_oslc_does_not_disable_internal_change_visibility(monkeypatch):
    monkeypatch.setenv('OSLC_ENABLED','false')
    c=client(monkeypatch)
    assert c.get('/oslc/change-control/records').status_code==404
    assert c.get('/api/v1/change-control/records').status_code==200
