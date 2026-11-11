"""Controlled scheduler state changes at the handoff boundary; no service I/O."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.data_pipeline_service import scheduler

@pytest.mark.parametrize('change',['disable','clear_schedule','delete'])
def test_scan_revalidates_definition_after_acquiring_job_lock(monkeypatch,change):
    snapshot={'job_id':'review','version':'1.0.0','lifecycle_state':'approved','enabled':True,
              'schedule':{'replay_run_id':'input-run','interval_seconds':60}}
    current=dict(snapshot)
    @contextmanager
    def lock(key):
        if change=='disable':current.update(lifecycle_state='disabled',enabled=False)
        elif change=='clear_schedule':current['schedule']=None
        else:current.clear()
        yield True
    monkeypatch.setattr(scheduler.job_definitions,'all_definitions',lambda:[snapshot])
    monkeypatch.setattr(scheduler.job_definitions,'get',lambda *args:current or None)
    monkeypatch.setattr(scheduler.job_definitions,'store',SimpleNamespace(advisory_lock=lock))
    monkeypatch.setattr(scheduler.run_records,'store',SimpleNamespace(latest_job_run=lambda *args:None))
    monkeypatch.setattr(scheduler.run_records,'get',lambda *args:{'run_id':'input-run','job_id':'review','job_version':'1.0.0'})
    monkeypatch.setattr(scheduler.run_records,'replay_payload',lambda *args:{'replay_of':'input-run'})
    monkeypatch.setenv('DEPO_PIPELINE_EXECUTION_MODE','inline')
    execute=Mock();scheduler.ScheduledJobSupervisor(execute).scan_once()
    execute.assert_not_called()

def test_retry_rechecks_definition_after_backoff(monkeypatch):
    current={'job_id':'review','version':'1.0.0','lifecycle_state':'approved','enabled':True,
             'schedule':{'replay_run_id':'input-run','interval_seconds':60},
             'retry_policy':{'max_attempts':2,'backoff_seconds':1}}
    @contextmanager
    def lock(key):yield True
    monkeypatch.setattr(scheduler.job_definitions,'all_definitions',lambda:[dict(current)])
    monkeypatch.setattr(scheduler.job_definitions,'get',lambda *args:dict(current))
    monkeypatch.setattr(scheduler.job_definitions,'store',SimpleNamespace(advisory_lock=lock))
    monkeypatch.setattr(scheduler.run_records,'store',SimpleNamespace(latest_job_run=lambda *args:None))
    monkeypatch.setattr(scheduler.run_records,'get',lambda *args:{'run_id':'input-run','job_id':'review','job_version':'1.0.0'})
    monkeypatch.setattr(scheduler.run_records,'replay_payload',lambda *args:{'replay_of':'input-run'})
    monkeypatch.setenv('DEPO_PIPELINE_EXECUTION_MODE','inline')
    calls=[]
    def execute(*args):
        calls.append(args);current.update(lifecycle_state='disabled',enabled=False)
        raise RuntimeError('transient failure before disable')
    supervisor=scheduler.ScheduledJobSupervisor(execute)
    supervisor._stop=SimpleNamespace(is_set=lambda:False,wait=lambda seconds:False)
    supervisor.scan_once()
    assert len(calls)==1
