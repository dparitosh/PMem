"""Remove quiescent Import tasks and their owned artifacts, retaining deletion fences."""
import json
import logging
import re
import shutil
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)
QUIESCENT = {'completed', 'failed', 'cancelled', 'canceled', 'ready_for_commit'}


def cleared(task_id, root):
    return (Path(root) / '.cleared' / task_id).exists()


def _receipt(path, identifier, status):
    temporary = path.with_name('.' + identifier + '-' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump({'task_id': identifier, 'status': status}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def clear_import_workflows(*, dry_run=False, importer=None, artifacts=None):
    # Caller holds the exclusive ontology-maintenance lock; importer writers
    # use the shared lock for creation, parse, commit and background generation.
    if importer is None:
        from backend.Services.unified_data_import import UnifiedDataImportService
        from backend.Services.workflow_artifact_service import WorkflowArtifactService
        from backend.qif.ownership import task_root
        from types import SimpleNamespace
        root = task_root(Path(__file__).resolve().parents[2] / 'uploads' / 'qif_workflows')
        def schema_tasks():
            return [json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*/manifest.json')]
        schema = SimpleNamespace(TASK_STORE_DIR=root, list_tasks=schema_tasks)
        schema_artifacts = SimpleNamespace(ARTIFACT_ROOT=root, task_dir=lambda identity: root / identity, _registry=lambda: None)
        stores = [(UnifiedDataImportService, WorkflowArtifactService), (schema, schema_artifacts)]
        # Inspect all stores before removing anything from any of them.
        for service, files in stores:
            clear_import_workflows(dry_run=True, importer=service, artifacts=files)
        outcomes = [clear_import_workflows(dry_run=dry_run, importer=service, artifacts=files) for service, files in stores]
        return {'status': 'partial' if any(o['status'] != 'success' for o in outcomes) else 'success',
                'candidate_count': sum(o.get('candidate_count', 0) for o in outcomes),
                'deleted_count': sum(o.get('deleted_count', 0) for o in outcomes),
                'stores': outcomes}
    if artifacts is None:
        from backend.Services.workflow_artifact_service import WorkflowArtifactService
        artifacts = WorkflowArtifactService
    tasks_by_id = {task['task_id']: task for task in importer.list_tasks()}
    # Failed file/registry removal remains retryable even though the fence hides
    # it from normal Import history and stale readers.
    for marker in (importer.TASK_STORE_DIR / '.cleared').glob('*'):
        if marker.name.startswith('.'):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', marker.name) or marker.is_symlink() or not marker.resolve().is_relative_to(importer.TASK_STORE_DIR.resolve()):
            raise ValueError('Invalid Import cleanup receipt path')
        try:
            receipt = json.loads(marker.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError):
            receipt = {}  # Recover receipts interrupted by an older writer.
        if not isinstance(receipt, dict):
            receipt = {}
        registry = artifacts._registry()
        remaining = artifacts.task_dir(marker.name).exists() or any(importer.TASK_STORE_DIR.glob(marker.name + '.*'))
        if receipt.get('status') != 'cleared' or remaining or (registry is not None and registry.get(marker.name) is not None):
            tasks_by_id[marker.name] = {'task_id': marker.name, 'status': 'failed'}
    tasks = list(tasks_by_id.values())
    blocked = [t['task_id'] for t in tasks if t.get('status') not in (QUIESCENT | {'awaiting_approval', 'graph_sync_failed'}) or t.get('committing') or t.get('graph_sync', {}).get('status') in {'unverified', 'publishing'}]
    if blocked:
        raise ValueError('Import tasks are active or have an uncertain outcome. Resolve or cancel them before clearing workflows: ' + ', '.join(blocked[:10]))
    if dry_run:
        return {'status': 'success', 'candidate_count': len(tasks)}
    deleted, failed = [], []
    for task in tasks:
        identifier = task['task_id']
        receipt_path = None
        try:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', identifier):
                raise ValueError('Invalid task identity')
            snapshot_root = importer.TASK_STORE_DIR.resolve()
            artifact_root = artifacts.ARTIFACT_ROOT.resolve()
            directory = artifacts.task_dir(identifier)
            if directory.is_symlink() or not directory.resolve().is_relative_to(artifact_root) or directory.resolve() == artifact_root:
                raise ValueError('Task artifacts are outside storage boundary')
            # Fences precede deletion so stale process caches cannot restore or
            # rewrite a cleared task, including after a partial file failure.
            for root in (snapshot_root, artifact_root):
                marker = root / '.cleared' / identifier
                if marker.is_symlink() or not marker.resolve().is_relative_to(root):
                    raise ValueError('Deletion fence is outside storage boundary')
                marker.parent.mkdir(parents=True, exist_ok=True)
                _receipt(marker, identifier, 'deleting')
                if root == snapshot_root:
                    receipt_path = marker
            if directory.exists():
                shutil.rmtree(directory)
            for path in snapshot_root.glob(identifier + '.*'):
                if path.is_symlink() or not path.resolve().is_relative_to(snapshot_root):
                    raise ValueError('Task snapshot is outside storage boundary')
                if path.is_file():
                    path.unlink()
            registry = artifacts._registry()
            if registry is not None:
                with registry._connect() as db, db.cursor() as cursor:
                    cursor.execute('DELETE FROM depo_registry WHERE namespace=%s AND key=%s',
                                   ('workflow_artifact_manifests_v1', identifier))
                if registry.get(identifier) is not None:
                    raise RuntimeError('Import manifest deletion verification failed')
            for root in {snapshot_root, artifact_root}:
                _receipt(root / '.cleared' / identifier, identifier, 'cleared')
            deleted.append(identifier)
        except Exception:
            logger.exception('Import workflow cleanup failed for %s', identifier)
            if receipt_path is not None:
                try:
                    _receipt(receipt_path, identifier, 'cleanup_failed')
                except OSError:
                    logger.exception('Import cleanup receipt update failed for %s; retry will reconcile the deletion fence', identifier)
            failed.append(identifier)
    return {'status': 'partial' if failed else 'success', 'deleted_count': len(deleted),
            'deleted_task_ids': deleted, 'failed_task_ids': failed}
