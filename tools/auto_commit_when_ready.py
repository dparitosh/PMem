import sys
import time
import json
from pathlib import Path
import subprocess
import os

if len(sys.argv) < 2:
    print('Usage: auto_commit_when_ready.py <task_id> [timeout_seconds]')
    sys.exit(2)

task_id = sys.argv[1]
timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 300
snapshot = Path(__file__).resolve().parents[1] / 'uploads' / '.import_tasks' / f'{task_id}.json'
start = time.time()
print('Monitoring', snapshot)
while time.time() - start < timeout:
    if snapshot.exists():
        try:
            data = json.loads(snapshot.read_text(encoding='utf-8'))
            prs = data.get('parsed_rows')
            if prs and len(prs) > 0:
                print('Parsed rows detected:', len(prs))
                # Run commit helper
                print('Running pre-commit+commit helper...')
                r = subprocess.run(['python', 'Depo_onto/tools/run_commit.py', task_id], capture_output=True, text=True)
                print(r.stdout)
                print(r.stderr)
                if r.returncode == 0:
                    print('Commit helper returned success; launching Playwright capture...')
                    # Run Node capture script; set BACKEND and URL for the capture helper
                    env = os.environ.copy()
                    env.setdefault('BACKEND', 'http://127.0.0.1:8000')
                    env.setdefault('URL', 'http://127.0.0.1:3000')
                    node_cmd = ['node', 'Depo_onto/frontend/tools/capture_tooltip.js']
                    try:
                        p2 = subprocess.run(node_cmd, capture_output=True, text=True, env=env)
                        print('Capture stdout:\n', p2.stdout)
                        print('Capture stderr:\n', p2.stderr)
                        sys.exit(p2.returncode or 0)
                    except FileNotFoundError as fe:
                        print('Node executable not found; skipping capture:', fe)
                        sys.exit(0)
                else:
                    sys.exit(r.returncode)
        except Exception as e:
            print('Error reading snapshot:', e)
    time.sleep(2)
print('Timed out waiting for parsed_rows')
sys.exit(1)
