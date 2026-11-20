"""Workflow definition changes retain authority and execute atomically."""
from copy import deepcopy
from uuid import uuid4
import pytest
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import definition_changes as changes, job_definitions
from backend.depo_platform import approval_matrix
from backend.depo_platform.request_bodies import DefinitionChangeSubmission, MergeChangeCommand

class Store(InMemoryRegistry):
    def get(self,key): return deepcopy(super().get(key))
    def put(self,key,value): return super().put(key,deepcopy(value))

@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(changes,'store',Store('workflow-changes-test'))
    monkeypatch.setattr(job_definitions,'store',Store('workflow-definitions-test'))
    monkeypatch.setattr(approval_matrix,'configuration',Store('workflow-matrix-test'))
    record={'job_id':'review-source','version':'1.0.0','name':'Review engineering source','lifecycle_state':'draft','enabled':True,'schedule':None}
    job_definitions.store.put(job_definitions.key('review-source','1.0.0'),record)
    return DefinitionChangeSubmission(request_id=str(uuid4()),job_id='review-source',version='1.0.0',operation='approve',parameters={},reason='Release reviewed workflow')

def act(identifier,action,actor='reviewer'):
    view=changes.view(identifier)
    return changes.command(identifier,MergeChangeCommand(action=action,expected_revision=view['change_request']['revision'],expected_plan_digest=view['change_request']['plan_digest'],reason='Reviewed'),actor)

def test_only_authorized_order_updates_definition(state):
    request=changes.submit(state,'requester')
    with pytest.raises(HTTPException):act(state.request_id,'execute')
    assert job_definitions.get(state.job_id,state.version)['lifecycle_state']=='draft'
    act(state.request_id,'accept');act(state.request_id,'authorize')
    result=act(state.request_id,'execute','executor')
    assert result['authorization_valid'] and result['already_applied']
    assert job_definitions.get(state.job_id,state.version)['approved_by']=='executor'
    assert act(state.request_id,'execute')['receipt']==result['receipt']

def test_changed_definition_blocks_execution_but_can_cancel(state):
    changes.submit(state,'requester');act(state.request_id,'accept');act(state.request_id,'authorize')
    record=job_definitions.get(state.job_id,state.version);record['name']='Changed after review'
    job_definitions.store.put(job_definitions.key(state.job_id,state.version),record)
    with pytest.raises(HTTPException):act(state.request_id,'execute')
    assert act(state.request_id,'cancel')['change_request']['state']=='cancelled'

def test_identity_and_scope_cannot_be_reused(state):
    with pytest.raises(HTTPException):changes.submit(state,'')
    changes.submit(state,'requester')
    with pytest.raises(HTTPException):changes.submit(state,'other-requester')
    assert changes.submit(state,'requester')['preview_id']==state.request_id

def test_legacy_route_cannot_bypass_co(state):
    with pytest.raises(HTTPException):changes.execute_legacy(state.job_id,state.version,'approve',{}, {},'reviewer')
    assert job_definitions.get(state.job_id,state.version)['lifecycle_state']=='draft'


def revision_request(state):
    original=job_definitions.get(state.job_id,state.version)
    original.update(lifecycle_state='approved',allowed_standards=['ap242'],job_type='validate-semantic-batch')
    job_definitions.store.put(job_definitions.key(state.job_id,state.version),original)
    return state.model_copy(update={'operation':'revise','parameters':{'version':'1.0.1','allowed_standards':['ap242','sysml-v1']}}),original


def test_revised_sources_create_a_new_approved_version_and_preserve_original(state):
    request,original=revision_request(state)
    changes.submit(request,'requester');act(request.request_id,'accept');act(request.request_id,'authorize')
    result=act(request.request_id,'execute','executor')
    assert result['already_applied'] and result['authorization_valid']
    assert job_definitions.get(request.job_id,'1.0.0')==original
    revised=job_definitions.get(request.job_id,'1.0.1')
    assert revised['allowed_standards']==['ap242','sysml-v1'] and revised['schedule'] is None
    assert revised['approved_by']=='executor' and revised['derived_from_version']=='1.0.0'
    assert act(request.request_id,'execute')['receipt']==result['receipt']


def test_competing_revision_cannot_overwrite_an_existing_target(state):
    request,original=revision_request(state)
    other=request.model_copy(update={'request_id':str(uuid4())})
    for value in (request,other):
        changes.submit(value,'requester');act(value.request_id,'accept');act(value.request_id,'authorize')
    act(request.request_id,'execute')
    retained=job_definitions.get(request.job_id,'1.0.1')
    with pytest.raises(HTTPException):act(other.request_id,'execute')
    assert job_definitions.get(request.job_id,'1.0.1')==retained
    assert job_definitions.get(request.job_id,'1.0.0')==original


def test_unknown_standard_or_non_new_version_is_not_a_reviewable_revision(state):
    request,_=revision_request(state)
    for parameters in ({'version':'1.0.0','allowed_standards':['ap242']},{'version':'1.0.1','allowed_standards':['../secret']}):
        with pytest.raises(HTTPException):changes.submit(request.model_copy(update={'parameters':parameters}),'requester')
