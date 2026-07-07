#!/usr/bin/env python3
"""Upload an XSD through the import pipeline, poll status, commit, and print outputs.

Usage:
  python tools/import/auto_import_xsd.py [path/to/file.xsd] [backend_url] [ontology_mapping]

Environment:
  BACKEND=http://127.0.0.1:8000
  ONTOLOGY_MAPPING=<optional legacy seed profile>
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO_ROOT / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd"
DEFAULT_BACKEND = "http://127.0.0.1:8000"


def _request_json(method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
    response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response.json()


def upload_file(file_path: Path, backend: str, ontology_mapping: str = "") -> Dict[str, Any]:
    url = f"{backend.rstrip('/')}/api/v1/import/upload"
    print(f"Uploading {file_path} to {url}")
    with file_path.open("rb") as fh:
        files = {"file": (file_path.name, fh, "application/xml")}
        data = {"ontology_mapping": ontology_mapping}
        return _request_json("POST", url, files=files, data=data, timeout=120)


def poll_status(task_id: str, backend: str, timeout: int = 900, interval: int = 4) -> Dict[str, Any]:
    url = f"{backend.rstrip('/')}/api/v1/import/status/{task_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            payload = _request_json("GET", url, timeout=15)
            status = payload.get("status") or payload.get("current_stage") or payload.get("task", {}).get("status")
            print("Status:", status)
            if status in {"completed", "failed", "committed"}:
                return payload
        except Exception as exc:
            print("Status poll error:", exc)
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for import task {task_id}")


def pre_commit_check(task_id: str, backend: str) -> Optional[Dict[str, Any]]:
    try:
        return _request_json("GET", f"{backend.rstrip('/')}/api/v1/import/pre-commit/{task_id}", timeout=30)
    except Exception as exc:
        print("Pre-commit check failed:", exc)
        return None


def commit_with_retries(task_id: str, backend: str, attempts: int = 5) -> Dict[str, Any]:
    delays = [5, 10, 20, 30, 60]
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            print(f"Commit attempt {attempt}/{attempts} for {task_id}")
            return _request_json("POST", f"{backend.rstrip('/')}/api/v1/import/commit/{task_id}", timeout=300)
        except Exception as exc:
            last_error = exc
            print("Commit attempt failed:", exc)
            if attempt < attempts:
                time.sleep(delays[min(attempt - 1, len(delays) - 1)])
    raise RuntimeError(f"Commit failed after {attempts} attempts: {last_error}")


def find_generated_ontology_files() -> list[str]:
    candidates = [
        REPO_ROOT / "frontend" / "public" / "Ontology",
        REPO_ROOT / "requirements" / "output" / "ontologies",
        REPO_ROOT / "data" / "parser_outputs",
    ]
    files: list[Path] = []
    for folder in candidates:
        if folder.exists():
            files.extend(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in {".owl", ".rdf", ".ttl"})
    return [str(path) for path in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)]


def main() -> int:
    file_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    backend = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BACKEND", DEFAULT_BACKEND)
    ontology_mapping = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("ONTOLOGY_MAPPING", "")

    if not file_path.is_absolute():
        file_path = REPO_ROOT / file_path
    if not file_path.exists():
        print("File not found:", file_path)
        return 2

    try:
        upload = upload_file(file_path, backend, ontology_mapping)
        task_id = upload.get("task_id") or upload.get("task") or upload.get("taskId")
        if not task_id:
            print("Upload response did not include a task id:", upload)
            return 3
        print("Upload started, task_id=", task_id)
        print("Final status object:", poll_status(task_id, backend))
        pre_commit = pre_commit_check(task_id, backend)
        if pre_commit is not None:
            print("Pre-commit check:", pre_commit)
        print("Commit response:", commit_with_retries(task_id, backend))
    except Exception as exc:
        print("Import failed:", exc)
        return 4

    generated = find_generated_ontology_files()
    if generated:
        print("Generated ontology files (most recent first):")
        for item in generated[:10]:
            print(" -", item)
    else:
        print("No generated ontology files found")
    return 0


if __name__ == "__main__":
    sys.exit(main())