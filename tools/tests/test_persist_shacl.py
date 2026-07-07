#!/usr/bin/env python3
"""Create a fake task with parsed_rows and shacl_report and call persist to verify files."""
from pathlib import Path
import json
import uuid
import os
import sys

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))

from backend.Services.unified_data_import import UnifiedDataImportService, import_tasks


def main():
    UnifiedDataImportService.initialize()
    task_id = str(uuid.uuid4())
    task = {
        'task_id': task_id,
        'status': 'processing',
        'parsed_rows': [{'a': 1}, {'a': 2}],
        'shacl_report': {'conforms': False, 'detail': 'test warning'},
    }
    import_tasks[task_id] = task
    print('Calling _persist_task for', task_id)
    UnifiedDataImportService._persist_task(task_id)
    snap = UnifiedDataImportService._task_snapshot_path(task_id)
    print('Snapshot exists:', snap.exists(), 'size=', snap.stat().st_size if snap.exists() else None)
    parsed = snap.with_name(snap.name + '.parsed_rows.json')
    shacl = snap.with_name(snap.name + '.shacl_report.json')
    print('Parsed_rows exists:', parsed.exists())
    if parsed.exists():
        print(parsed.read_text())
    print('Shacl exists:', shacl.exists())
    if shacl.exists():
        print(shacl.read_text())


if __name__ == '__main__':
    main()
