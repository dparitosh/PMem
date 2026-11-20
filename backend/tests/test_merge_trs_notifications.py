"""Native merge review freshness reuses the atomic TRS outbox."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.mesh_store import InMemoryRegistry,PostgresRegistry
from backend.oslc_service import notifications
from backend.ontology_service.merge_change import save
from backend.Services.oslc_trs_service import OSLCTRSService

class Store(InMemoryRegistry):
    @contextmanager
    def advisory_lock(self,key):yield True
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))


def record(revision=1):
    return {'preview_id':'p','change_request':{'request_id':'p','revision':revision,'plan_digest':'a'*64,
        'state':'submitted' if revision==1 else 'accepted','reason':'Private business reason','requested_by':'owner'}}

def retain(store,revision=1):
    captured=[]
    def atomic(*args,**kwargs):
        captured.append((args,kwargs));store.put(kwargs['related_key'],kwargs['related_value'])
    notifications.retain_merge_change(SimpleNamespace(put_with_related=atomic),'p',record(revision))
    return captured[0]

@pytest.fixture
def worker(monkeypatch):
    store=Store();monkeypatch.setattr(notifications,'PostgresRegistry',lambda *args:store)
    monkeypatch.setattr(notifications,'merge_exists',lambda identifier:True)
    monkeypatch.setattr(OSLCTRSService,'is_enabled',classmethod(lambda cls:True))
    published=[]
    def publish(*args,**kwargs):published.append((args,kwargs));return {'event_id':str(len(published))}
    monkeypatch.setattr(OSLCTRSService,'publish_event',classmethod(lambda cls,*args,**kwargs:publish(*args,**kwargs)))
    return store,published


def test_state_and_outbox_intent_use_one_atomic_call_without_private_reason():
    store=Store();args,kwargs=retain(store)
    assert args==('p',record()) and kwargs['related_namespace']=='oslc_trs_outbox'
    event=kwargs['related_value']
    assert event['resource_uri']=='/oslc/change-control/records/merges/p'
    assert event['event_type']=='Modification' and 'Private business reason' not in str(event)
    assert 'owner' not in str(event)


def test_native_save_requires_atomic_state_and_notice_commit():
    class AtomicStore(PostgresRegistry):
        def __init__(self):self.atomic=Mock(side_effect=RuntimeError('transaction rolled back'))
        def put_with_related(self,*args,**kwargs):return self.atomic(*args,**kwargs)
    store=AtomicStore();fallback=Mock()
    with pytest.raises(RuntimeError):save(SimpleNamespace(registry=store,_save=fallback),'p',record())
    store.atomic.assert_called_once();fallback.assert_not_called()


def test_many_pending_revisions_coalesce_into_one_resource_notice(worker):
    store,published=worker
    for revision in range(1,70):retain(store,revision)
    assert len(store.all())==1
    notifications.reconcile(limit=1)
    assert len(published)==1 and published[0][1]['metadata']['revision']==69
    assert next(iter(store.all().values()))['status']=='completed'


def test_newer_state_during_delivery_is_not_overwritten(worker,monkeypatch):
    store,published=worker;retain(store)
    def publish(cls,*args,**kwargs):
        published.append(kwargs);retain(store,2);return {'event_id':'old-receipt'}
    monkeypatch.setattr(OSLCTRSService,'publish_event',classmethod(publish))
    notifications.reconcile()
    event=next(iter(store.all().values()))
    assert event['status']=='pending' and event['metadata']['revision']==2
    assert event['delivery_id']==event['outbox_key']+':2:'+('a'*64)


def test_delivery_failure_remains_pending_for_existing_worker(worker,monkeypatch):
    store,published=worker;retain(store)
    def fail(*args,**kwargs):raise RuntimeError('TRS temporarily unavailable')
    monkeypatch.setattr(OSLCTRSService,'publish_event',classmethod(fail))
    notifications.reconcile()
    assert next(iter(store.all().values()))['status']=='pending'


def test_disabled_trs_does_not_complete_notification(worker,monkeypatch):
    store,published=worker;retain(store)
    monkeypatch.setattr(OSLCTRSService,'publish_event',classmethod(lambda *args,**kwargs:{'status':'disabled'}))
    notifications.reconcile()
    assert next(iter(store.all().values()))['status']=='pending'


def test_revision_delivery_ids_are_deterministic_and_distinct():
    store=Store();one=retain(store)[1]['related_value'];repeated=retain(store)[1]['related_value'];two=retain(store,2)[1]['related_value']
    assert one['delivery_id']==repeated['delivery_id']!=two['delivery_id']
    assert one['outbox_key']==two['outbox_key']


def test_worker_rechecks_current_notice_inside_resource_lock(worker):
    store,published=worker;retain(store)
    @contextmanager
    def lock(key):retain(store,2);yield True
    store.advisory_lock=lock
    notifications.reconcile()
    assert len(published)==1 and published[0][1]['metadata']['revision']==2


@pytest.mark.parametrize('event_type',['Modification','Deletion'])
@pytest.mark.parametrize('retained',[True,False])
def test_base_recovers_merge_membership_without_old_events_and_excludes_removed_records(monkeypatch,retained,event_type):
    from backend.oslc_service import trs_snapshot
    from backend.tests.test_oslc_functional_fixes import service_fixture
    service=service_fixture()
    path='/oslc/change-control/records/merges/p'
    service._load=lambda:{'events':[{'resource_uri':path,'event_type':event_type,'event_id':'old'}],'counter':1}
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def run(self,*args):return []
    monkeypatch.setattr(trs_snapshot,'get_driver',lambda:SimpleNamespace(session=lambda **kwargs:Session()))
    monkeypatch.setattr(trs_snapshot,'get_config',lambda:SimpleNamespace(database='graph',query_timeout=30))
    monkeypatch.setattr(trs_snapshot,'merge_resources',lambda current:[{'resource_uri':'https://host'+path,'title':'Proposal'}] if retained else [])
    result=trs_snapshot.build_snapshot(service,10)
    assert result['total_count']==int(retained)
    assert bool(result['members']) is retained
    # Also recover after this resource's last event has left the bounded changelog.
    service._load=lambda:{'events':[],'counter':10000}
    assert trs_snapshot.build_snapshot(service,10)['total_count']==int(retained)


def test_removed_pending_merge_emits_deletion_not_modification(worker,monkeypatch):
    store,published=worker;retain(store)
    monkeypatch.setattr(notifications,'merge_exists',lambda identifier:False)
    notifications.reconcile()
    assert published[0][0][1]=='Deletion'
    event=next(iter(store.all().values()))
    assert event['status']=='completed' and event['metadata']=={'preview_id':'p','deleted':True}
    assert event['delivery_id'].endswith(':deleted')


def test_completed_modification_is_reconciled_after_later_removal(worker,monkeypatch):
    store,published=worker;retain(store);notifications.reconcile()
    prior=next(iter(store.all().values()))
    monkeypatch.setattr(notifications,'missing_merge_events',lambda current,limit:[prior])
    monkeypatch.setattr(notifications,'merge_exists',lambda identifier:False)
    notifications.reconcile();notifications.reconcile()
    assert [call[0][1] for call in published]==['Modification','Deletion']


def test_dependency_failure_never_means_deletion(worker,monkeypatch):
    store,published=worker;retain(store)
    def unavailable(identifier):raise RuntimeError('database unavailable')
    monkeypatch.setattr(notifications,'merge_exists',unavailable)
    notifications.reconcile()
    assert published==[] and next(iter(store.all().values()))['status']=='pending'


def test_recreated_record_does_not_receive_a_stale_pending_deletion(worker,monkeypatch):
    store,published=worker;retain(store);key=next(iter(store.all()))
    value=store.get(key);value['event_type']='Deletion';store.put(key,value)
    notifications.reconcile()
    assert published==[] and store.get(key)['status']=='pending'


def test_deletion_does_not_overwrite_newer_native_notice(worker,monkeypatch):
    store,published=worker;retain(store)
    def missing(identifier):retain(store,2);return False
    monkeypatch.setattr(notifications,'merge_exists',missing)
    notifications.reconcile()
    assert published==[]
    event=next(iter(store.all().values()))
    assert event['status']=='pending' and event['metadata']['revision']==2


def test_deletion_retry_retains_the_same_delivery_identity(worker,monkeypatch):
    store,published=worker;retain(store)
    monkeypatch.setattr(notifications,'merge_exists',lambda identifier:False)
    def fail(*args,**kwargs):raise RuntimeError('lost response')
    monkeypatch.setattr(OSLCTRSService,'publish_event',classmethod(fail))
    notifications.reconcile();first=next(iter(store.all().values()))['delivery_id']
    notifications.reconcile();assert next(iter(store.all().values()))['delivery_id']==first


@pytest.mark.parametrize('head,after,expected',[(0,50,True),(3,50,True),(50,50,False),(51,50,False)])
def test_reset_stream_ahead_cursor_requires_rebase(monkeypatch,head,after,expected):
    monkeypatch.setattr(OSLCTRSService,'_load',classmethod(lambda cls:{'events':[],'counter':head}))
    result=OSLCTRSService.change_log(after=after)
    assert result['rebase_required'] is expected
    assert result['head_order']==head
