#!/usr/bin/env python3
"""Run pre-commit and commit for an import task.

Usage:
  python tools/import/run_commit.py <task_id> [backend_url]
"""
from __future__ import annotations

import os
import sys

import requests


def call_pre_commit(task_id: str, backend: str) -> bool:
    url = f"{backend.rstrip('/')}/api/v1/import/pre-commit/{task_id}"
    try:
        response = requests.get(url, timeout=30)
        print("PRE-COMMIT", response.status_code)
        print(response.text)
        return response.ok
    except Exception as exc:
        print("PRE-COMMIT ERROR", exc)
        return False


def call_commit(task_id: str, backend: str) -> bool:
    url = f"{backend.rstrip('/')}/api/v1/import/commit/{task_id}"
    try:
        response = requests.post(url, timeout=300)
        print("COMMIT", response.status_code)
        print(response.text)
        return response.ok
    except Exception as exc:
        print("COMMIT ERROR", exc)
        return False


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_commit.py <task_id> [backend_url]")
        return 2
    task_id = sys.argv[1]
    backend = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BACKEND", "http://127.0.0.1:8000")
    pre_ok = call_pre_commit(task_id, backend)
    commit_ok = call_commit(task_id, backend)
    return 0 if pre_ok and commit_ok else 1


if __name__ == "__main__":
    sys.exit(main())