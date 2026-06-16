#!/usr/bin/env python
"""CLI fallback for large-file backend imports.

Uses the same HTTP pipeline as the UI:
upload -> preview -> commit -> poll -> verify
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from pathlib import Path
from typing import Any

import requests


CLEAN_SCHEMA_CONFIRM_TOKEN = "CLEAN_NEO4J_SCHEMA"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def fail(message: str, *, details: Any | None = None, code: int = 1) -> int:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    print_json(payload)
    return code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backend import pipeline without the UI.")
    parser.add_argument("file_path", help="Absolute or relative path to the source file to import.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
    parser.add_argument("--clean-first", action="store_true", help="Clean Neo4j before import.")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--preview-timeout", type=int, default=300, help="Seconds to wait for preview readiness.")
    parser.add_argument("--commit-timeout", type=int, default=300, help="Seconds to wait for commit completion.")
    parser.add_argument("--request-timeout", type=int, default=300, help="Per-request timeout in seconds.")
    parser.add_argument("--skip-commit", action="store_true", help="Stop after preview and do not load to Neo4j.")
    return parser.parse_args()


def ensure_ok(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise RuntimeError(json.dumps(payload, indent=2))
    return payload


def clean_schema(session: requests.Session, base_url: str, timeout: int) -> None:
    last_error: Exception | None = None
    for path in ("/api/v1/admin/clean-schema", "/admin/clean-schema"):
        try:
            response = session.post(
                f"{base_url}{path}",
                json={"confirm": CLEAN_SCHEMA_CONFIRM_TOKEN},
                timeout=timeout,
            )
            payload = ensure_ok(response)
            print_json({"phase": "clean-schema", "endpoint": path, "result": payload})
            return
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error


def upload_file(session: requests.Session, base_url: str, file_path: Path, timeout: int) -> str:
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    with file_path.open("rb") as handle:
        response = session.post(
            f"{base_url}/api/v1/import/upload",
            files={"file": (file_path.name, handle, mime_type)},
            timeout=timeout,
        )
    payload = ensure_ok(response)
    task_id = payload.get("task_id")
    if not task_id:
        raise RuntimeError("Upload response did not include task_id.")
    print_json({"phase": "upload", "task_id": task_id, "response": payload})
    return str(task_id)


def poll_for_stage(
    session: requests.Session,
    base_url: str,
    task_id: str,
    *,
    poll_seconds: float,
    max_seconds: int,
    request_timeout: int,
    target_stage: str | None = None,
    min_progress: int | None = None,
    completed_only: bool = False,
) -> dict[str, Any]:
    started = time.time()
    while True:
        response = session.get(f"{base_url}/api/v1/import/status/{task_id}", timeout=request_timeout)
        payload = ensure_ok(response)

        if payload.get("status") == "failed":
            raise RuntimeError(json.dumps({"phase": "failed", "task_id": task_id, "status": payload}, indent=2))

        stage_ok = target_stage is None or payload.get("current_stage") == target_stage
        progress_ok = min_progress is None or int(payload.get("progress", 0) or 0) >= min_progress
        complete_ok = (not completed_only) or (payload.get("status") == "completed" and not payload.get("committing"))

        if stage_ok and progress_ok and complete_ok:
            return payload

        if (time.time() - started) > max_seconds:
            raise TimeoutError(
                f"Timed out waiting for task {task_id}: stage={target_stage!r}, "
                f"min_progress={min_progress!r}, completed_only={completed_only!r}"
            )

        time.sleep(poll_seconds)


def fetch_pre_commit(session: requests.Session, base_url: str, task_id: str, timeout: int) -> dict[str, Any]:
    response = session.get(f"{base_url}/api/v1/import/pre-commit/{task_id}", timeout=timeout)
    payload = ensure_ok(response)
    print_json({"phase": "pre-commit", "task_id": task_id, "preview": payload})
    return payload


def commit_import(session: requests.Session, base_url: str, task_id: str, timeout: int) -> dict[str, Any]:
    response = session.post(f"{base_url}/api/v1/import/commit/{task_id}", timeout=timeout)
    payload = ensure_ok(response)
    print_json({"phase": "commit-queued", "task_id": task_id, "commit": payload})
    return payload


def verify_import(task_id: str) -> dict[str, Any]:
    from backend.core.graph import query_with_timeout

    node_rows = query_with_timeout(
        "MATCH (n {import_id: $task_id}) RETURN count(n) AS c",
        {"task_id": task_id},
    ) or []
    rel_rows = query_with_timeout(
        "MATCH (a {import_id: $task_id})-[r]->(b {import_id: $task_id}) RETURN count(r) AS c",
        {"task_id": task_id},
    ) or []
    type_rows = query_with_timeout(
        "MATCH (a {import_id: $task_id})-[r]->(b {import_id: $task_id}) "
        "RETURN type(r) AS type, count(r) AS count ORDER BY count DESC LIMIT 20",
        {"task_id": task_id},
    ) or []
    return {
        "nodes": int((node_rows[0] or {}).get("c", 0)) if node_rows else 0,
        "relationships": int((rel_rows[0] or {}).get("c", 0)) if rel_rows else 0,
        "relationship_types": type_rows,
    }


def main() -> int:
    args = parse_args()
    file_path = Path(args.file_path).expanduser().resolve()
    if not file_path.exists():
        return fail(f"File not found: {file_path}")
    if not file_path.is_file():
        return fail(f"Path is not a file: {file_path}")

    session = requests.Session()
    base_url = args.base_url.rstrip("/")

    try:
        if args.clean_first:
            clean_schema(session, base_url, args.request_timeout)

        task_id = upload_file(session, base_url, file_path, args.request_timeout)
        preview_status = poll_for_stage(
            session,
            base_url,
            task_id,
            poll_seconds=args.poll_seconds,
            max_seconds=args.preview_timeout,
            request_timeout=args.request_timeout,
            target_stage="preview",
            min_progress=75,
        )
        print_json({"phase": "preview-status", "task_id": task_id, "status": preview_status})
        fetch_pre_commit(session, base_url, task_id, args.request_timeout)

        if args.skip_commit:
            print_json({"phase": "finished", "task_id": task_id, "mode": "preview-only"})
            return 0

        commit_import(session, base_url, task_id, args.request_timeout)
        completed_status = poll_for_stage(
            session,
            base_url,
            task_id,
            poll_seconds=args.poll_seconds,
            max_seconds=args.commit_timeout,
            request_timeout=args.request_timeout,
            completed_only=True,
        )
        print_json({"phase": "completed", "task_id": task_id, "status": completed_status})
        verification = verify_import(task_id)
        print_json({"phase": "verify", "task_id": task_id, "verification": verification})
        return 0
    except requests.HTTPError as exc:
        details = None
        try:
            details = exc.response.json()
        except Exception:
            details = exc.response.text if exc.response is not None else str(exc)
        return fail("HTTP request failed.", details=details)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
