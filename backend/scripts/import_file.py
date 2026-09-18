#!/usr/bin/env python
"""Submit one engineering source file through the governed ingestion boundary.

This command deliberately stops before graph publication. It invokes the same
approved data-job path used by the Import UI and prints its durable run receipt.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit an engineering file to governed ingestion.")
    parser.add_argument("file_path", help="Source STEP, ReqIF, QIF, PLMXML, XML, JSON, or schema file.")
    parser.add_argument(
        "--base-url", default=os.getenv("IMPORT_SERVICE_URL", "http://127.0.0.1:8014"),
        help="Ingestion service root; defaults to IMPORT_SERVICE_URL or local port 8014.",
    )
    parser.add_argument("--profile", default="auto", help="Configured source profile, or auto.")
    parser.add_argument("--job-id", default="semantic-source-validation", help="Approved data-job identifier.")
    parser.add_argument("--job-version", default="1.0.0", help="Approved data-job semantic version.")
    parser.add_argument("--source-system", default="", help="Optional source-system provenance value.")
    parser.add_argument("--request-timeout", type=int, default=300, help="Request timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.file_path).expanduser().resolve()
    if not source.is_file():
        print(json.dumps({"status": "error", "message": f"File not found: {source}"}, indent=2))
        return 2
    mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    try:
        with source.open("rb") as handle:
            response = requests.post(
                f"{args.base_url.rstrip('/')}/api/v1/governed-import",
                files={"file": (source.name, handle, mime_type)},
                data={
                    "profile": args.profile,
                    "job_id": args.job_id,
                    "job_version": args.job_version,
                    "source_system": args.source_system,
                },
                timeout=max(1, args.request_timeout),
            )
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2, default=str))
        return 0
    except requests.RequestException as exc:
        detail = exc.response.text if getattr(exc, "response", None) is not None else str(exc)
        print(json.dumps({"status": "error", "message": "Governed import failed", "detail": detail}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
