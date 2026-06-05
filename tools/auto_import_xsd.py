#!/usr/bin/env python3
"""Upload an XSD to the backend import pipeline, poll, commit, and report outputs.

Usage:
  python tools/auto_import_xsd.py [path/to/file.xsd] [backend_url]

Defaults:
  file: data/business_object_models/managed_model_based_3d_engineering/bom.xsd
  backend: http://127.0.0.1:8000
"""
import sys
import time
import os
import requests
from pathlib import Path

DEFAULT_FILE = Path(r"C:\Users\895428\DEPO_RR\Depo_onto\data\business_object_models\managed_model_based_3d_engineering\bom.xsd")

def upload_file(file_path, backend, ontology_mapping=''):
    url = f"{backend.rstrip('/')}/api/v1/import/upload"
    print('Uploading', file_path, 'to', url)
    with open(file_path, 'rb') as fh:
        files = {'file': (Path(file_path).name, fh, 'application/xml')}
        data = {'ontology_mapping': ontology_mapping}
        r = requests.post(url, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json()

def poll_status(task_id, backend, timeout=600, interval=3):
    url = f"{backend.rstrip('/')}/api/v1/import/status/{task_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                j = r.json()
                status = j.get('status') or j.get('current_stage') or j.get('task', {}).get('status')
                print('Status:', status)
                if status in ('completed', 'failed', 'committed'):
                    return j
            else:
                print('Status request returned', r.status_code)
        except Exception as e:
            print('Status poll error:', e)
        time.sleep(interval)
    raise TimeoutError('Timed out waiting for import to complete')

def pre_commit_check(task_id, backend):
    url = f"{backend.rstrip('/')}/api/v1/import/pre-commit/{task_id}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def commit(task_id, backend):
    url = f"{backend.rstrip('/')}/api/v1/import/commit/{task_id}"
    r = requests.post(url, timeout=300)
    r.raise_for_status()
    return r.json()

def find_generated_ontology_files(repo_root):
    ont_dir = Path(repo_root) / 'frontend' / 'public' / 'Ontology'
    if not ont_dir.exists():
        return []
    return sorted([str(p) for p in ont_dir.iterdir() if p.is_file()], key=lambda p: p, reverse=True)

def main():
    file_path = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_FILE)
    backend = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('BACKEND', 'http://127.0.0.1:8000')
    ontology_mapping = sys.argv[3] if len(sys.argv) > 3 else os.environ.get('ONTOLOGY_MAPPING', '')

    file_path = Path(file_path)
    if not file_path.exists():
        print('File not found:', file_path)
        return 2

    try:
        resp = upload_file(str(file_path), backend, ontology_mapping=ontology_mapping)
        task_id = resp.get('task_id') or resp.get('task') or resp.get('taskId')
        print('Upload started, task_id=', task_id)
    except Exception as e:
        print('Upload failed:', e)
        return 3

    try:
        status = poll_status(task_id, backend, timeout=900, interval=4)
        print('Final status object:', status)
    except Exception as e:
        print('Polling failed:', e)
        return 4

    # Pre-commit
    try:
        pre = pre_commit_check(task_id, backend)
        print('Pre-commit check:', pre)
    except Exception as e:
        print('Pre-commit check failed:', e)

    # Commit
    try:
        commit_res = commit(task_id, backend)
        print('Commit response:', commit_res)
    except Exception as e:
        print('Commit failed:', e)
        return 5

    # Report generated ontology files
    repo_root = Path(__file__).resolve().parents[2]
    files = find_generated_ontology_files(repo_root)
    if files:
        print('Generated ontology files (most recent first):')
        for f in files[:10]:
            print(' -', f)
    else:
        print('No generated ontology files found under frontend/public/Ontology')

    print('Import completed successfully')
    return 0

if __name__ == '__main__':
    sys.exit(main())
#!/usr/bin/env python3
"""Upload an XSD to the backend import pipeline, poll, commit, and report outputs.

Usage:
  python tools/auto_import_xsd.py [path/to/file.xsd] [backend_url]

Defaults:
  file: data/business_object_models/managed_model_based_3d_engineering/bom.xsd
  backend: http://127.0.0.1:8000
"""
import sys
import time
import os
import requests
from pathlib import Path

# Default: file is under the Depo_onto package 'data' directory
DEFAULT_FILE = Path(__file__).resolve().parents[1] / 'data' / 'business_object_models' / 'managed_model_based_3d_engineering' / 'bom.xsd'

# Backward-compatible fallback to workspace root if necessary
FALLBACK_FILE = Path(__file__).resolve().parents[2] / 'data' / 'business_object_models' / 'managed_model_based_3d_engineering' / 'bom.xsd'

def upload_file(file_path, backend):
    url = f"{backend.rstrip('/')}/api/v1/import/upload"
    print('Uploading', file_path, 'to', url)
    with open(file_path, 'rb') as fh:
        files = {'file': (Path(file_path).name, fh, 'application/xml')}
        data = {'ontology_mapping': ''}
        r = requests.post(url, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json()

def poll_status(task_id, backend, timeout=900, interval=4):
    url = f"{backend.rstrip('/')}/api/v1/import/status/{task_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                j = r.json()
                status = j.get('status') or j.get('current_stage') or j.get('task', {}).get('status')
                print('Status:', status)
                if status in ('completed', 'failed', 'committed'):
                    return j
            else:
                print('Status request returned', r.status_code)
        except Exception as e:
            print('Status poll error:', e)
        time.sleep(interval)
    raise TimeoutError('Timed out waiting for import to complete')


def commit_with_retries(task_id, backend, attempts=5):
    """Attempt pre-commit and commit with retries and simple backoff, tolerant of 429/read timeouts."""
    backoff = [5, 10, 20, 30, 60]
    for i in range(attempts):
        try:
            print(f'Pre-commit check (attempt {i+1}/{attempts}) for {task_id}')
            pre = requests.get(f"{backend.rstrip('/')}/api/v1/import/pre-commit/{task_id}", timeout=30)
            if pre.status_code == 200:
                try:
                    prej = pre.json()
                    print('Pre-commit response:', str(prej)[:200])
                except Exception:
                    print('Pre-commit returned non-json or empty body')
            else:
                print('Pre-commit returned', pre.status_code)
        except Exception as e:
            print('Pre-commit request failed:', e)

        try:
            print(f'Attempting commit (attempt {i+1}/{attempts}) for {task_id}')
            commit_res = requests.post(f"{backend.rstrip('/')}/api/v1/import/commit/{task_id}", timeout=300)
            if commit_res.status_code in (200, 201):
                try:
                    cj = commit_res.json()
                    print('Commit response:', str(cj)[:200])
                except Exception:
                    print('Commit succeeded with non-json response')
                return True
            else:
                print('Commit returned', commit_res.status_code)
                # If rate limited, backoff longer
                if commit_res.status_code == 429:
                    wait = backoff[min(i, len(backoff)-1)]
                    print(f'Rate limited; sleeping {wait}s')
                    time.sleep(wait)
        except Exception as e:
            print('Commit attempt failed:', e)
        # short backoff before retry
        time.sleep(backoff[min(i, len(backoff)-1)])
    return False

def pre_commit_check(task_id, backend):
    url = f"{backend.rstrip('/')}/api/v1/import/pre-commit/{task_id}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def commit(task_id, backend):
    url = f"{backend.rstrip('/')}/api/v1/import/commit/{task_id}"
    r = requests.post(url, timeout=300)
    r.raise_for_status()
    return r.json()

def find_generated_ontology_files(repo_root):
    ont_dir = Path(repo_root) / 'frontend' / 'public' / 'Ontology'
    if not ont_dir.exists():
        return []
    return sorted([str(p) for p in ont_dir.iterdir() if p.is_file()], key=lambda p: p, reverse=True)

def main():
    file_path = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_FILE)
    backend = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('BACKEND', 'http://127.0.0.1:8000')

    file_path = Path(file_path)
    if not file_path.exists():
        # try defaults
        if DEFAULT_FILE.exists():
            file_path = DEFAULT_FILE
            print('Using default file:', file_path)
        elif FALLBACK_FILE.exists():
            file_path = FALLBACK_FILE
            print('Using fallback file:', file_path)
        else:
            print('File not found:', file_path)
            print('Tried defaults:', DEFAULT_FILE, FALLBACK_FILE)
            return 2

    try:
        resp = upload_file(str(file_path), backend)
        task_id = resp.get('task_id') or resp.get('task') or resp.get('taskId')
        print('Upload started, task_id=', task_id)
    except Exception as e:
        print('Upload failed:', e)
        return 3

    # Poll status (best-effort). If polling fails/ times out, continue to attempt commit.
    try:
        status = poll_status(task_id, backend, timeout=900, interval=4)
        print('Final status object:', status)
    except Exception as e:
        print('Polling failed (will attempt commit anyway):', e)

    # Attempt pre-commit + commit with retries/backoff
    committed = commit_with_retries(task_id, backend, attempts=6)
    if not committed:
        print('Commit attempts exhausted or failed')
        return 5

    # Report generated ontology files
    repo_root = Path(__file__).resolve().parents[2]
    files = find_generated_ontology_files(repo_root)
    if files:
        print('Generated ontology files (most recent first):')
        for f in files[:10]:
            print(' -', f)
    else:
        print('No generated ontology files found under frontend/public/Ontology')

    print('Import completed successfully')
    return 0

if __name__ == '__main__':
    sys.exit(main())
