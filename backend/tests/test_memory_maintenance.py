import copy
from types import SimpleNamespace
import pytest
from backend.agentic_service.memory_maintenance import run_steps, prune_graph


class Store:
    def __init__(self, fail=False): self.records=[]; self.fail=fail
    def put(self, key, value):
        if self.fail: raise RuntimeError('receipt unavailable')
        self.records.append(copy.deepcopy(value))


@pytest.mark.asyncio
async def test_partial_failure_retains_per_store_results_without_private_errors():
    store=Store()
    def fail(): raise RuntimeError('private credential')
    result=await run_steps(store, [('postgres',lambda:2,()),('graph',fail,())])
    assert result['status']=='partial'
    assert result['steps'][0]['affected_records']==2
    assert result['steps'][1]['error_type']=='RuntimeError'
    assert 'private credential' not in str(store.records)
    assert store.records[1]['steps'][0]['status']=='running'


@pytest.mark.asyncio
async def test_receipt_failure_prevents_cleanup():
    touched=[]
    with pytest.raises(RuntimeError):
        await run_steps(Store(fail=True), [('delete',lambda:touched.append(True),())])
    assert not touched


def test_graph_disabled_and_unavailable_are_not_successful_zero_deletions():
    assert prune_graph(SimpleNamespace(enabled=lambda:False))['status']=='disabled'
    assert prune_graph(SimpleNamespace(enabled=lambda:True,prune_expired_sessions=lambda:None))['status']=='unavailable'
    assert prune_graph(SimpleNamespace(enabled=lambda:True,prune_expired_sessions=lambda:0))==0
