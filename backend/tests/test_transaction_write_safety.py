"""Regressions for deadline selection, inline ownership and terminal writes."""
from datetime import datetime,timezone
import pytest
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import run_records
from backend.depo_platform import qos

@pytest.mark.parametrize('path',[
 '/api/v1/pipeline/jobs/runs/run-1/replay',
 '/api/v1/pipeline/jobs/transform',
 '/api/v1/pipeline/jobs/definitions/job/1.0.0/run',
])
def test_pipeline_execution_uses_pipeline_budget(path,monkeypatch):
    monkeypatch.setenv('DEPO_PIPELINE_JOB_TIMEOUT_SECONDS','1200')
    monkeypatch.setenv('AGENTIC_RUN_TIMEOUT_SECONDS','30')
    assert qos.request_budget(path)==1230

def test_read_and_agent_budgets_are_not_widened(monkeypatch):
    monkeypatch.setenv('DEPO_REQUEST_TIMEOUT_SECONDS','90')
    monkeypatch.setenv('AGENTIC_RUN_TIMEOUT_SECONDS','30')
    assert qos.request_budget('/api/v1/pipeline/jobs/definitions')==90
    assert qos.request_budget('/api/v1/workflow-runs/run-1')==60

def test_late_inline_failure_cannot_replace_retained_completion(monkeypatch):
    store=InMemoryRegistry();monkeypatch.setattr(run_records,'store',store)
    original={'run_id':'run','status':'running'}
    completed={**original,'status':'completed','output_manifest':{'result_digest':'verified'}}
    store.put('run',completed)
    result=run_records.failed(original,'Commit acknowledgement lost')
    assert result==completed and store.get('run')==completed

def test_concurrent_completion_wins_over_failure_compare_and_put(monkeypatch):
    original={'run_id':'run','status':'running'}
    completed={**original,'status':'completed','output_manifest':{'result_digest':'verified'}}
    class RacingStore(InMemoryRegistry):
        def compare_and_put(self,key,expected,value):
            self.put(key,completed)
            return super().compare_and_put(key,expected,value)
    store=RacingStore();store.put('run',original);monkeypatch.setattr(run_records,'store',store)
    assert run_records.failed(original,'Late error')==completed
    assert store.get('run')==completed

def test_worker_never_claims_live_inline_execution_without_lease(monkeypatch):
    store=InMemoryRegistry();monkeypatch.setattr(run_records,'store',store)
    inline={'run_id':'inline','status':'running','started_at':datetime.now(timezone.utc).isoformat()}
    store.put('inline',inline)
    assert run_records.claim_next(worker_id='worker',lease_seconds=30) is None
    assert store.get('inline')==inline
