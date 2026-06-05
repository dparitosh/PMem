import requests
import time
import sys
import json

TASK = sys.argv[1] if len(sys.argv) > 1 else '2833530a-6f8c-4d06-b261-e490bdd23df7'
# Optional: max wait seconds and poll interval (seconds)
MAX_WAIT_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 90
POLL_INTERVAL = int(sys.argv[3]) if len(sys.argv) > 3 else 1

BASE = 'http://127.0.0.1:8000'
status_url = f'{BASE}/api/v1/import/status/{TASK}'
snap_path = f'Depo_onto/uploads/.import_tasks/{TASK}.json'

iterations = max(1, int(MAX_WAIT_SECONDS / POLL_INTERVAL))
for i in range(iterations):
    try:
        r = requests.get(status_url, timeout=10)
        print(i, 'STATUS', r.status_code, r.text)
    except Exception as e:
        print(i, 'STATUS ERR', e)
    try:
        with open(snap_path, 'r', encoding='utf-8') as f:
            snap = json.load(f)
            # support both new and legacy pointer keys
            if snap.get('_parsed_rows_file') or snap.get('parsed_rows_file'):
                print('SNAPSHOT has parsed_rows pointer:', snap.get('_parsed_rows_file') or snap.get('parsed_rows_file'))
                break
    except FileNotFoundError:
        pass
    except Exception as e:
        print('SNAP ERR', e)
    time.sleep(POLL_INTERVAL)
else:
    print('Timed out waiting for parsed_rows')
