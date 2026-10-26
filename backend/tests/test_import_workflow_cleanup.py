import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.depo_platform.import_cleanup import clear_import_workflows, cleared


def stores(tmp_path, status='completed', committing=False, registry=None):
    snapshots = tmp_path / 'tasks'
    artifacts = tmp_path / 'artifacts'
    snapshots.mkdir(); artifacts.mkdir()
    identifier = 'task-123'
    task = {'task_id': identifier, 'status': status, 'committing': committing}
    (snapshots / f'{identifier}.json').write_text(json.dumps(task))
    (snapshots / f'{identifier}.json.parsed_rows.json').write_text('[]')
    (snapshots / f'{identifier}.json.parsed_rows.abc123.json').write_text('[]')
    (snapshots / f'{identifier}.lock').write_bytes(b'0')
    directory = artifacts / identifier
    directory.mkdir(); (directory / 'source.xml').write_text('<test/>')
    importer = SimpleNamespace(TASK_STORE_DIR=snapshots, list_tasks=lambda: [] if cleared(identifier, snapshots) else [task])
    files = SimpleNamespace(ARTIFACT_ROOT=artifacts, task_dir=lambda identity: artifacts / identity, _registry=lambda: registry)
    return importer, files, identifier


def test_cleanup_removes_snapshots_artifacts_and_exact_postgres_manifest(tmp_path):
    registry = MagicMock()
    registry.get.return_value = None
    importer, files, identity = stores(tmp_path, registry=registry)
    (files.ARTIFACT_ROOT / 'unrelated').mkdir()
    result = clear_import_workflows(importer=importer, artifacts=files)
    assert result['deleted_count'] == 1
    assert not list(importer.TASK_STORE_DIR.glob(identity + '.*'))
    assert not files.task_dir(identity).exists()
    assert (files.ARTIFACT_ROOT / 'unrelated').exists()
    assert cleared(identity, importer.TASK_STORE_DIR)
    cursor = registry._connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.execute.assert_called_once_with('DELETE FROM depo_registry WHERE namespace=%s AND key=%s', ('workflow_artifact_manifests_v1', identity))
    assert clear_import_workflows(importer=importer, artifacts=files)['deleted_count'] == 0


@pytest.mark.parametrize('status,committing', [('processing', False), ('queued', False), ('completed', True), ('outcome_unknown', False)])
def test_busy_or_uncertain_tasks_block_before_any_deletion(tmp_path, status, committing):
    importer, files, identity = stores(tmp_path, status, committing)
    with pytest.raises(ValueError, match='active or have an uncertain outcome'):
        clear_import_workflows(importer=importer, artifacts=files)
    assert files.task_dir(identity).exists()
    assert not cleared(identity, importer.TASK_STORE_DIR)


def test_preview_does_not_touch_files_or_database(tmp_path):
    registry = MagicMock()
    importer, files, identity = stores(tmp_path, registry=registry)
    assert clear_import_workflows(dry_run=True, importer=importer, artifacts=files)['candidate_count'] == 1
    assert files.task_dir(identity).exists()
    assert not cleared(identity, importer.TASK_STORE_DIR)
    registry._connect.assert_not_called()


def test_failed_removal_is_reported_and_can_be_retried(tmp_path, monkeypatch):
    import shutil
    importer, files, identity = stores(tmp_path)
    original = shutil.rmtree
    monkeypatch.setattr(shutil, 'rmtree', MagicMock(side_effect=PermissionError('locked')))
    result = clear_import_workflows(importer=importer, artifacts=files)
    assert result['status'] == 'partial'
    assert result['failed_task_ids'] == [identity]
    assert cleared(identity, importer.TASK_STORE_DIR)
    monkeypatch.setattr(shutil, 'rmtree', original)
    assert clear_import_workflows(importer=importer, artifacts=files)['status'] == 'success'
    assert not files.task_dir(identity).exists()


def test_artifact_path_escape_is_rejected(tmp_path):
    importer, files, identity = stores(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir(); (outside / 'keep').write_text('keep')
    files.task_dir = lambda task: outside
    with pytest.raises(ValueError, match='outside storage boundary'):
        clear_import_workflows(importer=importer, artifacts=files)
    assert not cleared(identity, importer.TASK_STORE_DIR)
    assert (outside / 'keep').exists()


def test_cleared_artifacts_cannot_be_recreated_by_a_stale_writer(tmp_path, monkeypatch):
    from backend.Services.workflow_artifact_service import WorkflowArtifactService
    monkeypatch.setattr(WorkflowArtifactService, 'ARTIFACT_ROOT', tmp_path)
    (tmp_path / '.cleared').mkdir()
    (tmp_path / '.cleared/task-123').write_text('{}')
    assert WorkflowArtifactService.get_manifest('task-123') is None
    with pytest.raises(ValueError, match='cleared by an administrator'):
        WorkflowArtifactService.ensure_task('task-123')
    assert not (tmp_path / 'task-123').exists()


def test_schema_set_stale_reader_and_writer_are_fenced(tmp_path):
    from backend.qif.task_service import QifTaskService
    from fastapi import HTTPException
    service = QifTaskService(root=tmp_path)
    identity = 'a' * 32
    (tmp_path / '.cleared').mkdir()
    (tmp_path / '.cleared' / identity).write_text('{}')
    try:
        with pytest.raises(HTTPException) as error:
            service._read(identity)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException):
            service._write(identity, {'task_id': identity})
        assert not (tmp_path / identity).exists()
    finally:
        service.shutdown()


def test_full_cleanup_checks_import_activity_before_deleting_graph():
    import ast
    from fastapi import HTTPException
    from unittest.mock import patch
    source = Path(__file__).parents[1] / 'routes/admin_routes.py'
    node = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'clean_neo4j_schema')
    node.decorator_list = []
    cleaner = MagicMock()
    scope = dict(CleanSchemaRequest=object, CLEAN_SCHEMA_CONFIRM_TOKEN='confirm', HTTPException=HTTPException,
                 SCHEMA_CLEANER_AVAILABLE=True, Neo4jSchemaCleaner=cleaner, logger=MagicMock())
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    with patch('backend.depo_platform.import_cleanup.clear_import_workflows', side_effect=ValueError('Import tasks are active')):
        with pytest.raises(HTTPException) as error:
            scope['clean_neo4j_schema'](SimpleNamespace(confirm='confirm'))
    assert error.value.status_code == 409
    cleaner.assert_not_called()


@pytest.mark.parametrize('receipt', ['', '{', '{"status":"deleting"}', '{"status":"cleared"}'])
def test_interrupted_cleanup_receipts_reconcile_remaining_files(tmp_path, receipt):
    importer, files, identity = stores(tmp_path)
    marker = importer.TASK_STORE_DIR / '.cleared' / identity
    marker.parent.mkdir()
    marker.write_text(receipt)
    result = clear_import_workflows(importer=importer, artifacts=files)
    assert result['status'] == 'success'
    assert result['deleted_count'] == 1
    assert not files.task_dir(identity).exists()
    assert json.loads(marker.read_text())['status'] == 'cleared'


def test_failed_error_receipt_does_not_hide_partial_cleanup(tmp_path, monkeypatch):
    import shutil
    from backend.depo_platform import import_cleanup
    importer, files, identity = stores(tmp_path)
    original = import_cleanup._receipt
    def write(path, task_id, status, phases=None):
        if status == 'cleanup_failed':
            raise PermissionError('locked receipt')
        return original(path, task_id, status, phases)
    monkeypatch.setattr(import_cleanup, '_receipt', write)
    monkeypatch.setattr(shutil, 'rmtree', MagicMock(side_effect=PermissionError('locked folder')))
    result = clear_import_workflows(importer=importer, artifacts=files)
    assert result['status'] == 'partial'
    assert result['failed_task_ids'] == [identity]
    assert json.loads((importer.TASK_STORE_DIR / '.cleared' / identity).read_text())['status'] == 'deleting'


@pytest.mark.parametrize('dry_run',[False,True])
def test_legal_hold_prevents_any_deletion_fence(tmp_path,dry_run):
    importer, files, identity=stores(tmp_path)
    importer.list_tasks=lambda:[{'task_id':identity,'status':'completed','legal_hold':True}]
    with pytest.raises(ValueError,match='legal hold'):
        clear_import_workflows(dry_run=dry_run,importer=importer,artifacts=files)
    assert files.task_dir(identity).exists()
    assert not cleared(identity,importer.TASK_STORE_DIR)


def test_manifest_hold_protects_hidden_retry_task(tmp_path):
    registry=MagicMock();registry.get.return_value={'legal_hold':True}
    importer,files,identity=stores(tmp_path,registry=registry)
    marker=importer.TASK_STORE_DIR/'.cleared'/identity
    marker.parent.mkdir();marker.write_text('{"status":"cleanup_failed"}')
    with pytest.raises(ValueError,match='legal hold'):
        clear_import_workflows(importer=importer,artifacts=files)
    assert files.task_dir(identity).exists()
    registry._connect.assert_not_called()


def test_phase_receipt_preserves_progress_after_database_failure(tmp_path):
    registry=MagicMock();registry.get.return_value=None
    registry._connect.side_effect=RuntimeError('fixture database unavailable')
    importer,files,identity=stores(tmp_path,registry=registry)
    result=clear_import_workflows(importer=importer,artifacts=files)
    phases=result['task_results'][0]['phases']
    assert result['status']=='partial'
    assert phases=={'artifacts':'completed','snapshots':'completed','manifest':'pending'}
    receipt=json.loads((importer.TASK_STORE_DIR/'.cleared'/identity).read_text())
    assert receipt['phases']==phases
    assert receipt['status']=='cleanup_failed'



def test_retry_receipt_cannot_override_current_active_task_status(tmp_path):
    importer,files,identity=stores(tmp_path,status='processing')
    importer.list_tasks=lambda:[{'task_id':identity,'status':'processing'}]
    marker=importer.TASK_STORE_DIR/'.cleared'/identity
    marker.parent.mkdir();marker.write_text('{"status":"cleanup_failed"}')
    with pytest.raises(ValueError,match='active or have an uncertain outcome'):
        clear_import_workflows(importer=importer,artifacts=files)
    assert files.task_dir(identity).exists()
