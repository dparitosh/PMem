import importlib
from pathlib import Path
import sys

# Ensure project root is on sys.path so `backend` package imports work
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))

m = importlib.import_module('backend.Services.tests.test_shacl_persistence')
print('module loaded:', m)
try:
    # Try to call the pytest-style test directly (may require fixtures)
    m.test_shacl_persist()
    print('test_shacl_persist OK')
except TypeError as te:
    # The test likely requires pytest fixtures (tmp_path, monkeypatch).
    # Fall back to a manual persistence check equivalent to the test.
    print('test_shacl_persist requires fixtures; running manual persistence check instead')
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService, import_tasks
        import uuid
        UnifiedDataImportService.initialize()
        task_id = str(uuid.uuid4())
        task = {
            'task_id': task_id,
            'status': 'processing',
            'parsed_rows': [{'id': 1}],
            'shacl_report': {'conforms': False, 'results': ['warning']},
        }
        import_tasks[task_id] = task
        print('Calling _persist_task for', task_id)
        UnifiedDataImportService._persist_task(task_id)
        snap = UnifiedDataImportService._task_snapshot_path(task_id)
        print('Snapshot exists:', snap.exists())
        shacl_file = snap.with_name(snap.name + '.shacl_report.json')
        print('SHACL file exists:', shacl_file.exists())
        if shacl_file.exists():
            print(shacl_file.read_text())
    except Exception:
        import traceback
        traceback.print_exc()
except AssertionError as e:
    print('AssertionError:', e)
except Exception as e:
    import traceback
    traceback.print_exc()
