import requests
import sys

TASK_ID = "2965315c-b7cc-430f-9bca-63303c413673"
BASE = "http://127.0.0.1:8000"

def call_pre_commit(task_id):
    url = f"{BASE}/api/v1/import/pre-commit/{task_id}"
    try:
        r = requests.get(url, timeout=30)
        print("PRE-COMMIT", r.status_code)
        print(r.text)
    except Exception as e:
        print("PRE-COMMIT ERROR", e)

def call_commit(task_id):
    url = f"{BASE}/api/v1/import/commit/{task_id}"
    try:
        r = requests.post(url, timeout=120)
        print("COMMIT", r.status_code)
        print(r.text)
    except Exception as e:
        print("COMMIT ERROR", e)

if __name__ == '__main__':
    tid = TASK_ID
    if len(sys.argv) > 1:
        tid = sys.argv[1]
    call_pre_commit(tid)
    call_commit(tid)
