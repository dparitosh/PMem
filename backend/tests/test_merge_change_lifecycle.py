from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import Lock, Event
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.merge_service import GovernedMergeService
from backend.ontology_service.merge_change import ChangeConflict

class Store(InMemoryRegistry):
    def __init__(self):super().__init__();self.lock=Lock()
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))
    @contextmanager
    def advisory_lock(self,key):
        acquired=self.lock.acquire(blocking=False)
        try:yield acquired
        finally:
            if acquired:self.lock.release()

@pytest.fixture
def service():
    value=object.__new__(GovernedMergeService);value.registry=Store()
    value.catalog=SimpleNamespace(get=lambda key:{'ontology_id':key},with_publication_lock=lambda key,operation:operation())
    value.registry.put('p',{'preview_id':'p','ontology_name':'Combined','prefix':'combined','description':'Exact reviewed draft',
        'sources':[{'ontology_id':'a','artifact_sha256':'a'*64},{'ontology_id':'b','artifact_sha256':'b'*64}],
        'source_ontology_ids':['a','b'],'turtle':'<urn:a> <urn:p> <urn:b> .','governance_policy_sha256':'c'*64})
    def native(identifier,actor,approval_policy=None):
        record=value.registry.get(identifier)
        result={'preview_id':identifier,'status':'merged','ontology':{'ontology_id':'merged'}}
        record.update(applied_result=result,approved_by=actor);value.registry.put(identifier,record)
        return result
    value._apply_native=Mock(side_effect=native)
    def receipt(identifier):
        result=value.registry.get(identifier).get('applied_result')
        if not result:raise ValueError('No completed merge receipt is retained')
        return result
    value.receipt=Mock(side_effect=receipt)
    return value

def act(service,action,actor='owner',reason='Review baseline'):
    current=service.change_status('p');change=current['change_request']
    return service.change_transition('p',action,actor,change['revision'] if change else 0,current['current_plan_digest'],reason)

def authorize(service):
    act(service,'submit','requester');act(service,'accept','reviewer');return act(service,'authorize','authorizer')

def test_request_acceptance_is_not_execution_authority(service):
    act(service,'submit');act(service,'accept')
    with pytest.raises(ChangeConflict):service.apply('p','executor')
    service._apply_native.assert_not_called()
    assert service.change_status('p')['change_request']['state']=='accepted'

def test_exact_order_executes_once_with_authorizer_and_executor_retained(service):
    authorize(service);result=act(service,'execute','executor')
    assert result['change_request']['state']=='executed'
    service._apply_native.assert_called_once_with('p','authorizer',approval_policy=None)
    assert service.registry.get('p')['approved_by']=='authorizer'
    history=result['change_request']['history']
    assert any(item['action']=='execute' and item['actor']=='executor' for item in history)
    service.apply('p','executor');service._apply_native.assert_called_once()

def test_duplicate_submit_and_stale_review_cannot_overwrite_decisions(service):
    first=act(service,'submit');act(service,'accept')
    current=service.change_status('p')
    repeated=service.change_transition('p','submit','other',0,first['current_plan_digest'],'Different reason')
    assert repeated['change_request']==current['change_request']
    with pytest.raises(ChangeConflict):service.change_transition('p','reject','other',1,first['current_plan_digest'],'Stale rejection')
    assert service.change_status('p')['change_request']['state']=='accepted'

def test_modified_plan_cannot_use_old_authorization(service):
    old=authorize(service);record=service.registry.get('p');record['prefix']='changed';service.registry.put('p',record)
    assert service.change_status('p')['scope_changed']
    with pytest.raises(ChangeConflict):service.apply('p','executor')
    service._apply_native.assert_not_called()

def test_order_cannot_publish_or_execute_after_cancel(service):
    authorize(service)
    with pytest.raises(ChangeConflict,match='draft only'):service.apply('p','executor',publish_requested=True)
    service._apply_native.assert_not_called()
    act(service,'cancel')
    with pytest.raises(ChangeConflict):service.apply('p','executor')

def test_uncertain_failure_requires_receipt_verification_and_never_replays(service):
    authorize(service);native=service._apply_native.side_effect
    def uncertain(*args,**kwargs):native(*args,**kwargs);raise RuntimeError('connection interrupted after native result')
    service._apply_native.side_effect=uncertain
    with pytest.raises(RuntimeError):act(service,'execute','executor')
    assert service.change_status('p')['change_request']['state']=='needs_recovery'
    with pytest.raises(ChangeConflict):service.apply('p','executor')
    result=act(service,'reconcile','reviewer')
    assert result['change_request']['state']=='executed'
    assert service._apply_native.call_count==1

def test_missing_receipt_cannot_claim_execution_or_replay(service):
    authorize(service);service._apply_native.side_effect=RuntimeError('unverified failure')
    with pytest.raises(RuntimeError):act(service,'execute')
    with pytest.raises(ValueError,match='No completed'):act(service,'reconcile')
    assert service.change_status('p')['change_request']['state']=='needs_recovery'
    assert service._apply_native.call_count==1

def test_two_executors_cannot_run_the_same_native_write(service):
    snapshot=authorize(service);started=Event();release=Event();native=service._apply_native.side_effect
    def slow(*args,**kwargs):started.set();release.wait(5);return native(*args,**kwargs)
    service._apply_native.side_effect=slow
    def execute():return service.change_transition('p','execute','executor',snapshot['change_request']['revision'],snapshot['current_plan_digest'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        running=pool.submit(execute);assert started.wait(5)
        with pytest.raises(ChangeConflict):execute()
        release.set();assert running.result()['change_request']['state']=='executed'
    assert service._apply_native.call_count==1

def test_historical_execution_cannot_be_retroactively_approved(service):
    service._apply_native('p','historic')
    with pytest.raises(ChangeConflict,match='retroactively'):act(service,'submit')

def test_real_native_merge_uses_existing_catalog_validation_and_receipt(tmp_path:Path):
    from backend.ontology_service.catalog import OntologyCatalog
    from test_governed_merge_service import IntelligenceStub
    catalog=OntologyCatalog(root=tmp_path/'catalog')
    items=[catalog.register(content=f'@prefix ex: <https://example.test/> . ex:{name} ex:label "{name}" .'.encode(),filename=name+'.ttl',ontology_name=name,prefix=name.lower()) for name in ('One','Two')]
    value=GovernedMergeService(catalog,IntelligenceStub(),catalog.root)
    preview=value.preview({'source_ontology_ids':[item['ontology_id'] for item in items],'ontology_name':'Combined','prefix':'combined'})
    identifier=preview['preview_id']
    for action in ('submit','accept','authorize','execute'):
        current=value.change_status(identifier);change=current['change_request']
        value.change_transition(identifier,action,'owner',change['revision'] if change else 0,current['current_plan_digest'],'Business review')
    result=value.receipt(identifier)
    assert result['status']=='merged' and result['ontology']['provenance']['approved_by']=='owner'
    assert value.change_status(identifier)['change_request']['state']=='executed'


def test_review_updates_record_freshness_without_changing_plan_identity(service):
    before=service.change_status('p')['current_plan_digest']
    submitted=act(service,'submit');accepted=act(service,'accept')
    assert service.registry.get('p')['updated_at']==accepted['change_request']['history'][-1]['at']
    assert before==submitted['current_plan_digest']==accepted['current_plan_digest']
