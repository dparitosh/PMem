"""Offline execution, admission and delivery regressions for remaining QoS gaps."""
import ast
import asyncio
from concurrent.futures import Future
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest
from fastapi import HTTPException

from backend.depo_platform.operations import OperationContext, operation_scope
from backend.data_pipeline_service.runner import SparkJobRunner
from backend.data_pipeline_service import run_records
from backend.qif.task_service import QifTaskService


def deadline(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def test_pipeline_legacy_deadline_uses_original_start_and_never_retry_time(monkeypatch):
    monkeypatch.setenv('DEPO_PIPELINE_JOB_TIMEOUT_SECONDS', '90')
    record = {'started_at': '2000-01-01T00:00:00+00:00', 'attempt': 8}
    assert run_records.execution_deadline(record) == '2000-01-01T00:01:30+00:00'
    record['deadline_at'] = '2000-01-01T00:00:20+00:00'
    assert run_records.execution_deadline(record) == record['deadline_at']


def test_expired_lease_cannot_be_renewed_indefinitely():
    record = {'status': 'running', 'worker_id': 'worker', 'started_at': deadline(-5), 'deadline_at': deadline(-1)}
    with pytest.raises(TimeoutError):
        run_records.heartbeat(record, worker_id='worker')


@pytest.mark.parametrize('lose_lease', [False, True])
def test_spark_cancels_owned_group_without_waiting_for_work_lock(lose_lease):
    runner = SparkJobRunner()
    cancelled = threading.Event()
    groups = []
    context = SimpleNamespace(setJobGroup=lambda group, *a, **kw: groups.append(group),
                              cancelJobGroup=lambda group: (groups.append(group), cancelled.set()),
                              setLocalProperty=lambda *args: None)
    lost = threading.Event()
    with pytest.raises((TimeoutError, RuntimeError)):
        with runner.execution_scope(OperationContext('run', deadline(2 if lose_lease else .08)), lost):
            with runner._lock:
                runner._configure_group(SimpleNamespace(sparkContext=context))
                if lose_lease:
                    lost.set()
                assert cancelled.wait(1)
                if lose_lease:
                    raise RuntimeError('lease lost')
    assert len(groups) == 2 and groups[0] == groups[1]
    assert groups[0].startswith('run:')


def test_spark_waiting_for_busy_runner_consumes_request_budget():
    runner = SparkJobRunner()
    with runner._lock, operation_scope(OperationContext('waiting', deadline(.03))):
        with pytest.raises(TimeoutError):
            with runner._work():
                pytest.fail('Expired work acquired runner lock')


class ManualExecutor:
    def __init__(self):
        self.submitted = []
    def submit(self, work):
        future = Future()
        self.submitted.append((work, future))
        return future
    def shutdown(self, **kwargs):
        for _, future in self.submitted:
            future.cancel()


@pytest.fixture
def qif(tmp_path, monkeypatch):
    monkeypatch.setenv('QIF_MAX_PENDING_TASKS', '1')
    service = QifTaskService(tmp_path / 'tasks')
    service._executor.shutdown(wait=False)
    service._executor = ManualExecutor()
    yield service
    service.shutdown()


def task(service):
    return service.create(source_paths=[], ontology_name='Test', prefix='test', description='', source='test')['task_id']


def test_qif_queue_rejects_overload_and_cancelled_future_releases_capacity(qif):
    first, second = task(qif), task(qif)
    assert qif.submit_prepare(first)
    with pytest.raises(HTTPException) as error:
        qif.submit_prepare(second)
    assert error.value.status_code == 503
    assert error.value.headers['Retry-After'] == '5'
    assert qif.get(second)['status'] == 'queued'
    qif._executor.submitted[0][1].cancel()
    assert qif.submit_prepare(second)


def test_qif_expired_queued_task_never_executes_or_gets_new_deadline(qif):
    identity = task(qif)
    expired = deadline(-1)
    qif._update(identity, preparation_deadline_at=expired)
    called = []
    qif.prepare = lambda identity: called.append(identity)
    qif.submit_prepare(identity)
    qif._executor.submitted[0][1].set_running_or_notify_cancel()
    qif._executor.submitted[0][0]()
    assert not called
    assert qif.get(identity)['status'] == 'failed'
    assert qif.get(identity)['preparation_deadline_at'] == expired


def test_qif_shutdown_refuses_new_work_and_retains_existing_manifest(qif):
    identity = task(qif)
    qif.submit_prepare(identity)
    qif.shutdown()
    assert qif.get(identity)['status'] == 'queued'
    with pytest.raises(HTTPException) as error:
        qif.submit_prepare(identity)
    assert error.value.status_code == 503


def test_uncertain_qif_publication_is_verified_without_another_write(qif, monkeypatch):
    from backend.qif import task_service as module
    identity = task(qif)
    qif._update(identity, ontology_id='demo', graph_sync={'status':'unverified', 'attempts':1})
    calls = []
    def verify(**kwargs):
        calls.append('verify')
        return {'status':'success'}
    def write(**kwargs):
        pytest.fail('Uncertain publication was replayed')
    monkeypatch.setattr(module, 'get_publisher', lambda: SimpleNamespace(sync_graph=write, verify_graph=verify))
    qif._sync_graph(identity)
    assert calls == ['verify']
    assert qif.get(identity)['status'] == 'completed'


def test_qif_cannot_claim_to_cancel_a_dispatched_commit(qif):
    identity = task(qif)
    qif._update(identity, graph_sync={'status':'publishing'})
    with pytest.raises(HTTPException) as error:
        qif.cancel(identity)
    assert error.value.status_code == 409


def outbox_scope(records, register):
    """Exercise the real dispatcher with in-memory persistence and transport."""
    source = ast.parse(Path('backend/data_product_service/router.py').read_text(encoding='utf-8'))
    function = next(node for node in source.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'reconcile_pending')
    async def io(function, *args): return function(*args)
    @asynccontextmanager
    async def lock(key): yield True
    def put(key, expected, updated):
        if records[key] != expected: return False
        records[key] = updated
        return True
    namespace = {'asyncio':asyncio, 'datetime':datetime, 'timedelta':timedelta, 'timezone':timezone,
                 '_product_io':io, '_product_lock':lock, '_register_catalog':register,
                 'store':SimpleNamespace(due_pending=lambda limit:list(records.items())[:limit],
                                         get=records.get, compare_and_put=put)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<outbox>', 'exec'), namespace)
    return namespace['reconcile_pending']


def test_slow_catalog_record_does_not_block_independent_product(monkeypatch):
    monkeypatch.setenv('DATA_PRODUCT_OUTBOX_CONCURRENCY', '2')
    records = {'slow':{'id':'slow'}, 'fast':{'id':'fast'}}
    async def scenario():
        fast = asyncio.Event()
        async def register(record):
            if record['id'] == 'slow':
                await asyncio.wait_for(fast.wait(), .3)
            else:
                fast.set()
            return {**record, 'status':'published'}
        result = await outbox_scope(records, register)()
        assert result['published'] == 2
        assert result['deferred'] == 0
    asyncio.run(scenario())


def test_expired_outbox_batch_retains_unacknowledged_rows(monkeypatch):
    from backend.depo_platform import network
    original = network.bounded_timeout_seconds
    monkeypatch.setattr(network, 'bounded_timeout_seconds', lambda name, **kw: .03 if name == 'DATA_PRODUCT_OUTBOX_BATCH_TIMEOUT_SECONDS' else original(name, **kw))
    records = {'slow':{'id':'slow'}, 'queued':{'id':'queued'}}
    async def register(record):
        await asyncio.sleep(5)
        return {**record, 'status':'published'}
    result = asyncio.run(outbox_scope(records, register)())
    assert result['deferred'] == 2
    assert all('status' not in record for record in records.values())


@pytest.mark.parametrize('limited', [False, True])
def test_real_peer_stream_respects_total_deadline_and_response_limit(monkeypatch, limited):
    import httpx
    from backend.depo_platform.peer_http import async_peer_response
    original = httpx.AsyncClient
    seen = []
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(20):
                await asyncio.sleep(.01)
                yield b'abcdefgh'
    async def handle(request):
        seen.append(request.headers.get('X-DEPO-Deadline'))
        return httpx.Response(200, stream=SlowStream())
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    async def scenario():
        with operation_scope(OperationContext('stream', deadline(.05))):
            with pytest.raises(ValueError if limited else TimeoutError):
                await async_peer_response('GET', 'http://peer/data', headers={}, budget=10, response_limit=4 if limited else 10000)
    asyncio.run(scenario())
    assert seen[0]


def test_active_schema_parser_process_is_terminated_at_deadline(monkeypatch):
    import sys
    from backend.qif import preparation_worker
    original = preparation_worker.subprocess.Popen
    children = []
    def sleeping_child(command, **kwargs):
        child = original([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(preparation_worker.subprocess, 'Popen', sleeping_child)
    with operation_scope(OperationContext('qif-expiry', deadline(.08))):
        with pytest.raises(TimeoutError):
            preparation_worker.run_stage('inspect', paths=[])
    assert len(children) == 1
    assert children[0].poll() is not None


def test_schema_worker_rejects_expired_budget_before_resolving_tools(tmp_path):
    import pickle
    import subprocess
    import sys
    import time
    result = tmp_path / 'result.pickle'
    child = subprocess.run([sys.executable, '-m', 'backend.qif.preparation_worker', str(result)],
        input=pickle.dumps(('inspect', {'paths': []}, time.time() - 1)), capture_output=True, timeout=5)
    assert child.returncode == 124
    assert not result.exists()


def test_cancellation_after_worker_admission_cannot_start_parser(qif, monkeypatch):
    from backend.depo_platform.execution_guard import guarded_execution
    from backend.qif import task_service as module
    identity = task(qif)
    def guard():
        if qif._cancelled(identity):
            raise RuntimeError('cancelled')
    monkeypatch.setattr(module, 'run_stage', lambda *a, **kw: pytest.fail('Cancelled parser dispatched'))
    with guarded_execution(guard):
        qif.cancel(identity)
        qif.prepare(identity)
    assert qif.get(identity)['status'] == 'cancelled'


def test_cancelled_manifest_rejects_stale_worker_snapshot(qif):
    identity = task(qif)
    stale = qif.get(identity)
    qif.cancel(identity)
    stale.update(status='awaiting_approval', stage='review')
    qif._write(identity, stale)
    assert qif.get(identity)['status'] == 'cancelled'


@pytest.mark.parametrize('initial', ['publishing', 'unverified'])
@pytest.mark.parametrize('failure', ['exception', 'response'])
def test_receipt_failure_never_authorizes_another_publication(qif, monkeypatch, initial, failure):
    from backend.qif import task_service as module
    identity = task(qif)
    qif._update(identity, ontology_id='demo', graph_sync={'status': initial, 'publication_id': 'receipt-1'})
    calls = []
    def verify(**kwargs):
        calls.append('verify')
        if failure == 'exception':
            raise FileNotFoundError('Retained artifact temporarily unavailable')
        return {'status': 'pending'}
    def write(**kwargs):
        pytest.fail('Unresolved publication replayed')
    monkeypatch.setattr(module, 'get_publisher', lambda: SimpleNamespace(sync_graph=write, verify_graph=verify))
    qif._sync_graph(identity)
    assert qif.get(identity)['status'] == 'publication_unverified'
    assert qif.get(identity)['graph_sync']['status'] == 'unverified'
    qif.queue_graph_retry(identity)
    qif._executor.submitted[-1][1].set_running_or_notify_cancel()
    qif._executor.submitted[-1][0]()
    assert calls == ['verify', 'verify']
    assert qif.get(identity)['status'] == 'publication_unverified'
