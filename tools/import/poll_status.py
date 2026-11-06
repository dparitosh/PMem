import sys, time, requests

def poll(task_id, backend='http://127.0.0.1:8000', timeout=300, interval=4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{backend.rstrip('/')}/api/v1/import/status/{task_id}", timeout=10)
            if r.status_code == 200:
                j = r.json()
                s = j.get('status') or j.get('current_stage') or j.get('task', {}).get('status')
                print('Status:', s)
                sys.stdout.flush()
                if s in ('completed', 'failed', 'committed'):
                    print('Final:', j)
                    return 0
        except Exception as e:
            print('err', e)
            sys.stdout.flush()
        time.sleep(interval)
    print('timeout')
    return 2

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: poll_status.py <task_id> [backend]')
        sys.exit(2)
    task = sys.argv[1]
    backend = sys.argv[2] if len(sys.argv) > 2 else __import__('os').environ.get('BACKEND', 'http://127.0.0.1:8000')
    sys.exit(poll(task, backend))
