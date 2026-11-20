"""Real PostgreSQL coordination, native artifacts/packaging and controlled peer receipts."""
import asyncio,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from backend.tests.test_reporting_trs_postgres import reporting_db
from backend.artifact_store import ArtifactStore
from backend.depo_platform import release_chain as chain
from backend.depo_platform.request_bodies import ReleaseChangeSubmission,ReleaseChangeCommand,PipelineChangeCommand
from backend.oslc_service import release_changes as release,notifications,trs_snapshot
from backend.Services.oslc_trs_service import OSLCTRSService as trs
from backend.data_pipeline_service import router as pipeline,run_records,publication_change as pipeline_change
from backend.data_product_service import router as products,product_change


def run(awaitable):return asyncio.run(awaitable)


def test_real_source_to_release_recovery_configuration_rebase_and_trs(reporting_db,tmp_path,monkeypatch):
    Registry=type(reporting_db)
    with reporting_db._connect() as db:
        db.execute("CREATE TABLE depo_registry(namespace text NOT NULL,key text NOT NULL,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(namespace,key))")
    monkeypatch.setenv('ARTIFACT_STORAGE',str(tmp_path/'artifacts'));monkeypatch.setenv('OSLC_TRS_STORE','postgres');monkeypatch.setenv('OSLC_TRS_ENABLED','true')
    monkeypatch.setattr(notifications,'PostgresRegistry',Registry)
    artifact_store=ArtifactStore();artifact=artifact_store.ingest_bytes(json.dumps({'entities':[{'id':'part-a'}],'relationships':[]}).encode(),filename='accepted.json',kind='accepted-semantic-partition',media_type='application/json')
    monkeypatch.setattr(run_records,'store',Registry('data_job_runs'))
    run_records.store.put('run',{'run_id':'run','job_id':'semantic-job','job_version':'1.0.0','job_type':'validate-semantic-batch','status':'completed','source_system':'plm','input_manifest':{'payload_digest':'sha256:source'},'output_manifest':{'partition_artifacts':{'accepted':artifact['artifact_id']},'checkpoint_candidate':{'position':2}}})
    monkeypatch.setattr(products,'store',Registry('data_products'));monkeypatch.setattr(products,'approval_store',Registry('data_product_approvals'))
    monkeypatch.setattr(products,'artifact_store',artifact_store);monkeypatch.setattr(products,'root',tmp_path/'packages')
    monkeypatch.setattr(products,'resolve_lineage',AsyncMock(return_value={'verified':True}));monkeypatch.setattr(products,'resolve_approved_release',AsyncMock(side_effect=lambda ref:ref))
    delivery={'ready':False}
    async def catalog(value):return {**value,'status':'published' if delivery['ready'] else 'pending_catalog_registration','catalog_registered_at':'2026-11-14T12:00:00Z' if delivery['ready'] else None}
    monkeypatch.setattr(products,'_register_catalog',catalog)
    product={'product_id':'engineering','name':'Engineering evidence','version':'1.0.0','domain':'engineering','owner':'owner','steward':'steward','classification':'internal','lifecycle_state':'published','product_kind':'pipeline-evidence','artifacts':[{'artifact_id':artifact['artifact_id']}],'sources':[{'run_id':'run','job_id':'semantic-job','job_type':'validate-semantic-batch'}],'semantic_releases':[{'asset_id':'approved-model','version':'1.0.0','lifecycle_status':'approved'}]}
    parameters={'ontology_id':'parts','semantic_release':product['semantic_releases'][0]}
    run(pipeline_change.submit('run',parameters,'Release imported records','requester'))
    run(product_change.submit(product,'Package reviewed source evidence','requester'))
    body=ReleaseChangeSubmission(title='Source to governed engineering release',reason='Deliver reviewed engineering evidence',source_run_id='run',operations=[{'source_kind':'pipeline','identifier':'run'},{'source_kind':'product_changes','identifier':'engineering:1.0.0'}])
    parent=release.create(body,'coordinator');identifier=parent['request_id']
    # Registry recreation proves this is durable coordination, not browser state.
    monkeypatch.setattr(chain,'registry',lambda:Registry(chain.NAMESPACE))
    def parent_action(action):
        value=release.view(identifier)
        return release.transition(identifier,ReleaseChangeCommand(action=action,expected_revision=value['revision'],configuration_id=value['configuration_id']),'coordinator',value['configuration_context'])
    def pipe_action(action):
        value=run(pipeline_change.view('run'))
        return run(pipeline_change.command('run',PipelineChangeCommand(action=action,expected_revision=value['change_request']['revision'],expected_plan_digest=value['current_plan_digest']),SimpleNamespace(headers={}), 'native-publisher'))
    def product_action(action):
        value=run(product_change.view('engineering:1.0.0'))
        return run(product_change.command('engineering:1.0.0',action,'steward',value['change_request']['revision'],value['current_plan_digest']))
    pipe_action('accept');pipe_action('authorize');product_action('accept');product_action('authorize')
    with pytest.raises(HTTPException):pipe_action('execute')
    parent_action('accept');parent_action('authorize')
    with pytest.raises(HTTPException):product_action('execute')
    assert products.store.get('engineering:1.0.0') is None
    receipt={'status':'published','current':True,'ontology_id':'parts','publication_id':'run','resources':1,'relationships':0}
    peer={'writes':0,'receipt_available':False}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):peer['writes']+=1;raise httpx.ReadTimeout('lost response after peer commit')
    monkeypatch.setattr(pipeline.httpx,'AsyncClient',Client)
    monkeypatch.setattr(pipeline,'service_bearer_headers',lambda *args,**kwargs:{})
    async def receipt_read(**kwargs):return receipt if peer['receipt_available'] else None
    monkeypatch.setattr(pipeline,'_reconcile_graph_publication',receipt_read)
    with pytest.raises(HTTPException):pipe_action('execute')
    assert peer['writes']==1 and run_records.get('run')['change_request']['state']=='needs_recovery'
    assert not run_records.get('run').get('checkpoint')
    with pytest.raises(HTTPException):product_action('execute')
    peer['receipt_available']=True;pipe_action('reconcile')
    assert run_records.get('run')['checkpoint']=={'position':2}
    def native_read(service,path,download=False):
        if service=='GRAPH_SERVICE_URL':return receipt
        if service=='DATA_CATALOG_URL':
            value=products.store.get('engineering:1.0.0')
            return {'product_id':'engineering','version':'1.0.0','lifecycle_state':'published','manifest':value['manifest']}
        assert download and '/data-products/engineering%3A1.0.0/download'==path
        value=products.store.get('engineering:1.0.0');storage=value['package_storage']
        products.verify_package(Path(storage['package_dir']),Path(storage['zip_path']),value['manifest'])
        return True
    monkeypatch.setattr(chain,'graph_get',native_read)
    product_action('execute')
    assert Path(products.store.get('engineering:1.0.0')['package_storage']['zip_path']).is_file()
    with pytest.raises(HTTPException):parent_action('verify')
    with pytest.raises(HTTPException):parent_action('cancel')
    delivery['ready']=True;product_action('retry_delivery')
    closed=parent_action('verify');assert closed['state']=='completed' and peer['writes']==1
    baseline=closed['configuration_id']
    notifications.reconcile(limit=100)
    events=trs.change_log(after=0)['events'];paths={event['resource_uri'] for event in events}
    assert any('/records/releases/' in uri for uri in paths)
    assert any('/configurations/' in uri for uri in paths)
    assert any('/records/pipeline/' in uri for uri in paths)
    assert any('/records/product_changes/' in uri for uri in paths)
    # Reset/regrow cannot be mistaken for a current cursor or parent configuration.
    trs._store.put('change_log',{'counter':5000,'events':[]})
    assert release.view(identifier)['tracking_changed']
    changed=parent_action('rebase');assert changed['state']=='submitted' and changed['configuration_id']!=baseline
    assert Registry(chain.NAMESPACE).get('baseline:'+baseline)
    parent_action('accept');parent_action('authorize');assert parent_action('verify')['state']=='completed'
    assert peer['writes']==1
    # Base membership is native, even after event pruning; no Neo4j test writes.
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def run(self,*args):return []
    monkeypatch.setattr(trs_snapshot,'get_driver',lambda:SimpleNamespace(session=lambda **kwargs:Session()))
    monkeypatch.setattr(trs_snapshot,'get_config',lambda:SimpleNamespace(database='isolated',query_timeout=1))
    state=trs._load();state['events']=[];trs._store.put('change_log',state)
    base=trs.base_resources(limit=100)
    assert any('/records/releases/'+identifier in item['resource_uri'] for item in base['members'])
    assert any('/configurations/'+baseline in item['resource_uri'] for item in base['members'])
    assert base['stream_id']==trs.change_log()['stream_id']
