#!/usr/bin/env python3
"""Wait for an import task snapshot to contain parsed rows, then run commit helper.

Usage:
  python tools/import/auto_commit_when_ready.py <task_id> [timeout_seconds]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: auto_commit_when_ready.py <task_id> [timeout_seconds]")
        return 2

    task_id = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    snapshot = REPO_ROOT / "uploads" / ".import_tasks" / f"{task_id}.json"
    print("Monitoring", snapshot)

    start = time.time()
    while time.time() - start < timeout:
        if snapshot.exists():
            try:
                data = json.loads(snapshot.read_text(encoding="utf-8"))
                parsed_rows = data.get("parsed_rows")
                parsed_pointer = data.get("_parsed_rows_file") or data.get("parsed_rows_file")
                if parsed_rows or parsed_pointer:
                    print("Parsed output detected")
                    commit_cmd = [sys.executable, str(REPO_ROOT / "tools" / "import" / "run_commit.py"), task_id]
                    result = subprocess.run(commit_cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
                    print(result.stdout)
                    print(result.stderr)
                    if result.returncode != 0:
                        return result.returncode

                    capture = REPO_ROOT / "frontend" / "tools" / "capture_tooltip.js"
                    if not capture.exists():
                        print("Capture helper not found; commit completed.")
                        return 0
                    env = os.environ.copy()
                    env.setdefault("BACKEND", "http://127.0.0.1:8000")
                    env.setdefault("URL", "http://127.0.0.1:3000")
                    try:
                        p2 = subprocess.run(["node", str(capture)], capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
                        print("Capture stdout:\n", p2.stdout)
                        print("Capture stderr:\n", p2.stderr)
                        return p2.returncode or 0
                    except FileNotFoundError as exc:
                        print("Node executable not found; skipping capture:", exc)
                        return 0
            except Exception as exc:
                print("Error reading snapshot:", exc)
        time.sleep(2)
    print("Timed out waiting for parsed rows")
    return 1


if __name__ == "__main__":
    sys.exit(main())