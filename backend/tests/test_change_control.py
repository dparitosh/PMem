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


def pipeline_publication_record():
    from backend.data_pipeline_service.run_records import _digest
    receipt={'status':'published','ontology_id':'ceim-test','publication_id':'run-test','publication':{'ontology_id':'ceim-test','publication_id':'run-test','status':'published'}}
    return {'run_id':'run-test','job_id':'validate','status':'completed','output_manifest':{'publication':receipt,'publication_intent':{'ontology_id':'ceim-test'},'publication_digest':_digest(receipt)}}


def test_pipeline_graph_receipt_is_visible_without_implying_approval_or_catalog_delivery():
    row=normalize('pipeline',pipeline_publication_record())
    assert row['delivery_state']=='Graph publication receipt retained'
    assert row['receipt_retained'] is True
    assert row['review_state']=='Evidence only; not approval'


@pytest.mark.parametrize('field,value',[('publication_id','another-run'),('ontology_id','another-scope'),('status','pending')])
def test_pipeline_foreign_or_unfinished_receipt_is_not_reported_as_delivery(field,value):
    from backend.data_pipeline_service.run_records import _digest
    record=pipeline_publication_record();record['output_manifest']['publication'][field]=value
    record['output_manifest']['publication_digest']=_digest(record['output_manifest']['publication'])
    assert normalize('pipeline',record)['receipt_retained'] is False


def test_pipeline_tampered_receipt_fails_digest_validation():
    record=pipeline_publication_record();record['output_manifest']['publication']['extra']='changed'
    assert normalize('pipeline',record)['receipt_retained'] is False


def test_pipeline_summary_projection_preserves_native_publication_evidence():
    from backend.oslc_service.change_control import restore_summary,SUMMARY_PROJECTION
    record=pipeline_publication_record();output=record['output_manifest']
    summary={'run_id':record['run_id'],'status':record['status'],'pipeline_publication':output['publication'],'pipeline_publication_intent':output['publication_intent'],'pipeline_publication_digest':output['publication_digest']}
    assert SUMMARY_PROJECTION['pipeline_publication']==['output_manifest','publication']
    assert normalize('pipeline',restore_summary(summary))['receipt_retained'] is True


def merge_dossier_fixture():
    return {'preview_id':'p','ontology_name':'Assembly terminology merge','source_ontology_ids':['a','b'],
        'sources':[{'ontology_id':'a','ontology_name':'PLM vocabulary','artifact_sha256':'a'*64},
                   {'ontology_id':'b','ontology_name':'Product vocabulary','artifact_sha256':'b'*64}],
        'turtle':'<urn:private> <urn:value> "DO_NOT_EXPORT_TURTLE" .',
        'governance_policy_sha256':'c'*64,'mapping_evidence':[]}


def test_native_dossier_freezes_retained_scope_without_granting_authority():
    from backend.oslc_service.change_dossier import build_dossier
    record=merge_dossier_fixture()
    dossier=build_dossier('merges',record,normalize('merges',record),'http://local/change/p')
    assert dossier['request']['resource_type']=='oslc_cm:ChangeRequest'
    assert dossier['baseline']['status']=='Exact retained source snapshot'
    assert len(dossier['baseline']['members'])==2
    assert len(dossier['release']['plan_digest'])==64
    assert dossier['release']['native_result_linked'] is False
    assert dossier['release']['authorization_actor'] is None
    assert 'Not revalidated' in dossier['baseline']['currentness']
    assert 'grants no write permission' in dossier['release']['authority']
    assert 'DO_NOT_EXPORT_TURTLE' not in str(dossier)
    record['mapping_evidence']=[{'source':'a','target':'b'}]
    changed=build_dossier('merges',record,normalize('merges',record),'http://local/change/p')
    assert changed['release']['plan_digest']!=dossier['release']['plan_digest']


@pytest.mark.parametrize('fault',['missing','duplicate','wrong_order','missing_policy'])
def test_incomplete_baseline_cannot_claim_a_bound_release_plan(fault):
    from backend.oslc_service.change_dossier import build_dossier
    record=merge_dossier_fixture()
    if fault=='missing':record['sources'][0].pop('artifact_sha256')
    if fault=='duplicate':record['sources'][1]=dict(record['sources'][0])
    if fault=='wrong_order':record['source_ontology_ids'].reverse()
    if fault=='missing_policy':record.pop('governance_policy_sha256')
    result=build_dossier('merges',record,normalize('merges',record),'http://local/p')
    assert result['release']['plan_digest'] is None
    assert result['release']['native_result_linked'] is False


def test_native_result_must_match_the_preview_sources_and_actor():
    from backend.oslc_service.change_dossier import build_dossier
    record=merge_dossier_fixture();record['approved_by']='verified-owner'
    provenance={'preview_id':'p','source_ontology_ids':['a','b'],'approved_by':'verified-owner'}
    record['applied_result']={'preview_id':'p','ontology':{'ontology_id':'merged','provenance':provenance}}
    def dossier():return build_dossier('merges',record,normalize('merges',record),'http://local/p')
    assert dossier()['release']['native_result_linked'] is True
    provenance['preview_id']='other'
    assert dossier()['release']['native_result_linked'] is False
    assert dossier()['publication_receipt_retained'] is False


def test_dossier_etag_is_representation_specific_and_rechecks_identity(monkeypatch):
    monkeypatch.setenv('OSLC_ENABLED','true');c=client(monkeypatch)
    record=merge_dossier_fixture()
    monkeypatch.setattr(PostgresRegistry,'get',lambda self,key:record if key=='p' else None)
    response=c.get('/api/v1/change-control/records/merges/p')
    assert response.status_code==200 and response.json()['dossier']['read_only']
    etag=response.headers['etag']
    assert c.get('/api/v1/change-control/records/merges/p',headers={'If-None-Match':etag}).status_code==304
    rdf=c.get('/oslc/change-control/records/merges/p',headers={'Accept':'text/turtle','If-None-Match':etag})
    assert rdf.status_code==200 and rdf.headers['etag']!=etag
    record['sources'][0]['artifact_sha256']='d'*64
    assert c.get('/api/v1/change-control/records/merges/p',headers={'If-None-Match':etag}).status_code==200
    assert 'DO_NOT_EXPORT_TURTLE' not in response.text


@pytest.mark.parametrize('field,value',[('ontology_name','Different name'),('prefix','different-prefix'),('description','Different business purpose'),('changes',{'additions':3}),('recommended_version_bump','major')])
def test_native_plan_fingerprint_binds_all_output_instructions(field,value):
    from backend.oslc_service.change_dossier import build_dossier
    record=merge_dossier_fixture()
    def plan():return build_dossier('merges',record,normalize('merges',record),'http://local/p')['release']
    before=plan();record[field]=value;after=plan()
    assert before['plan_schema']==after['plan_schema']=='nexus.native-merge-plan.v1'
    assert before['plan_digest']!=after['plan_digest']


@pytest.mark.parametrize('media,format',[('text/turtle','turtle'),('application/rdf+xml','xml'),('application/ld+json','json-ld')])
def test_one_canonical_request_and_weak_semantic_etag_in_every_rdf_format(monkeypatch,media,format):
    c=client(monkeypatch)
    monkeypatch.setattr(PostgresRegistry,'get',lambda self,key:merge_dossier_fixture() if key=='p' else None)
    path='/api/v1/change-control/records/merges/p'
    first=c.get(path,headers={'Accept':media});second=c.get(path,headers={'Accept':media})
    assert first.status_code==second.status_code==200
    assert first.headers['etag'].startswith('W/') and first.headers['etag']==second.headers['etag']
    graph=Graph().parse(data=first.content,format=format)
    subjects=set(graph.subjects(RDF.type,URIRef('http://open-services.net/ns/cm#ChangeRequest')))
    assert len(subjects)==1 and all(isinstance(subject,URIRef) for subject in subjects)
    tag=first.headers['etag']
    for validator in (tag,tag.removeprefix('W/'),'"unrelated", '+tag,'*'):
        assert c.get(path,headers={'Accept':media,'If-None-Match':validator}).status_code==304
    assert c.get(path,headers={'Accept':media,'If-None-Match':'"unrelated"'}).status_code==200


def test_legacy_nonpreview_identity_cannot_claim_a_merge_plan():
    from backend.oslc_service.change_dossier import build_dossier
    value=merge_dossier_fixture();value.pop('preview_id');value['job_id']='legacy'
    result=build_dossier('merges',value,normalize('merges',value),'http://local/legacy')
    assert result['release']['plan_digest'] is None


def managed_order_fixture():
    from backend.ontology_service.merge_plan import merge_plan_digest
    record=merge_dossier_fixture();record.pop('approved_by',None);record.pop('applied_result',None)
    plan=merge_plan_digest(record)
    record['change_request']={'request_id':record['preview_id'],'state':'authorized','plan_digest':plan,
        'order':{'order_id':record['preview_id'],'plan_digest':plan,'authorized_by':'owner','operation':'create_merged_draft','publish':False}}
    return record

@pytest.mark.parametrize('field,value',[('order_id','foreign'),('authorized_by',None),('authorized_by',' '),('operation','publish'),('publish',True),('plan_digest','f'*64)])
def test_invalid_order_cannot_claim_authorization_in_list_or_dossier(field,value):
    from backend.oslc_service.change_dossier import build_dossier
    record=managed_order_fixture();record['change_request']['order'][field]=value
    record['approved_by']='legacy-actor-must-not-override-managed-order'
    summary=normalize('merges',record)
    dossier=build_dossier('merges',record,summary,'http://local/request')
    assert summary['review_state']!='Authorization retained'
    assert summary['authorization_actor'] is None and summary['needs_attention']
    assert dossier['release']['order'] is None


def test_exact_order_is_retained_but_list_does_not_claim_current_readiness():
    from backend.oslc_service.change_dossier import build_dossier
    record=managed_order_fixture();summary=normalize('merges',record)
    dossier=build_dossier('merges',record,summary,'http://local/request')
    assert summary['review_state']=='Authorization retained'
    assert summary['execution_state']=='Authorization recorded; verify current plan'
    assert dossier['release']['order']['order_id']==record['preview_id']
    assert dossier['request']['identifier']==record['preview_id']
    record['prefix']='changed-output';summary=normalize('merges',record)
    assert summary['execution_state']=='Authorization recorded; verify current plan'
    assert build_dossier('merges',record,summary,'http://local/request')['release']['order'] is None


def test_projected_summary_needs_no_large_rdf_body_to_report_recorded_authorization():
    from backend.oslc_service.change_control import restore_summary
    record=managed_order_fixture()
    projected=restore_summary({'preview_id':record['preview_id'],'merge_change':record['change_request']})
    assert 'turtle' not in projected
    assert normalize('merges',projected)['execution_state']=='Authorization recorded; verify current plan'


def test_foreign_request_identity_cannot_claim_a_co():
    from backend.oslc_service.change_dossier import build_dossier
    record=managed_order_fixture();record['change_request']['request_id']='foreign'
    summary=normalize('merges',record)
    assert summary['authorization_actor'] is None
    assert build_dossier('merges',record,summary,'http://local/request')['release']['order'] is None


def test_definition_versions_are_reviewable_without_inventing_run_or_release_approval():
    definition={'job_id':'validate-source','version':'1.0.0','name':'Validate engineering source','workflow_number':'WF-2026-000004','lifecycle_state':'draft','enabled':True,'owner':'engineering'}
    draft=normalize('definitions',definition)
    assert draft['identifier']=='validate-source:1.0.0'
    assert draft['execution_state']=='New execution blocked'
    assert draft['type']=='urn:depo:change-control:EvidenceRecord'
    assert not draft['receipt_retained'] and 'request_number' not in draft
    approved=normalize('definitions',{**definition,'lifecycle_state':'approved','approved_by':'verified-owner'})
    assert approved['review_state']=='Approved definition'
    assert approved['execution_state']=='Available for new runs'
    assert approved['workspace']=='#/data-flow?view=pipelines&definition_id=validate-source&definition_version=1.0.0'
    assert normalize('definitions',{**definition,'lifecycle_state':'approved','approved_by':'verified-owner','enabled':False})['execution_state']=='New execution blocked'


def test_projected_import_request_keeps_its_identity_and_does_not_invent_receipt(monkeypatch):
    from backend.oslc_service.change_control import SUMMARY_PROJECTION,restore_summary
    from backend.ingestion_service import import_change
    assert SUMMARY_PROJECTION['task_id']==['task_id']
    assert SUMMARY_PROJECTION['operation']==['operation']
    monkeypatch.setattr(import_change,'valid',lambda record:False)
    record=restore_summary({'task_id':'task-a','name':'Requirements.xml','merge_change':{'request_id':'task-a','state':'submitted','plan_digest':'a'*64},'receipt_publication_id':None,'receipt_request_digest':None,'native_import_receipt':None})
    result=normalize('import_changes',record)
    assert result['identifier']=='task-a' and result['type']=='oslc_cm:ChangeRequest'
    assert result['workspace']=='#/import'
    assert not result['receipt_retained']


@pytest.mark.parametrize('state',['submitted','authorized','executing','needs_recovery'])
def test_projected_import_cannot_claim_receipt_before_reconciliation(state,monkeypatch):
    from backend.ingestion_service import import_change
    monkeypatch.setattr(import_change,'valid',lambda record:False)
    result=normalize('import_changes',{'task_id':'t','change_request':{'state':state,'plan_digest':'a'*64},'receipt':{'publication_id':None,'request_digest':None}})
    assert not result['receipt_retained']
    assert result['delivery_state']=='Load not verified'


def test_native_import_authority_uses_the_shared_register_category(monkeypatch):
    from backend.ingestion_service import import_change
    monkeypatch.setattr(import_change,'valid',lambda record:True)
    result=normalize('import_changes',{'task_id':'t','change_request':{'state':'executed','plan_digest':'a'*64,'order':{'authorized_by':'verified-owner'}},'receipt':{'plan_digest':'a'*64}})
    assert result['authorization_kind']=='Service authorization'
    assert result['authorization_actor']=='verified-owner'
    assert result['receipt_retained']


def test_release_source_eligibility_requires_a_completed_supported_retained_partition():
    base={'run_id':'run','run_number':'RUN-2026-000101','status':'completed','job_type':'validate-semantic-batch',
          'output_manifest':{'partition_artifacts':{'accepted':'sha256:accepted'}}}
    summary=normalize('pipeline',base)
    assert summary['release_source_ready'] is True and summary['reference']=='RUN-2026-000101'
    for change in ({'status':'failed'},{'job_type':'published-graph-snapshot'},{'output_manifest':{}}):
        assert normalize('pipeline',{**base,**change})['release_source_ready'] is False


def test_small_change_projection_preserves_accepted_partition_without_loading_payloads():
    from backend.oslc_service.change_control import restore_summary,SUMMARY_PROJECTION
    assert SUMMARY_PROJECTION['accepted_partition']==['output_manifest','partition_artifacts','accepted']
    restored=restore_summary({'run_id':'run','accepted_partition':'sha256:accepted',
                              'pipeline_publication':None,'pipeline_publication_intent':None,'pipeline_publication_digest':None})
    assert restored['output_manifest']['partition_artifacts']['accepted']=='sha256:accepted'
