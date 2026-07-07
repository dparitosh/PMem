#!/usr/bin/env python3
"""Inspect a persisted import task snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check_snapshot.py <task_id|snapshot_file>")
        return 2
    token = sys.argv[1]
    snapshot = Path(token)
    if not snapshot.is_absolute():
        name = token if token.endswith(".json") else f"{token}.json"
        snapshot = REPO_ROOT / "uploads" / ".import_tasks" / name
    try:
        stat = snapshot.stat()
        print("path:", snapshot)
        print("size:", stat.st_size)
        print("mtime:", stat.st_mtime)
        text = snapshot.read_text(encoding="utf-8")
        print("preview of file (first 1000 chars):")
        print(text[:1000])
        data = json.loads(text)
        print("keys:", list(data.keys()))
        print("parsed_rows present?:", "parsed_rows" in data)
        if "parsed_rows" in data:
            value = data["parsed_rows"]
            print("parsed_rows type:", type(value), "len:", (len(value) if hasattr(value, "__len__") else "N/A"))
        return 0
    except Exception as exc:
        print("error reading", snapshot, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())