import asyncio
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import Lock
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry
from backend.data_product_service import router as native,product_change as change

class Store(InMemoryRegistry):
    def __init__(self,namespace):super().__init__(namespace);self.locks={}
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))
    def put_with_related(self,key,value,**kwargs):self.put(key,value);return value
    @contextmanager
    def advisory_lock(self,key):
        lock=self.locks.setdefault(key,Lock());acquired=lock.acquire(blocking=False)
        try:yield acquired
        finally:
            if acquired:lock.release()

@pytest.fixture
def setup(tmp_path,monkeypatch):
    source=tmp_path/'source.txt';source.write_text('retained evidence')
    payload={'product_id':'quality','name':'Quality evidence','version':'1.0.0','domain':'engineering','owner':'owner',
        'steward':'steward','classification':'internal','lifecycle_state':'published','artifacts':[{'artifact_id':'sha256:fixture'}],
        'semantic_releases':[{'asset_id':'release','version':'1.0.0'}],'idempotency_key':'input-request','approved_by':'untrusted-body'}
    monkeypatch.setattr(native,'root',tmp_path/'packages')
    monkeypatch.setattr(native,'store',Store('data_products'));monkeypatch.setattr(native,'approval_store',Store('data_product_approvals'))
    monkeypatch.setattr(native,'_validate',lambda payload:([({'artifact_id':'sha256:fixture'},source)],[]))
    async def lineage(*args):return {'verified':True}
    async def release(value):return value
    monkeypatch.setattr(native,'resolve_lineage',lineage);monkeypatch.setattr(native,'resolve_approved_release',release)
    delivery={'available':False}
    async def catalog(record):
        return {**record,'status':'published' if delivery['available'] else 'pending_catalog_registration',
            'catalog_registered_at':'2026-11-14T12:00:00Z' if delivery['available'] else None}
    monkeypatch.setattr(native,'_register_catalog',catalog)
    return payload,source,delivery

def run(value):return asyncio.run(value)
def act(action,actor='owner',reason='Review release'):
    state=run(change.view('quality:1.0.0'));request=state['change_request']
    return run(change.command('quality:1.0.0',action,actor,request['revision'],state['current_plan_digest'],reason))
def submit(setup):return run(change.submit(setup[0],'Release quality evidence','requester'))
def authorize(setup):submit(setup);act('accept','reviewer');return act('authorize','authorizer')


def test_product_request_is_not_a_package_and_acceptance_is_not_publication(setup):
    submit(setup);act('accept')
    assert native.store.all()=={}
    record=run(change.load('quality:1.0.0'))
    assert record['change_request']['requested_by']=='requester' and 'approved_by' not in record['publication']
    artifacts,_=run(change.checked_payload(record['publication']))
    with pytest.raises(HTTPException):run(change.guarded_publish(record['publication'],'executor',artifacts))
    assert native.store.all()=={}


def test_package_is_not_complete_until_catalog_delivery_is_verified(setup):
    authorize(setup);result=act('execute','executor')
    assert result['change_request']['state']=='awaiting_delivery'
    record=native.store.get('quality:1.0.0');assert record['approved_by']=='authorizer'
    assert Path(record['package_storage']['zip_path']).is_file()
    setup[2]['available']=True
    assert act('retry_delivery')['change_request']['state']=='executed'
    assert native.store.get('quality:1.0.0')['status']=='published'


def test_changed_artifact_cannot_execute_the_old_order(setup):
    authorize(setup);setup[1].write_text('changed evidence')
    state=run(change.load('quality:1.0.0'))
    with pytest.raises(HTTPException) as failure:
        run(change.command('quality:1.0.0','execute','executor',state['change_request']['revision'],state['plan_digest']))
    assert failure.value.status_code==409 and native.store.all()=={}


def test_cancelled_order_cannot_use_legacy_publish_to_bypass_review(setup):
    authorize(setup);act('cancel')
    record=run(change.load('quality:1.0.0'));artifacts,_=run(change.checked_payload(record['publication']))
    with pytest.raises(HTTPException):run(change.guarded_publish(record['publication'],'executor',artifacts))
    assert native.store.all()=={}


def test_lost_publication_response_recovers_only_the_matching_package(setup,monkeypatch):
    setup[2]['available']=True;authorize(setup);operation=native._publish_locked;calls=[]
    async def lost(*args):calls.append(True);await operation(*args);raise TimeoutError('lost response')
    monkeypatch.setattr(native,'_publish_locked',lost)
    with pytest.raises(TimeoutError):act('execute')
    assert run(change.view('quality:1.0.0'))['change_request']['state']=='needs_recovery'
    assert act('reconcile')['change_request']['state']=='executed' and len(calls)==1


def test_corrupt_package_cannot_claim_governed_completion(setup):
    authorize(setup);act('execute');record=native.store.get('quality:1.0.0')
    Path(record['package_storage']['zip_path']).write_text('corrupt package')
    with pytest.raises(HTTPException) as failure:act('reconcile')
    assert failure.value.status_code==409
    assert run(change.load('quality:1.0.0'))['change_request']['state']=='awaiting_delivery'


def test_expired_original_artifact_does_not_prevent_retained_package_recovery(setup,monkeypatch):
    authorize(setup);act('execute');setup[1].unlink()
    monkeypatch.setattr(native,'_validate',Mock(side_effect=AssertionError('Recovery must use retained package')))
    setup[2]['available']=True
    assert act('retry_delivery')['change_request']['state']=='executed'


def test_duplicate_submission_preserves_request_and_changed_scope_conflicts(setup):
    first=submit(setup);act('accept');second=submit(setup)
    assert second['change_request']['state']=='accepted' and first['current_plan_digest']==second['current_plan_digest']
    changed={**setup[0],'name':'Different product'}
    with pytest.raises(HTTPException) as failure:run(change.submit(changed,'Other scope','requester'))
    assert failure.value.status_code==409


def test_stale_reviewer_cannot_overwrite_a_later_decision(setup):
    first=submit(setup);act('accept')
    with pytest.raises(HTTPException):run(change.command('quality:1.0.0','reject','other',first['change_request']['revision'],first['current_plan_digest'],'stale'))
    assert run(change.load('quality:1.0.0'))['change_request']['state']=='accepted'

def test_central_projection_preserves_request_and_package_separation(setup):
    from backend.oslc_service.change_control import normalize
    submit(setup)
    record=run(change.load('quality:1.0.0'))
    row=normalize('product_changes',record)
    assert row['identifier']=='quality:1.0.0'
    assert row['type']=='oslc_cm:ChangeRequest'
    assert not native.store.get('quality:1.0.0')
    authorize(setup);act('execute')
    pending=normalize('product_changes',run(change.load('quality:1.0.0')))
    assert pending['delivery_state']=='Not verified'
    setup[2]['available']=True;act('retry_delivery')
    completed=normalize('product_changes',run(change.load('quality:1.0.0')))
    assert completed['delivery_state']=='Publication receipt retained'


def test_product_commands_reject_actor_spoofing_and_non_product_actions():
    from backend.depo_platform.request_bodies import ProductChangeCommand
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ProductChangeCommand(action='execute',expected_revision=1,expected_plan_digest='a'*64,approved_by='forged')
    with pytest.raises(ValidationError):
        ProductChangeCommand(action='submit',expected_revision=1,expected_plan_digest='a'*64)
