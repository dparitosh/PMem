from types import SimpleNamespace
from copy import deepcopy
import pytest
from rdflib import Graph,URIRef,Literal
from backend.mesh_store import InMemoryRegistry
from backend.Services.oslc_trs_service import OSLCTRSService as trs
from backend.oslc_service import notifications
from backend.data_pipeline_service import reporting_trs as consumer,reporting_store as reporting

@pytest.fixture
def stream(monkeypatch):
    class Atomic(InMemoryRegistry):
        def put_with_related(self,key,value,*,related_namespace,related_key,related_value):
            self.put_many({key:value,related_key:related_value});return value
    store=Atomic('oslc_trs');monkeypatch.setattr(trs,'_store',store)
    monkeypatch.setattr(trs,'_storage_backend',classmethod(lambda cls:'postgres'))
    monkeypatch.setattr(trs,'is_enabled',classmethod(lambda cls:True))
    return store


def test_stream_identity_survives_reload_but_changes_after_reset_with_regrown_counter(stream):
    first=trs.change_log(after=0)['stream_id'];assert first==trs.change_log(after=0)['stream_id']
    stream.put('change_log',{'counter':10000,'events':[]})
    second=trs.change_log(after=10)
    assert second['head_order']>10 and second['stream_id']!=first


def test_delivery_deduplication_is_scoped_to_stream_generation(stream):
    one=trs.publish_event('/oslc/shapes/parts','Modification',delivery_id='same-notice')
    assert trs.publish_event('/oslc/shapes/parts','Modification',delivery_id='same-notice')['event_id']==one['event_id']
    stream.put('change_log',{'counter':0,'events':[]})
    two=trs.publish_event('/oslc/shapes/parts','Modification',delivery_id='same-notice')
    assert one['event_id']!=two['event_id'] and two['order']==1


def test_base_cursor_from_old_stream_cannot_continue_after_reset(stream):
    identifier=trs.change_log()['stream_id'];stream.put('change_log',{'counter':500,'events':[]})
    with pytest.raises(RuntimeError,match='stream reset'):
        trs._base_page('snapshot',{'stream_id':identifier,'members':[],'total_count':0,'cutoff_order':0},0,10)


def test_consumer_rebases_when_counter_regrew_beyond_old_cursor(monkeypatch):
    state={'phase':'events','trs_after':50,'active_generation':'retained-report','stream_id':'old-stream'}
    provider=SimpleNamespace(changes=lambda after:{'events':[{'order':51,'event_type':'Modification','resource_uri':'http://provider/oslc/resources/part'}],'head_order':100,'stream_id':'new-stream'})
    monkeypatch.setattr(reporting,'commit',lambda identifier,expected,updated,changes:updated)
    result=consumer._events_step('feed',state,{},provider,float('inf'))
    assert result['phase']=='base' and result['active_generation']=='retained-report' and result['base_cutoff'] is None


def test_base_generation_change_between_pages_restarts_staging(monkeypatch):
    state={**consumer.begin({},'test'),'base_started':True,'base_cutoff':10,'base_stream_id':'old','base_cursor':{'snapshot_id':'retained'}}
    provider=SimpleNamespace(base=lambda cursor:{'members':[],'cutoff_order':10,'stream_id':'new','nextPage':None})
    monkeypatch.setattr(reporting,'commit',lambda identifier,expected,updated,changes:updated)
    result=consumer._base_step('feed',state,{},provider,float('inf'))
    assert result['base_started'] is False and result['base_stream_id'] is None


@pytest.mark.parametrize('source,namespace,key,identifier',[('pipeline','data_job_runs','run','run'),('publications','ontology_publication_jobs_v1','ontology','ontology'),('bridges','semantic_bridge_jobs_v1','bridge-publication-p','bridge-publication-p'),('product_changes','data_product_approvals','request:product:1','product:1')])
def test_native_state_and_freshness_notice_share_one_transaction_without_private_reason(source,namespace,key,identifier):
    seen=[];record={'change_request':{'revision':2,'plan_digest':'a'*64,'state':'accepted','reason':'PRIVATE_REASON'}}
    owner=SimpleNamespace(namespace=namespace,put_with_related=lambda *args,**kwargs:seen.append((args,kwargs)))
    notifications.retain_native_change(owner,key,record,source,identifier)
    assert seen[0][0]==(key,record)
    notice=seen[0][1]['related_value']
    assert notice['resource_uri'].endswith('/'+source+'/'+__import__('urllib.parse',fromlist=['quote']).quote(identifier,safe=''))
    assert 'PRIVATE_REASON' not in str(notice)


def test_stream_identity_is_present_in_trs_rdf(stream):
    from backend.oslc_service.representation import rdf_graph
    payload=trs.change_log();graph=rdf_graph(payload)
    assert (URIRef(payload['uri']),URIRef('urn:depo:oslc:extension:stream_id'),Literal(payload['stream_id'])) in graph
