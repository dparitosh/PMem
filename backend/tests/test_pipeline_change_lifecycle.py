import asyncio
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.mesh_store import InMemoryRegistry
from backend.artifact_store import ArtifactStore
from backend.data_pipeline_service import publication_change as change,router as native,run_records
from backend.depo_platform.request_bodies import PipelineChangeCommand

ORIGINAL_PUBLISH=native._publish_job_run_locked

class Store(InMemoryRegistry):
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))
    @contextmanager
    def advisory_lock(self,key):yield True

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('ARTIFACT_STORAGE',str(tmp_path/'artifacts'))
    store=Store('pipeline-change-fixture');monkeypatch.setattr(run_records,'store',store)
    artifact=ArtifactStore().ingest_bytes(json.dumps({'entities':[{'id':'part-a'}],'relationships':[]}).encode(),filename='accepted.json',kind='accepted-semantic-partition',media_type='application/json')
    record={'run_id':'run-a','job_id':'semantic-job','job_version':'1.0.0','job_type':'validate-semantic-batch','status':'completed','source_system':'plm',
        'input_manifest':{'payload_digest':'sha256:input'},'output_manifest':{'partition_artifacts':{'accepted':artifact['artifact_id']},'checkpoint_candidate':{'position':2}}}
    store.put('run-a',record)
    parameters={'ontology_id':'parts','semantic_release':{'asset_id':'approved-model','version':'1.0.0'}}
    receipt={'status':'published','current':True,'ontology_id':'parts','publication_id':'run-a','resources':1,'relationships':0}
    monkeypatch.setattr(native,'_reconcile_graph_publication',AsyncMock(return_value=receipt))
    async def publish(run_id,payload,request,actor):
        current=run_records.get(run_id);plan,_=change.prepare(current,payload)
        current['output_manifest']['publication_intent']=plan['intent'];store.put(run_id,current)
        return current
    operation=AsyncMock(side_effect=publish);monkeypatch.setattr(native,'_publish_job_run_locked',operation)
    return parameters,operation,receipt


def run(awaitable):return asyncio.run(awaitable)
def submit(setup):return run(change.submit('run-a',setup[0],'Review imported engineering records','requester'))
def act(action,actor='reviewer'):
    state=run(change.view('run-a'))
    return run(change.command('run-a',PipelineChangeCommand(action=action,expected_revision=state['change_request']['revision'],expected_plan_digest=state['current_plan_digest']),None,actor))
def authorize(setup):submit(setup);act('accept');act('authorize')


def test_request_and_acceptance_do_not_publish_or_advance_checkpoint(setup):
    submit(setup);state=act('accept')
    assert state['change_request']['state']=='accepted'
    assert not run_records.get('run-a').get('checkpoint')
    with pytest.raises(HTTPException):act('execute')
    setup[1].assert_not_awaited()


def test_authorized_partition_uses_native_operation_and_verifies_current_receipt(setup):
    authorize(setup);state=act('execute','executor')
    assert state['change_request']['state']=='executed'
    assert state['change_request']['order']['authorized_by']=='reviewer'
    assert state['change_request']['receipt']['verified_by']=='executor'
    assert run_records.get('run-a')['checkpoint']=={'position':2}
    assert setup[1].await_count==1
    with pytest.raises(HTTPException):act('execute')
    assert setup[1].await_count==1


@pytest.mark.parametrize('field,value',[('ontology_id','different'),('source_system','other'),('semantic_release',{'asset_id':'other','version':'1.0.0'})])
def test_direct_publish_cannot_expand_authorized_scope(setup,field,value):
    authorize(setup)
    with pytest.raises(HTTPException):run(change.execute_locked('run-a',{**setup[0],field:value},None,'actor'))
    setup[1].assert_not_awaited()


def test_changed_partition_bytes_cannot_use_old_authorization(setup):
    authorize(setup);artifact=run_records.get('run-a')['output_manifest']['partition_artifacts']['accepted']
    _,path=ArtifactStore().resolve(artifact);path.write_text('{"entities":[],"relationships":[]}')
    with pytest.raises(HTTPException):act('execute')
    setup[1].assert_not_awaited()


def test_cancelled_request_blocks_legacy_native_publish(setup):
    authorize(setup);act('cancel')
    with pytest.raises(HTTPException):run(change.execute_locked('run-a',setup[0],None,'executor'))
    setup[1].assert_not_awaited()


def test_lost_response_reconciles_without_replaying_native_write(setup,monkeypatch):
    authorize(setup);original=setup[1].side_effect
    async def lost(*args):await original(*args);raise TimeoutError('lost response')
    setup[1].side_effect=lost
    with pytest.raises(TimeoutError):act('execute')
    assert run(change.view('run-a'))['change_request']['state']=='needs_recovery'
    assert act('reconcile')['change_request']['state']=='executed'
    assert setup[1].await_count==1


@pytest.mark.parametrize('field,value',[('current',False),('publication_id','other'),('ontology_id','other'),('resources',True),('relationships',-1),('status','publishing')])
def test_incorrect_or_stale_graph_receipt_never_completes_order(setup,field,value):
    authorize(setup);setup[2][field]=value
    with pytest.raises(HTTPException):act('execute')
    assert run(change.view('run-a'))['change_request']['state']=='needs_recovery'
    assert not run_records.get('run-a').get('checkpoint')
    assert setup[1].await_count==1
    with pytest.raises(HTTPException):act('execute')
    assert setup[1].await_count==1


def test_duplicate_submit_and_stale_review_are_deterministic(setup):
    first=submit(setup);act('accept');assert submit(setup)['change_request']['state']=='accepted'
    with pytest.raises(HTTPException):run(change.command('run-a',PipelineChangeCommand(action='authorize',expected_revision=1,expected_plan_digest=first['current_plan_digest']),None,'stale'))
    with pytest.raises(HTTPException):run(change.submit('run-a',{**setup[0],'ontology_id':'other'},'Changed','actor'))


def test_preexisting_publication_intent_is_not_retroactively_approved(setup):
    record=run_records.get('run-a');record['output_manifest']['publication_intent']={'ontology_id':'parts'};run_records.store.put('run-a',record)
    with pytest.raises(HTTPException):submit(setup)
    assert not run_records.get('run-a').get('change_request')


def test_central_projection_requires_matching_order_and_exact_receipt(setup):
    from backend.oslc_service.change_control import normalize
    from backend.oslc_service.change_dossier import build_dossier
    assert normalize('pipeline',run_records.get('run-a'))['type']!='oslc_cm:ChangeRequest'
    authorize(setup);act('execute');record=run_records.get('run-a');summary=normalize('pipeline',record)
    assert summary['type']=='oslc_cm:ChangeRequest' and summary['receipt_retained']
    dossier=build_dossier('pipeline',record,summary,'http://local/run')
    assert dossier['release']['order']['operation']=='publish_accepted_partition'
    record['change_request']['order']['plan_digest']='0'*64
    assert not normalize('pipeline',record)['receipt_retained']


def test_native_submission_requires_verified_credential_before_artifact_access(setup,monkeypatch):
    from backend.data_pipeline_service.app import app
    from backend.depo_platform.authorization import graph_read_identity
    monkeypatch.setattr(native,'approval_identity',lambda *args,**kwargs:(_ for _ in ()).throw(HTTPException(403,'Not authorized')))
    app.dependency_overrides[graph_read_identity]=lambda:'reader'
    try:
        response=TestClient(app).post('/api/v1/pipeline/jobs/runs/run-a/change/submit',json={'publication':setup[0],'reason':'Review'})
        assert response.status_code==403
        assert not run_records.get('run-a').get('change_request')
    finally:app.dependency_overrides.clear()


from backend.tests.test_reporting_trs_postgres import reporting_db


def test_postgres_restart_and_receipt_only_recovery(reporting_db,setup,monkeypatch):
    Registry=type(reporting_db)
    with reporting_db._connect() as db:
        db.execute("CREATE TABLE depo_registry(namespace text NOT NULL,key text NOT NULL,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(namespace,key))")
    registry=Registry('data_job_runs');registry.put('run-a',run_records.get('run-a'))
    monkeypatch.setattr(run_records,'store',registry)
    submit(setup);monkeypatch.setattr(run_records,'store',Registry('data_job_runs'))
    act('accept');act('authorize')
    async def lost(run_id,parameters,request,actor):
        record=run_records.get(run_id);plan,_=change.prepare(record,parameters)
        record['output_manifest']['publication_intent']=plan['intent']
        run_records.store.put(run_id,record)
        raise TimeoutError('lost response after persisted receipt')
    setup[1].side_effect=lost
    with pytest.raises(TimeoutError):act('execute','executor')
    monkeypatch.setattr(run_records,'store',Registry('data_job_runs'))
    assert run(change.view('run-a'))['change_request']['state']=='needs_recovery'
    assert act('reconcile','verifier')['change_request']['state']=='executed'
    assert setup[1].await_count==1
    assert run_records.get('run-a')['checkpoint']=={'position':2}


def test_native_managed_publication_defers_checkpoint_until_current_graph_verification(setup,monkeypatch):
    import httpx
    from types import SimpleNamespace
    authorize(setup);monkeypatch.setattr(native,'_publish_job_run_locked',ORIGINAL_PUBLISH)
    monkeypatch.setattr(native,'service_bearer_headers',lambda *args,**kwargs:{})
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            assert "approval_token" not in kwargs["json"], "Body tokens must not override authenticated peer headers"
            return httpx.Response(200,request=httpx.Request('POST',url),json={'status':'published','ontology_id':'parts','publication_id':'run-a'})
    monkeypatch.setattr(native.httpx,'AsyncClient',Client)
    async def verify(**kwargs):
        record=run_records.get('run-a')
        assert not record.get('checkpoint') and not record['output_manifest'].get('publication')
        return setup[2]
    monkeypatch.setattr(native,'_reconcile_graph_publication',verify)
    current=run(change.view('run-a'))
    command=PipelineChangeCommand(action='execute',expected_revision=current['change_request']['revision'],expected_plan_digest=current['current_plan_digest'])
    assert run(change.command('run-a',command,SimpleNamespace(headers={}), 'executor'))['change_request']['state']=='executed'
    assert run_records.get('run-a')['checkpoint']=={'position':2}


def test_native_publication_without_a_cr_and_co_fails_closed(setup,monkeypatch):
    with pytest.raises(HTTPException) as failure:
        run(change.execute_locked('run-a',setup[0],None,'publication-credential-owner'))
    assert failure.value.status_code==409
    from backend.data_pipeline_service.app import app
    monkeypatch.setattr(native,'approval_identity',lambda *args,**kwargs:'publication-credential-owner')
    response=TestClient(app).post('/api/v1/pipeline/jobs/runs/run-a/publish',json={**setup[0],'semantic_release':{**setup[0]['semantic_release'],'lifecycle_status':'approved'},'approved_by':'ignored-untrusted-body-name'})
    assert response.status_code==409
    assert 'Change Control' in response.json()['detail']
    setup[1].assert_not_awaited()
    assert run_records.get('run-a').get('checkpoint') is None
    assert run_records.get('run-a').get('change_request') is None
