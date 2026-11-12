"""Real isolated PostgreSQL: resource changes and checkpoint rollback are inseparable."""
import json,os,uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import psycopg
from psycopg import sql
import pytest
from backend.mesh_store import PostgresRegistry
from backend.data_pipeline_service import reporting_store as store,reporting_trs as consumer,reporting_export


@pytest.fixture
def reporting_db(monkeypatch):
    dsn=os.getenv('DEPO_TEST_DATABASE_URL')
    if not dsn:pytest.skip('An isolated DEPO_TEST_DATABASE_URL is required')
    schema='reporting_acceptance_'+uuid.uuid4().hex[:12]
    with psycopg.connect(dsn,autocommit=True) as control:
        assert control.info.dbname=='depo_acceptance_test','Use the isolated acceptance database only'
        control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            control.execute(Path('infra/postgres/migrations/018_trs_reporting_replica.sql').read_text(encoding='utf-8'))
            class Registry(PostgresRegistry):
                @contextmanager
                def _connect(self,**kwargs):
                    with psycopg.connect(dsn,autocommit=True) as db:
                        db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)));yield db
                _session_connect=_connect
            registry=Registry('reporting_test');monkeypatch.setattr(store,'registry',lambda:registry)
            yield registry
        finally:
            control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def record(uri,name,value=1):
    return {'title':name,'rdf:type':['urn:class:Part'],'properties':{'ontology_id':'v1','uri':uri,'mass':value},'outgoingLinks':[]}


class Provider:
    one='http://provider/oslc/resources/one?ontology_id=v1';two='http://provider/oslc/resources/two?ontology_id=v1'
    def __init__(self):self.data={self.one:record('urn:part:one','Part one'),self.two:record('urn:part:two','Part two')};self.events=[];self.head=0;self.gap=False
    def base(self,cursor=None):return {'members':[{'resource_uri':uri} for uri in self.data], 'cutoff_order':self.head,'nextPage':None}
    def resource(self,uri,definition):return store.normalise(uri,self.data[uri],definition) if uri in self.data else None
    def changes(self,after):return {'events':[event for event in self.events if event['order']>after],'head_order':self.head,'rebase_required':self.gap}
    def event(self,uri,kind):self.head+=1;self.events.append({'order':self.head,'resource_uri':uri,'event_type':kind})


def approved_feed():
    identifier=store.create('Engineering reporting',{'ontology_ids':['v1']},'author');store.approve(identifier,'reviewer');return identifier


def test_initial_load_is_hidden_until_complete_and_resumes(reporting_db):
    identifier=approved_feed();provider=Provider()
    consumer.synchronize({'feed_id':identifier,'max_steps':2},provider)
    before=store.report(identifier)
    assert before['total_resources']==0 and before['feed']['state']['phase']=='base'
    result=consumer.synchronize({'feed_id':identifier},provider)
    report=store.report(identifier)
    assert report['total_resources']==2 and result['freshness']=='tracked_feed_caught_up'
    assert report['read_from_source_graph'] is False


def test_updates_deletes_and_replay_keep_replica_current(reporting_db):
    identifier=approved_feed();provider=Provider()
    provider.data[provider.one]['outgoingLinks']=[{'predicate':'urn:contains','targetUri':provider.two}]
    consumer.synchronize({'feed_id':identifier},provider)
    assert store.report(identifier)['recorded_links']==1
    provider.data[provider.one]['title']='Revised part';provider.data[provider.one]['properties']['mass']=12
    provider.event(provider.one,'Modification');consumer.synchronize({'feed_id':identifier},provider)
    first=store.report(identifier)
    assert any(row['name']=='Revised part' for row in first['resources'])
    assert first['feed']['state']['trs_after']==1
    consumer.synchronize({'feed_id':identifier},provider)
    assert store.report(identifier)['total_resources']==2
    del provider.data[provider.two];provider.event(provider.two,'Deletion');consumer.synchronize({'feed_id':identifier},provider)
    after=store.report(identifier)
    assert after['total_resources']==1 and after['recorded_links']==0 and after['feed']['state']['trs_after']==2


def test_failed_transaction_changes_neither_rows_nor_checkpoint(reporting_db,monkeypatch):
    identifier=approved_feed();provider=Provider();consumer.synchronize({'feed_id':identifier},provider)
    expected=store.get(identifier)['state'];updated={**expected,'trs_after':99}
    replacement=store.normalise(provider.one,record('urn:part:one','Should roll back'),store.get(identifier)['definition'])
    calls=[]
    def fence():
        calls.append(1)
        if len(calls)>1:raise RuntimeError('Lease lost before checkpoint commit')
    monkeypatch.setattr(store,'ensure_execution_allowed',fence)
    with pytest.raises(RuntimeError,match='Lease lost'):store.commit(identifier,expected,updated,[(provider.one,replacement)])
    assert store.get(identifier)['state']==expected
    assert all(row['name']!='Should roll back' for row in store.report(identifier)['resources'])


def test_retention_gap_rebases_without_hiding_last_complete_generation(reporting_db):
    identifier=approved_feed();provider=Provider();consumer.synchronize({'feed_id':identifier},provider)
    old=store.get(identifier)['state']['active_generation'];provider.gap=True;provider.head=50
    consumer.synchronize({'feed_id':identifier,'max_steps':1},provider)
    pending=store.report(identifier)
    assert pending['total_resources']==2 and pending['feed']['state']['active_generation']==old
    assert pending['feed']['state']['phase']=='base'
    provider.gap=False;provider.data.pop(provider.two)
    consumer.synchronize({'feed_id':identifier},provider)
    current=store.report(identifier)
    assert current['total_resources']==1 and current['feed']['state']['active_generation']!=old
    assert current['feed']['state']['trs_after']==50


def test_unapproved_selection_cannot_replicate(reporting_db):
    identifier=store.create('Not approved',{'ontology_ids':['v1']},'author')
    with pytest.raises(ValueError,match='Approve'):consumer.synchronize({'feed_id':identifier},Provider())


def test_reporting_export_is_retained_and_not_published(reporting_db,monkeypatch):
    identifier=approved_feed();consumer.synchronize({'feed_id':identifier},Provider());parts=[]
    monkeypatch.setattr(reporting_export,'ArtifactStore',lambda:SimpleNamespace(ingest_bytes=lambda data,**kw:(parts.append(data) or {'artifact_id':'sha256:part'})))
    result=reporting_export.execute(None,{'feed_id':identifier},correlation_id='export-test')
    assert result['reporting_snapshot']['record_count']==2
    assert len([json.loads(row) for part in parts for row in part.splitlines()])==2
    assert result['data_product_draft']['quality_status']=='requires_review'
    assert result['data_product_draft']['publication_requirements']
