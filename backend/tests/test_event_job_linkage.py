import pytest
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry
from backend.tests.test_speed_path_recovery import setup,envelope
from backend.data_pipeline_service import event_jobs as jobs,speed_path as speed,run_records,job_definitions

@pytest.fixture
def linked(setup,monkeypatch):
 monkeypatch.setattr(jobs,'ArtifactStore',speed.ArtifactStore);monkeypatch.setenv('ARTIFACT_STORAGE',str(speed.ArtifactStore().root));monkeypatch.setattr(run_records,'store',InMemoryRegistry());monkeypatch.setattr(job_definitions,'store',InMemoryRegistry())
 job_definitions.store.put('validate:1.0.0',{'job_id':'validate','version':'1.0.0','name':'Validate source changes','job_type':'validate-semantic-batch','lifecycle_state':'approved','enabled':True,'input_contract':'source-ceim-batch-v1'})
 speed.capture_event(envelope(),'capture-owner');review=speed.reconcile(['event-one'],'capture-owner')
 return review

def submit(review,**overrides):
 return jobs.submit(review['reconciliation_id'],overrides.get('job_id','validate'),'1.0.0',overrides.get('digest',speed._digest(review)),overrides.get('actor','execution-owner'),'request-one')

def test_real_queue_binding_and_retry_do_not_invent_change_approval(linked):
 first=submit(linked);second=submit(linked)
 assert first['run_id']==second['run_id'] and first['status']=='queued'
 assert first['input_manifest']['event_review_id']==linked['reconciliation_id']
 current=speed.reconciliations.get(linked['reconciliation_id']);evidence=jobs.lineage(current)
 assert evidence['linked'] and evidence['job_id']=='validate' and evidence['version']=='1.0.0'
 assert evidence['request_number'] is None and evidence['order_number'] is None and not evidence['publication_verified']
 assert len(run_records.store.all())==1

@pytest.mark.parametrize('change',['disabled','digest','source','tamper'])
def test_invalid_current_scope_is_rejected_before_queueing(linked,change):
 if change=='disabled':job_definitions.store.put('validate:1.0.0',{**job_definitions.get('validate','1.0.0'),'enabled':False})
 if change=='source':speed.sources.put('plm-events',{**speed.sources.get('plm-events'),'enabled':False})
 if change=='tamper':
  event=speed.events.get('event-one');_,path=jobs.ArtifactStore().resolve(event['artifact_id']);path.write_text('{}')
 with pytest.raises(HTTPException):submit(linked,**({'digest':'sha256:'+'0'*64} if change=='digest' else {}))
 assert not run_records.store.all()

def test_lost_binding_write_recovers_the_same_queued_job(linked,monkeypatch):
 original=speed.reconciliations.put
 monkeypatch.setattr(speed.reconciliations,'put',lambda *args:(_ for _ in ()).throw(RuntimeError('lost persistence')))
 with pytest.raises(RuntimeError):submit(linked)
 monkeypatch.setattr(speed.reconciliations,'put',original)
 assert submit(linked)['run_id']==next(iter(run_records.store.all().values()))['run_id']
 assert len(run_records.store.all())==1

def test_unlinked_event_publication_cannot_use_a_publication_key_only(linked,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.data_pipeline_service.app import app
 monkeypatch.setattr('backend.data_pipeline_service.speed_router.approval_identity',lambda *a,**kw:'publisher')
 response=TestClient(app).post('/api/v1/pipeline/speed/reconciliations/'+linked['reconciliation_id']+'/publish',json={})
 assert response.status_code==409 and 'Change Control' in response.json()['detail']


def test_event_processing_requires_execution_credentials_not_read_access(linked,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.data_pipeline_service.app import app
 from backend.depo_platform.authorization import approval_identity
 monkeypatch.setattr('backend.data_pipeline_service.speed_router.approval_identity',approval_identity)
 monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
 monkeypatch.setenv('GRAPH_READ_TOKEN','reader-key');monkeypatch.setenv('DATA_JOB_EXECUTION_TOKEN','executor-key');monkeypatch.setenv('DATA_JOB_EXECUTION_TOKEN_ACTOR','verified-executor')
 body={'job_id':'validate','version':'1.0.0','expected_digest':speed._digest(linked)}
 route='/api/v1/pipeline/speed/reconciliations/'+linked['reconciliation_id']+'/jobs'
 client=TestClient(app)
 assert client.post(route,json=body,headers={'Authorization':'Bearer reader-key'}).status_code==403
 assert not run_records.store.all()
 result=client.post(route,json=body,headers={'Authorization':'Bearer executor-key'})
 assert result.status_code==202 and result.json()['run']['executed_by']=='verified-executor'

def test_stored_foreign_run_cannot_supply_event_lineage(linked):
 record=submit(linked);review=speed.reconciliations.get(linked['reconciliation_id'])
 run_records.store.put(record['run_id'],{**record,'input_manifest':{**record['input_manifest'],'event_review_id':'foreign'}})
 with pytest.raises(HTTPException):jobs.lineage(review)
