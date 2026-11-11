import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import Mock,AsyncMock
import pytest
from backend.mesh_store import InMemoryRegistry
from backend.artifact_store import ArtifactStore
from backend.data_pipeline_service import speed_path as speed

@pytest.fixture
def setup(monkeypatch,tmp_path):
 sources=InMemoryRegistry();events=InMemoryRegistry();reviews=InMemoryRegistry()
 sources.create('plm-events',{'allowed_standards':['ap242'],'lifecycle_state':'approved','enabled':True,'max_lateness_seconds':300,'retraction_policy':'review'})
 monkeypatch.setattr(speed,'sources',sources);monkeypatch.setattr(speed,'events',events);monkeypatch.setattr(speed,'reconciliations',reviews)
 store=ArtifactStore(tmp_path);monkeypatch.setattr(speed,'ArtifactStore',lambda:store)
 monkeypatch.setattr(speed,'contract',SimpleNamespace(version='fixture',mapping_pack=lambda _:{'digest':'mapping'},normalize_entity=lambda **kw:kw['record'],normalize_relationship=lambda **kw:kw['record'],validate_projection=lambda **kw:{'conforms':True}))
 return events,reviews

def envelope(identity='event-one',part='A'):
 return {'event_id':identity,'source_id':'plm-events','standard':'ap242','occurred_at':'2026-11-01T00:00:00+00:00','records':{'entities':[{'id':part}],'relationships':[]}}

def test_atomic_conflicting_event_ids_preserve_one_intent(setup,monkeypatch):
 events,_=setup;barrier=threading.Barrier(2);original=events.get;count=0;lock=threading.Lock()
 def simultaneous(key):
  nonlocal count
  result=original(key)
  with lock:count+=1;number=count
  if number<=2:barrier.wait(timeout=3)
  return result
 monkeypatch.setattr(events,'get',simultaneous)
 def capture(part):
  try:return speed.capture_event(envelope(part=part),'reviewer')
  except speed.SpeedConflict:return 'conflict'
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(capture,['A','B']))
 assert results.count('conflict')==1 and len(events.values)==1
 winner=next(row for row in results if isinstance(row,dict));assert events.values['event-one']['payload_digest']==winner['payload_digest']

def test_same_event_retries_return_same_capture(setup):
 first=speed.capture_event(envelope(),'reviewer');again=speed.capture_event(envelope(),'reviewer')
 assert first['artifact_id']==again['artifact_id'] and again['idempotent'] is True

def test_partial_event_transition_resumes_same_retained_review(setup,monkeypatch):
 events,reviews=setup
 for key in ['event-a','event-b']:speed.capture_event(envelope(key,key),'reviewer')
 original=reviews.transition_bundle;calls=0
 def failing(*args,**kwargs):
  nonlocal calls
  calls+=1
  if calls==1:raise RuntimeError('Injected transaction failure before commit')
  return original(*args,**kwargs)
 monkeypatch.setattr(reviews,'transition_bundle',failing)
 with pytest.raises(RuntimeError):speed.reconcile(['event-a','event-b'],'reviewer')
 assert len(reviews.values)==1 and next(iter(reviews.values.values()))['status']=='reconciling'
 assert all(row['status'] in {'accepted','late'} for row in events.values.values())
 result=speed.reconcile(['event-b','event-a'],'reviewer')
 assert result['status']=='ready_for_approved_publication' and len(reviews.values)==1
 assert all(row['status']=='reconciled' and row['reconciliation_id']==result['reconciliation_id'] for row in events.values.values())
 assert speed.reconcile(['event-a','event-b'],'reviewer')==result

def test_duplicates_are_one_event_and_competing_batches_conflict(setup):
 speed.capture_event(envelope(),'reviewer');first=speed.reconcile(['event-one','event-one'],'reviewer')
 assert first['counts']['events']==1
 with pytest.raises(speed.SpeedConflict):speed.reconcile(['event-one'],'another-reviewer')

def test_listing_applies_bound_in_registry_query(monkeypatch):
 store=Mock();store.page.return_value=(100000,[{'event_id':'selected'}]);monkeypatch.setattr(speed,'events',store)
 assert speed.list_events(1,10)==[{'event_id':'selected'}]
 store.page.assert_called_once_with(limit=1,offset=10,order_field='captured_at');store.all.assert_not_called()

def test_context_excludes_source_rows_and_never_claims_business_approval(setup):
 speed.capture_event(envelope(),'reviewer');record=speed.reconcile(['event-one'],'reviewer');context=speed.review_context(record['reconciliation_id'])
 assert context['advisory_only'] is True and context['business_correctness_established'] is False
 assert context['semantic_conforms'] is True and context['publication_verified'] is False
 assert 'records' not in context and 'validation' not in context

@pytest.mark.asyncio
async def test_companion_uses_current_owner_evidence_and_scope_not_memory(monkeypatch):
 from backend.agentic_service import selected_record
 from backend.agentic_service.companion import KnowledgeCompanion
 from backend.agentic_service.context_scope import same_companion_scope
 read=AsyncMock(return_value=({'reconciliation_id':'retained-one','status':'reconciling','advisory_only':True,'semantic_conforms':None},'fixture'))
 monkeypatch.setattr(selected_record,'_read_json',read)
 answer=await KnowledgeCompanion().ask('Is this ready?',reconciliation_id='retained-one',headers={})
 assert answer['answerable'] and 'reconciling' in answer['response'] and 'separate authorized workflow' in answer['response']
 assert answer['generation']['enabled'] is False
 assert not same_companion_scope({'reconciliation_id':'one'},{'reconciliation_id':'two'})
 read.return_value=({'reconciliation_id':'different','advisory_only':True},'fixture')
 answer=await KnowledgeCompanion().ask('Is this ready?',reconciliation_id='retained-one',headers={})
 assert not answer['answerable'] and not answer['evidence']


def test_authorization_is_not_retained_in_event_evidence_or_idempotency(setup):
 first=speed.capture_event({**envelope(),'approval_token':'private-one','approved_by':'caller'},'reviewer')
 again=speed.capture_event({**envelope(),'approval_token':'private-two'},'reviewer')
 assert first['artifact_id']==again['artifact_id'] and again['idempotent']
 _,path=speed.ArtifactStore().resolve(first['artifact_id'])
 assert 'private-' not in path.read_text() and 'approval_token' not in path.read_text()

def test_published_receipt_cannot_be_replaced_by_a_stale_transition(setup):
 events,reviews=setup
 reviews.create('receipt',{'status':'published'})
 assert not reviews.transition_bundle('receipt',{'status':'ready'},related_store=events,expected_rows={},updated_rows={},expected_value={'status':'reconciling'})
 assert reviews.get('receipt')['status']=='published'


def test_reconciliation_inspection_requires_read_access(setup,monkeypatch):
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from backend.data_pipeline_service.speed_router import router
 monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment');monkeypatch.setenv('GRAPH_READ_TOKEN','fixture-read')
 speed.capture_event(envelope(),'reviewer');record=speed.reconcile(['event-one'],'reviewer')
 app=FastAPI();app.include_router(router)
 with TestClient(app) as client:
  route='/pipeline/speed/reconciliations/'+record['reconciliation_id']
  assert client.get(route).status_code==403
  result=client.get(route,headers={'Authorization':'Bearer fixture-read'})
  assert result.status_code==200 and result.json()['advisory_only'] is True


def test_legacy_authorized_envelope_retries_survive_upgrade_without_rewriting_artifact(setup):
 import hashlib
 events,_=setup;original={**envelope(),'approval_token':'old-private','approved_by':'legacy-reviewer'}
 content=json.dumps(original,sort_keys=True,separators=(',',':')).encode()
 artifact=speed.ArtifactStore().ingest_bytes(content,filename='legacy.json',kind='speed-event-envelope')
 old={'event_id':'event-one','payload_digest':speed._digest(original),'artifact_id':artifact['artifact_id'],'status':'accepted'}
 events.create('event-one',old)
 result=speed.capture_event(envelope(),'reviewer')
 assert result['idempotent'] and events.get('event-one')==old
 assert hashlib.sha256(speed.ArtifactStore().resolve(artifact['artifact_id'])[1].read_bytes()).hexdigest()==artifact['artifact_id'].split(':')[1]


def test_agent_scope_and_tool_read_identity_stay_bound_to_the_selected_review():
 from backend.agentic_service.goal_runner import selected_scope,verify_read_identity
 from backend.agentic_service.catalog_loader import load_catalog
 from backend.agentic_service.dt_bindings import extend_catalog
 assert selected_scope({'reconciliation_id':'one','password':'not-context'})=={'reconciliation_id':'one'}
 with pytest.raises(ValueError):verify_read_identity('pipeline.reconciliation.evidence',{'reconciliation_id':'one'},{'reconciliation_id':'other'})
 catalog=load_catalog();agent=next(a for a in catalog['agents'] if a['id']=='graph-analyst')
 assert 'pipeline.reconciliation.evidence' in agent['tools']
 assert next(t for t in catalog['tools'] if t['id']=='pipeline.reconciliation.evidence')['mutates'] is False
 assert extend_catalog(catalog)==catalog


def test_mixed_standard_selection_does_not_create_a_pending_review(setup):
    events,reviews=setup
    for key,standard in [('event-a','ap242'),('event-b','qif')]:
        events.create(key,{'event_id':key,'standard':standard,'status':'accepted',
                           'payload_digest':key,'reconciliation_id':None})
    with pytest.raises(ValueError,match='one source standard'):
        speed.reconcile(['event-a','event-b'],'reviewer')
    assert reviews.values == {}
    assert all(row['status']=='accepted' for row in events.values.values())
