import json
import uuid

from backend.Services.unified_data_import import UnifiedDataImportService, import_tasks


def test_shacl_persist(tmp_path, monkeypatch):
    # Ensure fixture is available (no-op) and initialize directories under repo
    assert monkeypatch is not None
    UnifiedDataImportService.initialize()

    task_id = str(uuid.uuid4())
    task = {
        'task_id': task_id,
        'status': 'processing',
        'parsed_rows': [{'id': 1}],
        # Simulate a SHACL report produced by OWL generation/validation
        'shacl_report': {'conforms': False, 'results': ['warning']},
    }
    import_tasks[task_id] = task

    # Persist the task — should write snapshot and a separate shacl_report file
    UnifiedDataImportService._persist_task(task_id)

    snap_path = UnifiedDataImportService._task_snapshot_path(task_id)
    assert snap_path.exists(), "Snapshot file not written"

    # Read snapshot and ensure pointer exists
    snap = json.loads(snap_path.read_text(encoding='utf-8'))
    assert '_shacl_file' in snap, "Snapshot missing _shacl_file pointer"

    shacl_file = snap_path.parent / snap['_shacl_file']
    assert shacl_file.exists(), "SHACL report file not written"

    content = json.loads(shacl_file.read_text(encoding='utf-8'))
    assert content.get('conforms') is False
