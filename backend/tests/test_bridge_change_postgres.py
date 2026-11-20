"""Persisted mapping CR–CO and lost-response recovery in isolated PostgreSQL."""
import pytest
from backend.tests.test_reporting_trs_postgres import reporting_db
from backend.tests.test_bridge_change_lifecycle import BaselineSource,Graph
from backend.agentic_service.bridge_jobs import BridgeJobs,BridgeConflict
from backend.agentic_service import bridge_change


def test_mapping_request_survives_service_recreation_and_reconciles_without_republish(reporting_db):
    Registry=type(reporting_db)
    with reporting_db._connect() as db:
        db.execute("CREATE TABLE depo_registry(namespace text NOT NULL,key text NOT NULL,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(namespace,key))")
    graph=Graph();source=BaselineSource()
    def recreate():return BridgeJobs(Registry('semantic_bridge_jobs_v1'),source,graph,
        holds=Registry('semantic_bridge_holds_v1'),policy_evaluator=lambda *args,**kwargs:{'blocking':False})
    jobs=recreate();value=jobs.preview('ontology','import','reader');ids=[value['candidates'][0]['candidate_id']]
    def act(owner,action,actor):
        status=bridge_change.view(owner,value['job_id']);request=status['change_request']
        return bridge_change.transition(owner,value['job_id'],action,actor,request['revision'] if request else 0,
            status['current_plan_digest'],'Review source classification',ids if action=='submit' else [])
    act(jobs,'submit','requester');jobs=recreate()
    with pytest.raises(BridgeConflict):jobs.publish(value['job_id'],ids,'unauthorized-executor')
    act(jobs,'accept','reviewer');act(jobs,'authorize','authorizer')
    graph.lose_response=True
    with pytest.raises(TimeoutError):act(jobs,'execute','executor')
    jobs=recreate();assert bridge_change.view(jobs,value['job_id'])['change_request']['state']=='needs_recovery'
    assert act(jobs,'reconcile','reconciler')['change_request']['state']=='executed'
    assert len(graph.calls)==1 and graph.calls[0]['approved_by']=='authorizer'
    assert jobs.get(value['job_id'])==value
    assert jobs.get(value['publication_job_id'])['status']=='published'
