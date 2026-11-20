from copy import deepcopy
from contextlib import contextmanager
from threading import Lock,Event
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.tests.test_bridge_jobs import Source,Graph
from backend.mesh_store import InMemoryRegistry
from backend.agentic_service.bridge_jobs import BridgeJobs,BridgeConflict
from backend.agentic_service import bridge_change as change
from backend.depo_platform.bridge_contract import digest

class Store(InMemoryRegistry):
    def __init__(self):super().__init__();self.locks={};self.guard=Lock()
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))
    @contextmanager
    def advisory_lock(self,key):
        with self.guard:lock=self.locks.setdefault(key,Lock())
        acquired=lock.acquire(blocking=False)
        try:yield acquired
        finally:
            if acquired:lock.release()

class BaselineSource(Source):
    def snapshot(self,*args):return {'source':digest(self.revision),'ontology':'b'*64}
    def preview(self,*args):
        snapshot,rows=super().preview(*args)
        return snapshot,rows+[{**rows[0],'source_term':'assembly','import_row_key':'row-2'}]

@pytest.fixture
def setup():
    jobs=BridgeJobs(Store(),BaselineSource(),Graph(),holds=Store(),policy_evaluator=lambda *args,**kw:{'blocking':False})
    value=jobs.preview('ontology','import','reader')
    return jobs,value,[value['candidates'][0]['candidate_id']]

def act(setup,action,actor='owner',**extra):
    jobs,value,ids=setup;status=change.view(jobs,value['job_id']);current=status['change_request']
    return change.transition(jobs,value['job_id'],action,actor,current['revision'] if current else 0,
        status['current_plan_digest'],extra.pop('reason','Business review'),ids if action=='submit' else extra.pop('candidate_ids',[]),**extra)

def authorize(setup):
    act(setup,'submit','requester');act(setup,'accept','reviewer');return act(setup,'authorize','authorizer')


def test_submission_does_not_change_preview_or_authorize_publication(setup):
    jobs,value,ids=setup;original=jobs.get(value['job_id']);act(setup,'submit');act(setup,'accept')
    assert jobs.get(value['job_id'])==original
    job=jobs.get(value['publication_job_id'])
    assert job['approved_ids']==[] and 'approved_by' not in job
    with pytest.raises(BridgeConflict):jobs.publish(value['job_id'],ids,'executor')
    assert jobs.graph.calls==[]


def test_exact_selection_publishes_once_and_retains_authorizer_and_executor(setup):
    jobs,value,ids=setup;authorize(setup);result=act(setup,'execute','executor')
    assert result['change_request']['state']=='executed'
    assert len(jobs.graph.calls)==1 and jobs.graph.calls[0]['approved_by']=='authorizer'
    history=result['change_request']['history'];assert any(event['action']=='execute' and event['actor']=='executor' for event in history)
    jobs.publish(value['job_id'],ids,'executor');assert len(jobs.graph.calls)==1


def test_duplicate_submission_does_not_overwrite_a_later_review(setup):
    jobs,value,ids=setup;initial=change.view(jobs,value['job_id']);act(setup,'submit');act(setup,'accept')
    result=change.transition(jobs,value['job_id'],'submit','other',0,initial['current_plan_digest'],'Different reason',ids)
    assert result['change_request']['state']=='accepted' and result['change_request']['reason']=='Business review'


def test_old_revision_cannot_reject_or_execute_newer_decision(setup):
    jobs,value,ids=setup;old=act(setup,'submit');act(setup,'accept')
    with pytest.raises(BridgeConflict):change.transition(jobs,value['job_id'],'reject','other',1,old['current_plan_digest'],'Old decision')
    authorize_revision=act(setup,'authorize')
    with pytest.raises(BridgeConflict):change.transition(jobs,value['job_id'],'execute','other',2,authorize_revision['current_plan_digest'])
    assert jobs.graph.calls==[]


def test_selection_cannot_expand_or_change_after_submission(setup):
    jobs,value,ids=setup;authorize(setup)
    with pytest.raises(BridgeConflict):jobs.publish(value['job_id'],[row['candidate_id'] for row in value['candidates']],'executor')
    with pytest.raises(ValueError):act(setup,'execute',candidate_ids=ids)
    assert jobs.graph.calls==[]


def test_unknown_or_duplicate_candidates_do_not_create_a_request(setup):
    jobs,value,ids=setup;initial=change.view(jobs,value['job_id'])
    for selected in [['unknown'],ids+ids,[]]:
        with pytest.raises(ValueError):change.transition(jobs,value['job_id'],'submit','owner',0,initial['current_plan_digest'],'Business reason',selected)
    assert jobs.store.get(value['publication_job_id']) is None


def test_lost_graph_response_requires_receipt_reconciliation_without_replay(setup):
    jobs,value,ids=setup;authorize(setup);jobs.graph.lose_response=True
    with pytest.raises(TimeoutError):act(setup,'execute')
    assert change.view(jobs,value['job_id'])['change_request']['state']=='needs_recovery'
    with pytest.raises(BridgeConflict):jobs.publish(value['job_id'],ids,'executor')
    result=act(setup,'reconcile');assert result['change_request']['state']=='executed' and len(jobs.graph.calls)==1


def test_missing_receipt_does_not_claim_completion(setup):
    jobs,value,ids=setup;authorize(setup);jobs.source.revision='changed'
    with pytest.raises(BridgeConflict):act(setup,'execute')
    with pytest.raises(BridgeConflict):act(setup,'reconcile')
    assert change.view(jobs,value['job_id'])['change_request']['state']=='needs_recovery' and jobs.graph.calls==[]


@pytest.mark.parametrize('field,invalid',[('order_id','foreign'),('request_id','foreign'),('authorized_by',' '),('operation','publish_everything'),('publish',False)])
def test_invalid_order_never_reaches_graph(setup,field,invalid):
    jobs,value,ids=setup;authorize(setup);job=jobs.get(value['publication_job_id'])
    job['change_request']['order'][field]=invalid;jobs.store.put(job['job_id'],job)
    assert change.view(jobs,value['job_id'])['authorization_valid'] is False
    with pytest.raises(BridgeConflict):jobs.publish(value['job_id'],ids,'executor')
    assert jobs.graph.calls==[]


def test_cancellation_blocks_old_manual_and_automatic_publication(setup):
    jobs,value,ids=setup;authorize(setup);act(setup,'cancel')
    with pytest.raises(BridgeConflict):jobs.publish(value['job_id'],ids,'executor')
    # Existing automatic path must still pass the same native publication guard.
    jobs.evaluate_policy=lambda identifier:{'accepted_ids':ids,'held_count':0}
    with pytest.raises(BridgeConflict):jobs.publish_automatic(value['job_id'],'executor')
    assert jobs.graph.calls==[]


def test_concurrent_execution_does_not_duplicate_graph_mutation(setup):
    jobs,value,ids=setup;authorize(setup);entered=Event();release=Event();native=jobs.graph.publish
    def slow(command):entered.set();release.wait(3);return native(command)
    jobs.graph.publish=slow
    with ThreadPoolExecutor(2) as pool:
        running=pool.submit(act,setup,'execute');assert entered.wait(2)
        with pytest.raises(BridgeConflict):act(setup,'execute')
        release.set();assert running.result()['change_request']['state']=='executed'
    assert len(jobs.graph.calls)==1


def test_historical_native_publication_cannot_be_retroactively_approved(setup):
    # Construct a historical receipt through the primitive; new writes require CR/CO.
    jobs,value,ids=setup;jobs._publish_locked(value['job_id'],ids,'old-owner')
    assert change.view(jobs,value['job_id'])['already_applied']
    with pytest.raises(BridgeConflict):act(setup,'submit')


def test_central_projection_retains_managed_mapping_request_and_order(setup):
    from backend.oslc_service.change_control import normalize,restore_summary
    from backend.oslc_service.change_dossier import build_dossier
    jobs,value,ids=setup;act(setup,'submit')
    submitted=jobs.get(value['publication_job_id']);summary=normalize('bridges',submitted)
    assert summary['type']=='oslc_cm:ChangeRequest' and summary['authorization_actor'] is None
    act(setup,'accept');act(setup,'authorize');job=jobs.get(value['publication_job_id'])
    summary=normalize('bridges',job);dossier=build_dossier('bridges',job,summary,'http://local/record')
    assert dossier['release']['order']['operation']=='publish_selected_mappings'
    assert summary['execution_state']=='Authorization recorded; verify current plan'
    projection=restore_summary({**job,'merge_change':job['change_request'],'mapping_snapshot':job['snapshot']})
    assert normalize('bridges',projection)['authorization_actor']=='owner'
    act(setup,'cancel');assert normalize('bridges',jobs.get(job['job_id']))['authorization_actor'] is None


def test_preview_and_publication_have_distinct_central_record_keys(setup):
    from backend.oslc_service.change_control import normalize
    jobs,value,ids=setup;act(setup,'submit')
    proposal=normalize('bridges',jobs.get(value['job_id']))
    publication=normalize('bridges',jobs.get(value['publication_job_id']))
    assert proposal['record_key']=='bridges:'+value['job_id']
    assert publication['record_key']=='bridges:'+value['publication_job_id']
    assert proposal['record_key']!=publication['record_key']


@pytest.mark.parametrize('corruption',['selection','actor','order','snapshot'])
def test_recovery_cannot_confirm_a_different_retained_scope(setup,corruption):
    jobs,value,ids=setup;authorize(setup);jobs.graph.lose_response=True
    with pytest.raises(TimeoutError):act(setup,'execute')
    job=jobs.get(value['publication_job_id'])
    if corruption=='selection':job['approved_ids']=['foreign-candidate']
    elif corruption=='actor':job['approved_by']='different-owner'
    elif corruption=='order':job['change_request']['order']['order_id']='foreign'
    else:job['snapshot']['source']='f'*64
    jobs.store.put(job['job_id'],job)
    with pytest.raises(BridgeConflict):act(setup,'reconcile')
    assert change.view(jobs,value['job_id'])['change_request']['state']=='needs_recovery'
    assert len(jobs.graph.calls)==1


def test_publication_without_change_request_is_blocked(setup):
    jobs,value,ids=setup
    with pytest.raises(BridgeConflict,match="Change Control"):
        jobs.publish(value["job_id"],ids,"agent-operator")
    assert jobs.graph.calls==[]
