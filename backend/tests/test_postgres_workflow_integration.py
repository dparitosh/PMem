"""Opt-in live localhost PostgreSQL tests in a disposable uniquely named test table.

Set DEPO_RUN_ISOLATED_POSTGRES_TESTS=1 to run. External workflow tools are
mocked; application registry SQL and workflow state persistence are real.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import re
import threading
import time
from uuid import uuid4

import pytest

from backend.mesh_store import PostgresRegistry
from backend.depo_platform.postgres_pool import close_idle, _DeadlineConnection
from backend.depo_platform.operations import operation_scope
from backend.tests.test_orchestration_recovery_api import recovery_api


@pytest.fixture(scope='module')
def isolated_postgres():
    if os.getenv('DEPO_RUN_ISOLATED_POSTGRES_TESTS') != '1':
        pytest.skip('Live localhost PostgreSQL integration requires explicit opt-in')
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    from dotenv import dotenv_values
    settings={}
    root=Path(__file__).resolve().parents[2]
    for name in ('.env','.env.local'):
        if (root/name).is_file():settings.update(dotenv_values(root/name))
    settings.update(os.environ)
    dsn=settings.get('DEPO_DATABASE_URL') or settings.get('DATABASE_URL')
    if not dsn:pytest.fail('No configured PostgreSQL connection; credentials are never printed')
    if conninfo_to_dict(dsn).get('host','localhost') not in {'localhost','127.0.0.1','::1'}:
        pytest.fail('This integration suite only permits localhost PostgreSQL')
    from backend.depo_platform.postgres_schema import configured_schema
    schema=settings.get('DEPO_DATABASE_SCHEMA','semantic')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}',schema):pytest.fail('Invalid configured schema')
    table='timing_audit_'+uuid4().hex
    assert re.fullmatch(r'timing_audit_[0-9a-f]{32}',table)
    qualified=sql.Identifier(schema,table)
    changes=pytest.MonkeyPatch()
    created=False
    original_connect=PostgresRegistry._connect
    class Cursor:
        def __init__(self,cursor):self.raw=cursor
        def __getattr__(self,name):return getattr(self.raw,name)
        def __enter__(self):self.raw.__enter__();return self
        def __exit__(self,*args):return self.raw.__exit__(*args)
        def execute(self,query,*args,**kwargs):
            self.raw.execute(re.sub(r'\bdepo_registry\b',target,query),*args,**kwargs);return self
        def executemany(self,query,*args,**kwargs):
            self.raw.executemany(re.sub(r'\bdepo_registry\b',target,query),*args,**kwargs);return self
    class Connection:
        def __init__(self,connection):self.raw=connection
        def __getattr__(self,name):return getattr(self.raw,name)
        def cursor(self,*args,**kwargs):return Cursor(self.raw.cursor(*args,**kwargs))
        def execute(self,query,*args,**kwargs):return self.cursor().execute(query,*args,**kwargs)
    @contextmanager
    def private_connect(registry):
        with original_connect(registry) as db:yield Connection(db)
    try:
        with psycopg.connect(dsn,connect_timeout=3,autocommit=True) as setup:
            target=qualified.as_string(setup)
            setup.execute("SET statement_timeout='3000ms'")
            setup.execute(sql.SQL("""CREATE TABLE {} (
              namespace text NOT NULL, key text NOT NULL, value jsonb NOT NULL,
              updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(namespace,key),
              CONSTRAINT test_related_failure CHECK(namespace <> 'reject_related'))""").format(qualified))
            created=True
        changes.setenv('DEPO_DATABASE_URL',dsn)
        changes.setenv('DEPO_DATABASE_SCHEMA',schema)
        changes.setenv('DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS','1')
        changes.setattr(PostgresRegistry,'_connect',private_connect)
        yield {'dsn':dsn,'schema':schema,'table':table}
    finally:
        close_idle()
        changes.undo()
        if created:
            # No CASCADE: remove only this fresh test table, never application data.
            with psycopg.connect(dsn,connect_timeout=3,autocommit=True) as cleanup:
                cleanup.execute("SET lock_timeout='3000ms'")
                cleanup.execute(sql.SQL('DROP TABLE {}').format(qualified))
                assert not cleanup.execute('SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname=%s AND tablename=%s)',(schema,table)).fetchone()[0]


def test_related_write_failure_rolls_back_both_rows(isolated_postgres):
    import psycopg
    store=PostgresRegistry('test_atomic')
    with pytest.raises(psycopg.errors.CheckViolation):
        store.put_with_related('record',{'state':'prepared'},related_namespace='reject_related',related_key='approval',related_value={'approved':True})
    assert store.get('record') is None
    assert PostgresRegistry('reject_related').get('approval') is None


def test_two_workflow_claimants_have_exactly_one_cas_winner(isolated_postgres):
    store=PostgresRegistry('test_cas');before={'status':'queued'};store.put('run',before)
    barrier=threading.Barrier(2,timeout=3)
    def claim(worker):
        barrier.wait()
        return store.compare_and_put('run',before,{'status':'running','worker':worker})
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(claim,['a','b']))
    assert sorted(results)==[False,True]
    assert store.get('run')['worker'] in {'a','b'}


def test_atomic_queue_claim_and_stale_worker_fence(isolated_postgres):
    store=PostgresRegistry('data_job_runs')
    store.put('claim-run',{'run_id':'claim-run','status':'queued','attempt':0})
    barrier=threading.Barrier(2,timeout=3)
    def claim(worker):barrier.wait();return store.claim_next(worker_id=worker,lease_seconds=30)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(claim,['a','b']))
    claimed=[record for record in results if record]
    assert len(claimed)==1 and claimed[0]['attempt']==1
    old=claimed[0]
    store.put('claim-run',{**old,'lease':{**old['lease'],'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}})
    replacement=store.claim_next(worker_id='replacement',lease_seconds=30)
    assert replacement['attempt']==2
    with pytest.raises(ValueError,match='no longer owns'):
        store.transition_owned('claim-run',old,{**old,'status':'completed'})
    assert store.heartbeat(key='claim-run',worker_id=old['worker_id'],attempt=old['attempt'],lease=old['lease']) is None
    assert store.get('claim-run')['worker_id']=='replacement'


def test_row_lock_wait_times_out_without_replaying_write(isolated_postgres):
    import psycopg
    store=PostgresRegistry('test_contention');before={'status':'queued'};store.put('locked',before)
    with store._connect() as owner,owner.transaction(),owner.cursor() as cursor:
        cursor.execute('SELECT key FROM depo_registry WHERE namespace=%s AND key=%s FOR UPDATE',(store.namespace,'locked'))
        started=time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as workers:
            future=workers.submit(store.compare_and_put,'locked',before,{'status':'running'})
            with pytest.raises((psycopg.errors.LockNotAvailable,psycopg.errors.QueryCanceled)):
                future.result(timeout=5)
        assert time.monotonic()-started<5
    assert store.get('locked')==before


def test_expiry_before_commit_rolls_back_real_postgres_write(isolated_postgres):
    class Budget:
        expired=False
        def timeout(self,requested):
            if self.expired:raise TimeoutError('controlled deadline elapsed')
            return min(requested,3)
    store=PostgresRegistry('test_deadline');budget=Budget()
    with store._connect() as raw:
        with operation_scope(budget),pytest.raises(TimeoutError):
            with _DeadlineConnection(raw).transaction():
                raw.execute('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s::jsonb)',(store.namespace,'expired','{}'))
                budget.expired=True
    assert store.get('expired') is None


@pytest.fixture
def persisted_workflow(isolated_postgres,monkeypatch,recovery_api):
    from backend.agentic_service import router as routes
    client,prior,dispatch,data=recovery_api
    record=prior.get('run-fixture');run_id='timing-'+uuid4().hex
    record={**record,'run_id':run_id}
    store=PostgresRegistry('test_workflows');store.put(run_id,record)
    monkeypatch.setattr(routes,'workflow_store',store)
    monkeypatch.setattr(routes,'workflow_controls',PostgresRegistry('test_workflow_controls'))
    monkeypatch.setattr(routes,'workflow_heartbeats',PostgresRegistry('test_workflow_heartbeats'))
    return client,store,dispatch,run_id


def test_workflow_recovery_persists_and_does_not_repeat_completed_step(persisted_workflow):
    client,store,dispatch,run_id=persisted_workflow
    url=f'/api/v1/workflow-runs/{run_id}/recover';headers={'Authorization':'Bearer fixture-read'}
    assert client.post(url,json={},headers=headers).status_code==403
    assert store.get(run_id)['status']=='failed'
    approval={'approved_by':'supervisor','approval_token':'fixture-supervisor'}
    response=client.post(url,json=approval,headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    assert dispatch.await_count==1 and dispatch.call_args.args[0]['tool_id']=='second'
    stored=store.get(run_id)
    assert stored['status']=='completed' and stored['traces'][0]['result']=={'answer':'retained'}
    assert stored['recovery_history']
    assert client.post(url,json=approval,headers=headers).status_code==409
    assert dispatch.await_count==1


def test_expired_workflow_does_not_dispatch_tools(persisted_workflow):
    client,store,dispatch,run_id=persisted_workflow
    store.put(run_id,{**store.get(run_id),'deadline_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()})
    response=client.post(f'/api/v1/workflow-runs/{run_id}/recover',json={'approved_by':'supervisor','approval_token':'fixture-supervisor'},headers={'Authorization':'Bearer fixture-read'})
    assert response.status_code==409
    dispatch.assert_not_awaited()

def test_live_inline_execution_is_never_reclaimed_by_queue_worker(isolated_postgres):
    store=PostgresRegistry('data_job_runs')
    # Remove no prior fixture records: other runs are terminalized through their
    # current owned transition, leaving this inline run as the only candidate.
    previous=store.get('claim-run')
    if previous and previous.get('status')=='running':
        store.transition_owned('claim-run',previous,{**previous,'status':'completed'})
    inline={'run_id':'inline-active','status':'running','started_at':datetime.now(timezone.utc).isoformat()}
    store.put('inline-active',inline)
    assert store.claim_next(worker_id='another-worker',lease_seconds=30) is None
    assert store.get('inline-active')==inline

def test_late_failure_preserves_real_committed_receipt(isolated_postgres,monkeypatch):
    from backend.data_pipeline_service import run_records
    store=PostgresRegistry('test_terminal');monkeypatch.setattr(run_records,'store',store)
    original={'run_id':'retained-terminal','status':'running'}
    completed={**original,'status':'completed','output_manifest':{'result_digest':'retained-receipt'}}
    store.put(original['run_id'],completed)
    assert run_records.failed(original,'Lost commit acknowledgement')==completed
    assert store.get(original['run_id'])==completed
