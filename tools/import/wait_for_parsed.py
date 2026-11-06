#!/usr/bin/env python3
"""Poll an import task and its persisted snapshot for parsed output."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: wait_for_parsed.py <task_id> [max_wait_seconds] [poll_interval] [backend_url]")
        return 2
    task_id = sys.argv[1]
    max_wait = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    backend = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("BACKEND", "http://127.0.0.1:8000")
    status_url = f"{backend.rstrip('/')}/api/v1/import/status/{task_id}"
    snapshot = REPO_ROOT / "uploads" / ".import_tasks" / f"{task_id}.json"

    iterations = max(1, int(max_wait / interval))
    for index in range(iterations):
        try:
            response = requests.get(status_url, timeout=10)
            print(index, "STATUS", response.status_code, response.text)
        except Exception as exc:
            print(index, "STATUS ERR", exc)
        try:
            data = json.loads(snapshot.read_text(encoding="utf-8"))
            pointer = data.get("_parsed_rows_file") or data.get("parsed_rows_file")
            if pointer or data.get("parsed_rows"):
                print("SNAPSHOT has parsed output:", pointer or "inline parsed_rows")
                return 0
        except FileNotFoundError:
            pass
        except Exception as exc:
            print("SNAP ERR", exc)
        time.sleep(interval)
    print("Timed out waiting for parsed output")
    return 1


if __name__ == "__main__":
    sys.exit(main())