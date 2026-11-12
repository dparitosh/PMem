import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rdflib import URIRef, RDF
from backend.mesh_store import InMemoryRegistry
from backend.Services.oslc_service import OSLCService
from backend.Services.oslc_query_service import OSLCQueryParameters
from backend.oslc_service.identity import resource_uri
from backend.oslc_service.representation import rdf_graph
from backend.oslc_service.sync import OSLCSyncStore, OSLCSynchronizer
from backend.oslc_service import trs_snapshot


def test_exact_version_scope_legacy_fallback_is_only_unversioned():
    for method in [OSLCService._build_resource_query,OSLCService._build_count_query]:
        query,parameters=method(OSLCQueryParameters(),ontology_scope={'ontology_id':'a','prefix':'same'})
        assert "toString(coalesce(n.ontology_id, '')) = '' AND $ontology_prefix" in query
        assert parameters['ontology_id']=='a'


def test_resource_links_bind_the_ontology_version():
    a=resource_uri('https://host',{'uri':'urn:part:1','ontology_id':'a'},'old')
    b=resource_uri('https://host',{'uri':'urn:part:1','ontology_id':'b'},'new')
    assert a!=b and a.endswith('?ontology_id=a')
    assert a==resource_uri('https://host',{'uri':'urn:part:1','ontology_id':'a'},'recreated')


def test_ambiguous_resource_never_returns_arbitrary_revision():
    with patch('backend.Services.oslc_service.GraphViewService._run',return_value=[{'element_id':'a'},{'element_id':'b'}]):
        with pytest.raises(ValueError,match='ambiguous'):OSLCService.get_resource('uri:urn:part:1')


def test_resource_read_filters_exact_version():
    with patch('backend.Services.oslc_service.GraphViewService._run',return_value=[]) as run:
        assert OSLCService.get_resource('uri:urn:part:1',ontology_id='a') is None
    assert run.call_args.args[1]['ontology_id']=='a'
    assert '$ontology_id IS NULL OR n.ontology_id = $ontology_id' in run.call_args.args[0]


def test_trs_rdf_has_typed_events_changed_resource_and_order():
    trs='http://open-services.net/ns/core/trs#'
    graph=rdf_graph({'uri':'https://host/oslc/trs/changelog','type':'trs:ChangeLog',
        'events':[{'event_id':'e','event_type':'Modification','order':4,'resource_uri':'https://host/oslc/resources/x'}]})
    node=next(graph.objects(URIRef('https://host/oslc/trs/changelog'),URIRef(trs+'change')))
    assert (node,RDF.type,URIRef(trs+'Modification')) in graph
    assert str(next(graph.objects(node,URIRef(trs+'changed'))))=='https://host/oslc/resources/x'
    assert int(next(graph.objects(node,URIRef(trs+'order'))))==4


def test_trs_base_rdf_has_cutoff_event():
    graph=rdf_graph({'uri':'https://host/oslc/trs/base?snapshot_id=x','type':'trs:Base','members':[], 'cutoff_event':'e'})
    assert list(graph.objects(None,URIRef('http://open-services.net/ns/core/trs#cutoffEvent')))


def test_snapshot_records_provider_actor_and_rejects_tampering(tmp_path):
    store=OSLCSyncStore();store.root=tmp_path
    client=SimpleNamespace(base_url='https://provider',query=lambda *a:{'members':[{'id':'r1'}]})
    snapshot=OSLCSynchronizer(client,store).pull('requirements',{},requested_by='reviewer')
    assert snapshot['requested_by']=='reviewer' and snapshot['provider_url']=='https://provider'
    assert len(snapshot['content_sha256'])==64
    path=store._path(snapshot['sync_id']);data=json.loads(path.read_text());data['resources'][0]['id']='changed';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='integrity'):store.get(snapshot['sync_id'])


def service_fixture():
    return SimpleNamespace(_store=InMemoryRegistry(),_load=lambda:{'events':[],'counter':0},
        base_url=lambda:'https://host',base_resource_uri=lambda:'https://host/oslc/trs/base',
        _external_resource_uri=lambda path:'https://host'+path)


def test_streamed_base_exceeds_old_limit_without_loading_one_large_record(monkeypatch):
    service=service_fixture()
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def run(self,query):
            assert 'StagedOntologyResource' in query.text and 'OntologyPublication' in query.text
            return ({'element_id':str(i),'uri':None,'ontology_id':None,'title':'item'} for i in range(50001))
    monkeypatch.setattr(trs_snapshot,'get_driver',lambda:SimpleNamespace(session=lambda **kw:Session()))
    monkeypatch.setattr(trs_snapshot,'get_config',lambda:SimpleNamespace(database='graph',query_timeout=30))
    result=trs_snapshot.build_snapshot(service,2)
    assert result['total_count']==50001 and len(result['members'])==2
    meta=service._store.get('base:'+result['snapshot_id'])
    assert 'members' not in meta
    assert max(len(v.get('members',[])) for v in service._store.values.values())<=1000
    last=trs_snapshot.read_page(service,result['snapshot_id'],meta,50000,2)
    assert len(last['members'])==1 and last['nextPage'] is None


def test_missing_snapshot_chunk_never_silently_returns_partial():
    service=service_fixture()
    with pytest.raises(RuntimeError,match='missing'):
        trs_snapshot.read_page(service,'x',{'total_count':2,'chunk_size':1000},0,2)


def test_publication_and_notification_intent_use_one_atomic_storage_call():
    from backend.oslc_service.notifications import retain_publication
    calls=[]
    store=SimpleNamespace(put_with_related=lambda *args,**kwargs:calls.append((args,kwargs)))
    retain_publication(store,'ontology',{'publication_id':'digest','status':'published'})
    assert calls[0][1]['related_namespace']=='oslc_trs_outbox'
    assert calls[0][1]['related_value']['status']=='pending'


def test_notification_retry_after_lost_response_keeps_one_event(monkeypatch):
    from backend.Services.oslc_trs_service import OSLCTRSService
    class Store(InMemoryRegistry):
        namespace='test'
        @contextmanager
        def advisory_lock(self,key):yield True
        def put_with_related(self,key,value,*,related_namespace,related_key,related_value):
            self.put(key,value);self.put(related_key,related_value)
    store=Store()
    monkeypatch.setattr(OSLCTRSService,'_store',store)
    monkeypatch.setattr(OSLCTRSService,'_storage_backend',classmethod(lambda cls:'postgres'))
    monkeypatch.setattr(OSLCTRSService,'is_enabled',classmethod(lambda cls:True))
    first=OSLCTRSService.publish_event('/oslc/shapes/a','Modification',delivery_id='receipt-1')
    second=OSLCTRSService.publish_event('/oslc/shapes/a','Modification',delivery_id='receipt-1')
    assert first['event_id']==second['event_id']
    assert store.get('change_log')['counter']==1


def test_worker_failure_retains_notification_for_retry(monkeypatch):
    from backend.oslc_service import notifications
    from backend.Services.oslc_trs_service import OSLCTRSService
    event={'delivery_id':'a','status':'pending','resource_uri':'/oslc/shapes/a','event_type':'Modification','title':'changed','metadata':{}}
    store=InMemoryRegistry();store.put('a',event)
    monkeypatch.setattr(notifications,'PostgresRegistry',lambda *a:store)
    monkeypatch.setattr(OSLCTRSService,'is_enabled',classmethod(lambda cls:True))
    monkeypatch.setattr(OSLCTRSService,'publish_event',classmethod(lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('database unavailable'))))
    notifications.reconcile()
    assert store.get('a')['status']=='pending'


def test_discovery_uses_advertised_query_base_and_stays_on_provider(monkeypatch):
    from backend.oslc_service.client import OSLCClient
    client=OSLCClient();client.base_url='https://provider.test/context'
    monkeypatch.setattr(client,'discover',lambda:{'serviceProviders':[{'uri':'https://provider.test/context/providers/p'}]})
    calls=[]
    def request(path,params=None,**kwargs):
        calls.append(path)
        if path=='providers/p':return {'queryCapabilities':[{'resourceTypeUri':'http://open-services.net/ns/rm#Requirement','queryBase':'https://provider.test/context/rm/items'}]}
        return {'members':[]}
    monkeypatch.setattr(client,'_request',request)
    assert client.query('requirements',{})=={'members':[]}
    assert calls==['providers/p','rm/items']
    monkeypatch.setattr(client,'discover',lambda:{'queryCapabilities':[{'resourceType':'requirements','queryBase':'https://evil.test/items'}]})
    with pytest.raises(ValueError,match='configured provider'):client.query('requirements',{})


def test_preparation_rejects_incomplete_and_legacy_sources(monkeypatch):
    from backend.oslc_service import preparation
    monkeypatch.setattr(preparation.OSLCSyncStore,'get',lambda *a:{'complete':False})
    with pytest.raises(ValueError,match='complete'):preparation.execute(None,{'snapshot_id':'x'},correlation_id='c')
    monkeypatch.setattr(preparation.OSLCSyncStore,'get',lambda *a:{'complete':True,'status':'staged'})
    with pytest.raises(ValueError,match='provenance'):preparation.execute(None,{'snapshot_id':'x'},correlation_id='c')


def test_preparation_retains_records_but_does_not_publish(monkeypatch):
    from backend.oslc_service import preparation
    monkeypatch.setattr(preparation,'authorize',lambda *a:None)
    snapshot={'complete':True,'status':'staged','content_sha256':'digest','provider_url':'https://provider',
              'requested_by':'reader','sync_id':'x','resources':[{'id':'req-1','title':'Temperature requirement'}]}
    monkeypatch.setattr(preparation.OSLCSyncStore,'get',lambda *a:snapshot)
    saved=[]
    monkeypatch.setattr(preparation,'ArtifactStore',lambda:SimpleNamespace(ingest_bytes=lambda data,**kw:(saved.append((data,kw)) or {'artifact_id':'sha256:records'})))
    result=preparation.execute(None,{'snapshot_id':'x','content_sha256':'digest'},correlation_id='c')
    assert result['publication']=='not_attempted' and result['partition_artifacts']['source']=='sha256:records'
    assert saved[0][1]['provenance']['provider_url']=='https://provider'


def test_preparation_submission_retries_return_same_durable_run(monkeypatch):
    from backend.oslc_service import preparation
    from backend.data_pipeline_service import run_records
    import backend.mesh_store as mesh
    class Receipts(InMemoryRegistry):
        @contextmanager
        def advisory_lock(self,key):yield True
    receipts=Receipts();runs={};calls=[]
    monkeypatch.setattr(mesh,'PostgresRegistry',lambda *a:receipts)
    monkeypatch.setattr(preparation.OSLCSyncStore,'get',lambda *a:{'complete':True,'content_sha256':'digest','sync_id':'snapshot'})
    monkeypatch.setattr(run_records,'get',lambda key:runs.get(key))
    def enqueue(definition,payload,**kw):
        calls.append(payload);record={'run_id':kw['run_id'],'status':'queued'};runs[record['run_id']]=record;return record
    monkeypatch.setattr(run_records,'enqueue',enqueue)
    definition={'job_id':'prepare-oslc','version':'1.0.0'};payload={'snapshot_id':'snapshot','idempotency_key':'same-click'}
    first=preparation.submit(definition,payload,'reader','c');second=preparation.submit(definition,payload,'reader','c')
    assert first['run']['run_id']==second['run']['run_id'] and len(calls)==1


def test_worker_rechecks_snapshot_grant_before_retaining_records(monkeypatch):
    from fastapi import HTTPException
    from backend.oslc_service import preparation
    monkeypatch.setattr(preparation.OSLCSyncStore,'get',lambda *a:{'sync_id':'s','complete':True,'status':'staged',
        'content_sha256':'d','provider_url':'https://provider','requested_by':'reader','resources':[]})
    def denied(*args):raise HTTPException(403,'Grant revoked')
    monkeypatch.setattr(preparation,'authorize',denied)
    with pytest.raises(HTTPException) as error:preparation.execute(None,{'snapshot_id':'s','execution_actor':'reader'},correlation_id='c')
    assert error.value.status_code==403
