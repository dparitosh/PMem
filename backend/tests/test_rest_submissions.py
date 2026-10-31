from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import rest_submissions as submissions


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(submissions,'store',InMemoryRegistry())
    monkeypatch.setattr(submissions.rest_sources,'store',InMemoryRegistry())
    submissions.rest_sources.store.create('parts',{'source_id':'parts'})
    runs={}
    def enqueue(definition,payload,*,run_id,**kwargs):
        record={'run_id':run_id,'status':'queued','executed_by':payload['execution_actor'],
            'source_system':payload['source_system'],'job_id':definition['job_id'],'job_version':definition['version']}
        runs[run_id]=record
        return record
    queue=Mock(side_effect=enqueue)
    monkeypatch.setattr(submissions.run_records,'enqueue',queue)
    monkeypatch.setattr(submissions.run_records,'get',runs.get)
    return {'job_id':'fetch','version':'1.0.0'},runs,queue


def send(definition,key='one',actor='tester'):
    return submissions.submit(definition,{'source_id':'parts','idempotency_key':key},actor,'audit')


def test_reconnect_retry_reuses_one_durable_run(setup):
    definition,runs,queue=setup
    assert send(definition)['run']['run_id']==send(definition)['run']['run_id']
    assert queue.call_count==1


def test_two_tabs_with_different_keys_share_active_source_run(setup):
    definition,runs,queue=setup
    assert send(definition,'tab-one')['run']['run_id']==send(definition,'tab-two')['run']['run_id']
    assert queue.call_count==1


def test_changed_identity_cannot_replay_pending_reference(setup):
    definition,runs,queue=setup
    send(definition)
    with pytest.raises(HTTPException) as failure: send(definition,actor='different-user')
    assert failure.value.status_code==409 and queue.call_count==1


def test_enqueue_failure_leaves_recoverable_intent_for_another_tab(setup):
    definition,runs,queue=setup
    real_enqueue=queue.side_effect
    queue.side_effect=RuntimeError('Registry temporarily unavailable')
    with pytest.raises(RuntimeError): send(definition,'first')
    queue.side_effect=real_enqueue
    recovered=send(definition,'second')
    assert send(definition,'first')['run']['run_id']==recovered['run']['run_id']
    assert len(runs)==1


def test_completed_run_needs_new_reference_for_new_snapshot(setup):
    definition,runs,queue=setup
    first=send(definition)
    runs[first['run']['run_id']]['status']='completed'
    assert send(definition)['run']['run_id']==first['run']['run_id']
    assert send(definition,'new-snapshot')['run']['run_id']!=first['run']['run_id']
    assert queue.call_count==2


def test_reference_is_bound_to_original_job_version(setup):
    definition,runs,queue=setup
    send(definition)
    with pytest.raises(HTTPException): send({**definition,'version':'2.0.0'})
    assert queue.call_count==1


def test_retained_status_is_readable_without_new_enqueue(setup):
    definition,runs,queue=setup
    first=send(definition)
    assert submissions.retained('one','tester')['run_manifest']['run_id']==first['run']['run_id']
    assert queue.call_count==1
    with pytest.raises(HTTPException) as failure: submissions.retained('one','different-user')
    assert failure.value.status_code==409
