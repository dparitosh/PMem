import json
import sys
from pathlib import Path
from pprint import pprint

# Ensure project packages import correctly when run from workspace root
_here = Path(__file__).resolve().parents[2]
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import sys as _sys

TASK_ID = _sys.argv[1] if len(_sys.argv) > 1 else ""

def main():
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService, import_tasks
    except Exception:
        # Try relative import fallback
        from Services.unified_data_import import UnifiedDataImportService, import_tasks

    print('Snapshot file path:', UnifiedDataImportService._task_snapshot_path(TASK_ID))
    restored = UnifiedDataImportService._restore_task(TASK_ID)
    print('Restored:', bool(restored))
    task = import_tasks.get(TASK_ID)
    if not task:
        print('No in-memory task found')
        return 2

    print('Task status:', task.get('status'))
    print('Current stage:', task.get('current_stage'))
    print('Preview data present:', bool(task.get('preview_data')))
    print('Parsed rows present:', bool(task.get('parsed_rows')))
    if task.get('parsed_rows'):
        print('Parsed rows count:', len(task.get('parsed_rows')))
    if task.get('preview_data'):
        print('Preview summary:')
        pprint(task.get('preview_data'))
    if task.get('result'):
        print('Result keys:', list(task.get('result').keys()))

    # print small sample of parsed_rows
    prs = task.get('parsed_rows') or []
    print('Sample parsed row (first):')
    if prs:
        pprint(prs[0])
    else:
        print('(none)')

if __name__ == '__main__':
    raise SystemExit(main())
