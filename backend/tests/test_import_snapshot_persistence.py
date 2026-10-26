import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from backend.Services import import_task_persistence as persistence


def test_transient_sharing_failure_retries_without_deleting_destination(tmp_path):
    path = tmp_path / 'task.json'
    path.write_bytes(b'old')
    replace = os.replace
    seen = []
    def blocked(source, destination):
        seen.append(source)
        assert path.read_bytes() == b'old'
        if len(seen) < 3:
            raise PermissionError('sharing violation')
        replace(source, destination)
    with patch.object(persistence.os, 'replace', side_effect=blocked), patch.object(persistence.time, 'sleep'):
        persistence.atomic_bytes(path, b'new')
    assert len(seen) == 3 and path.read_bytes() == b'new'
    assert not list(tmp_path.glob('*.tmp'))


def test_permanent_failure_preserves_old_snapshot_and_sidecar(tmp_path):
    path = tmp_path / 'task.json'
    task = {'task_id': 'task', 'status': 'processing', 'parsed_rows': [{'name': 'old'}]}
    saved = persistence.persist_task(path, task, dict)
    task.update(status='completed', parsed_rows=[{'name': 'new'}])
    replace = os.replace
    def blocked(source, destination):
        if destination == path:
            raise PermissionError('permanent ACL failure')
        replace(source, destination)
    with patch.object(persistence.os, 'replace', side_effect=blocked), patch.object(persistence.time, 'sleep'):
        with pytest.raises(PermissionError):
            persistence.persist_task(path, task, dict)
    assert json.loads(path.read_text()) == saved
    assert json.loads((tmp_path / saved['_parsed_rows_file']).read_text()) == [{'name': 'old'}]
    assert task['_persist_version'] == 1
    assert not list(tmp_path.glob('*.tmp'))


def test_concurrent_writers_serialize_and_reuse_unchanged_sidecars(tmp_path):
    path = tmp_path / 'task.json'
    task = {'task_id': 'task', 'parsed_rows': [{'id': 1}], 'shacl_report': {'conforms': True}}
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: persistence.persist_task(path, task, copy.deepcopy), range(12)))
    assert json.loads(path.read_text())['_persist_version'] == 12
    assert task['_persist_version'] == 12
    assert len(list(tmp_path.glob('task.json.parsed_rows.*.json'))) == 1
    assert len(list(tmp_path.glob('task.json.shacl_report.*.json'))) == 1
    assert not list(tmp_path.glob('*.tmp'))


def test_lock_timeout_never_writes_unlocked_and_old_lock_file_does_not_block(tmp_path):
    path = tmp_path / 'task.json'
    path.with_suffix('.lock').touch()  # abandoned legacy marker
    with persistence.task_lock(path):
        with pytest.raises(persistence.TaskPersistenceError, match='busy'):
            with persistence.task_lock(path, timeout=0):
                pytest.fail('entered without ownership')
    persistence.persist_task(path, {'task_id': 'task'}, dict)
    assert path.exists()


def test_stale_process_snapshot_cannot_overwrite_newer_state(tmp_path):
    path = tmp_path / 'task.json'
    task = {'task_id': 'task', 'status': 'processing'}
    persistence.persist_task(path, task, dict)
    stale = dict(task)
    task['status'] = 'completed'
    persistence.persist_task(path, task, dict)
    with pytest.raises(persistence.TaskPersistenceError, match='newer'):
        persistence.persist_task(path, stale, dict)
    assert json.loads(path.read_text())['status'] == 'completed'


def test_import_service_propagates_storage_failure_and_exposes_warning(tmp_path, monkeypatch):
    from backend.Services import unified_data_import as imports
    service = imports.UnifiedDataImportService
    task = dict(task_id='task', filename='part.xml', file_type='xml', current_stage='parse',
                progress=25, status='processing', message='Parsing')
    monkeypatch.setattr(imports, 'import_tasks', {'task': task})
    monkeypatch.setattr(service, 'TASK_STORE_DIR', tmp_path)
    with patch.object(persistence, 'atomic_bytes', side_effect=PermissionError('ACL denied')):
        with pytest.raises(persistence.TaskPersistenceError, match='permissions'):
            # Exercise the actual service method, excluding only its DB maintenance guard.
            service._persist_task.__func__.__wrapped__(service, 'task')
    assert task['_persistence_error']
    assert service._read_status_task('task')['_persistence_error']
    assert not (tmp_path / 'task.json').exists()
    service._persist_task.__func__.__wrapped__(service, 'task')
    assert '_persistence_error' not in task


@pytest.mark.asyncio
async def test_graph_commit_persistence_failure_cannot_offer_automatic_retry():
    import ast
    import asyncio
    import logging
    from contextlib import nullcontext
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    source = Path(__file__).resolve().parents[1] / 'Services/unified_data_import.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    fn = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == '_run_commit_background')
    task = {'status': 'processing', 'committing': True}
    service = SimpleNamespace(_commit_sync=MagicMock(side_effect=persistence.TaskPersistenceError('snapshot blocked')),
                              _persist_task=MagicMock())
    scope = dict(__package__='backend.Services', asyncio=asyncio, cls=service, task=task, task_id='task', schema={}, logger=logging.getLogger(__name__))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), scope)
    with patch('backend.Services.import_commit_integrity.commit_operation', return_value=nullcontext()):
        await scope['_run_commit_background']()
    assert task['status'] == 'outcome_unknown' and task['commit_phase'] == 'outcome_unknown'
    assert 'before retrying' in task['message']
    service._persist_task.assert_called_once_with('task')


@pytest.mark.skipif(os.name != 'nt', reason='Windows share-delete behavior')
def test_real_windows_reader_lock_recovers_after_handle_closes(tmp_path):
    import ctypes
    from ctypes import wintypes
    path = tmp_path / 'task.json'
    path.write_bytes(b'old')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    timer = threading.Timer(.2, lambda: kernel.CloseHandle(handle))
    timer.start()
    try:
        persistence.atomic_bytes(path, b'new')
    finally:
        timer.join()
    assert path.read_bytes() == b'new'
