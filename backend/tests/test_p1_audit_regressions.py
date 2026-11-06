"""Isolated regressions for bridge recovery, gateway headers and worker lifecycle."""
import ast
import io
import logging
import signal
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from unittest.mock import AsyncMock
import asyncio

import pytest

from backend.agentic_service.bridge_jobs import BridgeJobs, BridgeConflict, GraphBridgeClient
from backend.mesh_store import InMemoryRegistry
from backend.tests.test_bridge_jobs import Source, Graph


def test_published_bridge_requires_authoritative_receipt():
    graph = Graph()
    jobs = BridgeJobs(InMemoryRegistry(), Source(), graph)
    preview = jobs.preview('ontology', 'import', 'reader')
    ids = [preview['candidates'][0]['candidate_id']]
    jobs.publish(preview['job_id'], ids, 'reviewer')
    graph.receipts.clear()
    with pytest.raises(BridgeConflict, match='receipt is missing'):
        jobs.publish(preview['job_id'], ids, 'reviewer')
    assert jobs.get(preview['publication_job_id'])['status'] == 'stale'
    assert len(graph.calls) == 1


def test_bridge_gateway_header_is_scoped(monkeypatch):
    monkeypatch.setenv('GRAPH_PUBLICATION_TOKEN', 'test-token')
    monkeypatch.setenv('DEPO_API_GATEWAY_URL', 'https://gateway.test/depo')
    monkeypatch.setenv('DEPO_APIM_SUBSCRIPTION_KEY', 'test-subscription')
    client = MagicMock()
    client.request.return_value.status_code = 200
    client.request.return_value.json.return_value = {'ok': True}
    with patch('httpx.Client') as factory:
        factory.return_value.__enter__.return_value = client
        for base, expected in [('https://gateway.test/depo/api/v1', True), ('https://peer.test/api/v1', False)]:
            monkeypatch.setenv('GRAPH_SERVICE_URL', base)
            GraphBridgeClient().receipt('id')
            headers = client.request.call_args.kwargs['headers']
            assert headers['Authorization'] == 'Bearer test-token'
            assert ('Ocp-Apim-Subscription-Key' in headers) == expected


def test_worker_retries_registration_before_claiming():
    path = Path(__file__).parents[1] / 'data_pipeline_service' / 'worker.py'
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    stop = MagicMock()
    stop.is_set.side_effect = [False, False, True]
    status = MagicMock()
    status.put.side_effect = [RuntimeError('temporary database outage'), {}, {}, {}]
    records = MagicMock()
    records.claim_next.return_value = None
    runner = MagicMock()
    environment = dict(threading=SimpleNamespace(Event=lambda: stop), signal=signal, logging=logging,
                       bounded_timeout_seconds=lambda *a, **k: k['default'], worker_status=status,
                       run_records=records, runner=runner)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), environment)
    with patch.object(signal, 'signal'):
        environment['run']()
    assert records.claim_next.call_count == 1
    assert stop.wait.call_count == 2
    runner.shutdown.assert_called_once()


def reqif_parser():
    path = Path(__file__).parents[1] / 'Services' / 'unified_data_import.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FileParser')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_parse_reqif')
    node.decorator_list = []
    environment = {}
    module = ast.parse('from __future__ import annotations')
    module.body.append(node)
    exec(compile(module, str(path), 'exec'), environment)
    return environment['_parse_reqif']


def test_reqif_archive_rejects_expansion_over_budget(monkeypatch):
    monkeypatch.setenv('DEPO_MAX_INGEST_BYTES', '1024')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as writer:
        writer.writestr('sample.reqif', '<REQ-IF>' + ' ' * 2048 + '</REQ-IF>')
    assert len(archive.getvalue()) < 1024
    rows, result = reqif_parser()(archive.getvalue())
    assert rows == []
    assert 'expanded-byte limit' in result['error']


def test_reqif_archive_accepts_small_member(monkeypatch):
    monkeypatch.setenv('DEPO_MAX_INGEST_BYTES', '1024')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as writer:
        writer.writestr('sample.reqif', '<REQ-IF/>')
    rows, result = reqif_parser()(archive.getvalue())
    assert 'error' not in result


def test_graph_reset_invalidates_bridge_publications():
    from backend.depo_platform.maintenance import reconcile_graph_reset
    cursor = MagicMock()
    cursor.rowcount = 2
    db = MagicMock()
    db.cursor.return_value.__enter__.return_value = cursor
    with patch('backend.depo_platform.credentials.uses_postgres', return_value=True), \
         patch('backend.mesh_store.PostgresRegistry') as registry:
        registry.return_value._connect.return_value.__enter__.return_value = db
        result = reconcile_graph_reset()
    assert result['invalidated_bridge_publications'] == 2
    assert cursor.execute.call_args_list[1].args[1][1] == 'semantic_bridge_jobs_v1'
    assert "value->>'kind'='publication'" in cursor.execute.call_args_list[1].args[0]


def test_read_tool_execution_returns_explicit_completed_state():
    path = Path(__file__).parents[1] / 'agentic_service' / 'router.py'
    node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run')
    node.decorator_list = []
    async def io_call(function, *args, **kwargs):
        return function(*args, **kwargs)
    environment = dict(asyncio=asyncio, plan=lambda _: {'requires_approval': False, 'tool': {'mutates': False}},
                       graph_read_identity=MagicMock(), _agent_io=io_call,
                       telemetry=SimpleNamespace(start=lambda **_: ({'run_id': 'read-run'}, 0)),
                       _dispatch=AsyncMock(return_value={'tool_id': 'read-tool', 'result': {'items': []}}),
                       _tool_span=MagicMock(), _finish_observation=MagicMock(),
                       bounded_timeout_seconds=lambda *a, **kw: kw['default'], time=SimpleNamespace(perf_counter=lambda: 1))
    module = ast.parse('from __future__ import annotations')
    module.body.append(node)
    exec(compile(module, str(path), 'exec'), environment)
    result = asyncio.run(environment['run']({'tool_id': 'read-tool'}, SimpleNamespace(state=SimpleNamespace(request_id='test'))))
    assert result['status'] == 'completed'
    assert result['execution_kind'] == 'agent'
    assert result['run_id'] == 'read-run'
