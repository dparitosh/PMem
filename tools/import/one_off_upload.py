#!/usr/bin/env python3
"""Upload a single XSD/XML file to the import API.

Usage:
  python tools/import/one_off_upload.py [file] [backend_url] [ontology_mapping]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO_ROOT / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    if not path.is_absolute():
        path = REPO_ROOT / path
    backend = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BACKEND", "http://127.0.0.1:8000")
    ontology_mapping = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("ONTOLOGY_MAPPING", "AP242")
    if not path.exists():
        print("File missing:", path)
        return 2

    url = f"{backend.rstrip('/')}/api/v1/import/upload"
    with path.open("rb") as fh:
        files = {"file": (path.name, fh, "application/xml")}
        data = {"ontology_mapping": ontology_mapping}
        response = requests.post(url, files=files, data=data, timeout=300)
    print("STATUS", response.status_code)
    print(response.text)
    return 0 if response.ok else 1


if __name__ == "__main__":
    sys.exit(main())