"""Opt-in real worker crash recovery; owns child processes and a disposable schema only."""
import os,sys,time,json,tempfile,subprocess,uuid
from pathlib import Path
from datetime import datetime,timezone
import pytest
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'), reason='Requires isolated depo_acceptance_test database')
def test_owned_worker_crash_recovers_one_projection():
 original_environment=os.environ.copy()
 try:
  root=Path(__file__).resolve().parents[2]
  dsn=os.environ['DEPO_TEST_DATABASE_URL']
  assert conninfo_to_dict(dsn)['dbname']=='depo_acceptance_test'
  schema='worker_acceptance_'+uuid.uuid4().hex[:12]
  with tempfile.TemporaryDirectory(prefix='pmem-worker-') as temporary,psycopg.connect(dsn,autocommit=True) as control:
   assert control.info.dbname=='depo_acceptance_test'
   control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
   child=None;blocker=None
   try:
    control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
    control.execute('CREATE TABLE depo_registry(namespace TEXT NOT NULL,key TEXT NOT NULL,value JSONB NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(namespace,key))')
    control.execute((root/'infra/postgres/migrations/015_semantic_datasets.sql').read_text(encoding='utf-8'))
    os.environ.update(DEPO_DATABASE_URL=dsn,DATABASE_URL=dsn,DEPO_DATABASE_SCHEMA=schema,ARTIFACT_STORAGE=temporary,OSLC_TRS_ENABLED='false',DEPO_PIPELINE_LEASE_SECONDS='30',DEPO_PIPELINE_POLL_SECONDS='1',DEPO_CREDENTIAL_STORE='environment')
    os.environ['DEPO_PIPELINE_WORKER_ID']='isolated-'+uuid.uuid4().hex
    from backend.artifact_store import ArtifactStore
    from backend.mesh_store import PostgresRegistry
    from backend.data_pipeline_service import job_definitions,run_records
    a=ArtifactStore().ingest_bytes(b'<urn:p> a <urn:Part>; <urn:mass> 4 .',filename='test.ttl')
    PostgresRegistry('catalog_products').put('local-test:1.0.0',{'name':'ISOLATED TEST','version':'1.0.0','artifacts':[{'artifact_id':a['artifact_id']}]})
    d=job_definitions.create({'job_id':'interruption-acceptance','name':'ISOLATED INTERRUPTION TEST','version':'1.0.0','job_type':'rdf-semantic-materialize','quality_profile':'semantic-core-v1','owner':'acceptance','enabled':True,'retry_policy':{'max_attempts':2,'backoff_seconds':1}})
    d=job_definitions.approve(d['job_id'],d['version'],'acceptance')
    r=run_records.enqueue(d,{'source_id':'catalog:local-test:1.0.0','artifact_id':a['artifact_id'],'execution_actor':'acceptance'},correlation_id='isolated-worker-crash')
    blocker=psycopg.connect(dsn);blocker.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)));blocker.execute('LOCK TABLE depo_semantic_datasets IN ACCESS EXCLUSIVE MODE')
    log_path=Path(temporary)/'worker.log'
    log=log_path.open('w',encoding='utf-8')
    def launch():return subprocess.Popen([sys.executable,'-m','backend.data_pipeline_service.worker'],cwd=root,env=os.environ.copy(),stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    child=launch()
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
     current=run_records.get(r['run_id'])
     waiting=control.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%%depo_semantic_datasets%%'").fetchone()[0]
     if current['status']=='running' and waiting:break
     if child.poll() is not None:raise RuntimeError('Child worker exited; inspect retained test log')
     time.sleep(.2)
    else:raise RuntimeError('Could not observe worker blocked before persistence')
    assert current['worker_id']==os.environ['DEPO_PIPELINE_WORKER_ID']
    child.kill();child.wait(timeout=10);child=None
    blocker.rollback();blocker.close();blocker=None
    assert control.execute('SELECT count(*) FROM depo_semantic_datasets').fetchone()[0]==0
    print('PASS: killed owned child worker while blocked before persistence; zero partial datasets',flush=True)
    remaining=(datetime.fromisoformat(current['lease']['expires_at'])-datetime.now(timezone.utc)).total_seconds()
    if remaining>0:time.sleep(min(remaining+.3,31))
    child=launch();deadline=time.monotonic()+45
    while time.monotonic()<deadline:
     current=run_records.get(r['run_id'])
     if current['status'] in ['completed','failed','validation_failed']:break
     time.sleep(.3)
    assert current['status']=='completed',current.get('last_error')
    assert current['attempt']==2
    assert control.execute('SELECT count(*) FROM depo_semantic_datasets').fetchone()[0]==1
    assert current['output_manifest']['counts']['entities']==1
    result={'status':'passed','run_id':r['run_id'],'attempt':2,'partial_datasets_after_crash':0,'datasets_after_recovery':1,'database':'depo_acceptance_test','schema_removed':False}
    print('PASS: replacement worker reclaimed expired lease; attempt 2 completed exactly one dataset',flush=True)
   finally:
    if blocker:blocker.rollback();blocker.close()
    if child and child.poll() is None:child.kill();child.wait(timeout=10)
    if 'log' in locals():log.close()
    control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    assert not control.execute('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s)',(schema,)).fetchone()[0]
   print('PASS: isolated worker recovery and schema cleanup')
 finally:
  os.environ.clear();os.environ.update(original_environment)
