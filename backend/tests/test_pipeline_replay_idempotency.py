from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.data_pipeline_service import router as module
from backend.mesh_store import InMemoryRegistry
import pytest


def setup(monkeypatch):
    store=InMemoryRegistry()
    store.put('source',{'run_id':'source','job_id':'job','job_version':'1'})
    monkeypatch.setattr(module.run_records,'store',store)
    monkeypatch.setattr(module.run_records,'get',store.get)
    monkeypatch.setattr(module.run_records,'replay_payload',lambda previous:{'replay_of':previous['run_id']})
    monkeypatch.setattr(module.job_definitions,'get',lambda *args:{'job_id':'job','version':'1','lifecycle_state':'approved','enabled':True})
    monkeypatch.setattr(module,'approval_identity',lambda *args,**kwargs:'actor')
    monkeypatch.setattr(module,'_worker_execution_enabled',lambda:True)
    created=[]
    def enqueue(definition,payload,*,correlation_id,run_id=None):
        created.append(run_id)
        record={'run_id':run_id,'replay_of':payload['replay_of'],'executed_by':payload['execution_actor'],'status':'queued'}
        store.put(run_id,record)
        return record
    monkeypatch.setattr(module.run_records,'enqueue',enqueue)
    app=FastAPI();app.include_router(module.router)
    return TestClient(app),created


@pytest.mark.parametrize('worker',[True,False])
def test_retry_after_lost_response_returns_same_durable_run(monkeypatch,worker):
    client,created=setup(monkeypatch)
    monkeypatch.setattr(module,'_worker_execution_enabled',lambda:worker)
    def inline(definition,payload,correlation_id,**options):
        run=module.run_records.enqueue(definition,payload,correlation_id=correlation_id,**options)
        return {'run_manifest':run,'run':run,'status':run['status']}
    monkeypatch.setattr(module,'execute_configured_job',inline)
    first=client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'intent-1'})
    second=client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'intent-1'})
    assert first.status_code==second.status_code==200
    assert first.json()['run']['run_id']==second.json()['run']['run_id']
    assert second.json()['idempotent'] is True and len(created)==1
    third=client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'intent-2'})
    assert third.json()['run']['run_id']!=first.json()['run']['run_id'] and len(created)==2


def test_invalid_replay_intent_is_rejected_before_execution(monkeypatch):
    client,created=setup(monkeypatch)
    assert client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'a'*129}).status_code==422
    assert client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':42}).status_code==422
    assert not created


def test_retained_replay_receipt_survives_original_input_retention(monkeypatch):
    client,created=setup(monkeypatch)
    first=client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'retained-intent'})
    assert first.status_code==200
    def expired(previous):
        raise ValueError('Original replay input expired')
    monkeypatch.setattr(module.run_records,'replay_payload',expired)
    monkeypatch.setattr(module.job_definitions,'get',lambda *args:None)
    second=client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'retained-intent'})
    assert second.status_code==200
    assert second.json()['run']['run_id']==first.json()['run']['run_id']
    assert len(created)==1
    def revoked(*args,**kwargs):
        raise HTTPException(403,'Access revoked')
    monkeypatch.setattr(module,'approval_identity',revoked)
    assert client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'retained-intent'}).status_code==403
    assert len(created)==1


def test_mismatched_retained_replay_identity_is_not_reused(monkeypatch):
    client,created=setup(monkeypatch)
    first=client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'intent'})
    run_id=first.json()['run']['run_id']
    module.run_records.store.put(run_id,{'run_id':'wrong-run','replay_of':'source','executed_by':'actor','status':'completed'})
    assert client.post('/pipeline/jobs/runs/source/replay',json={'idempotency_key':'intent'}).status_code==409
    assert len(created)==1
