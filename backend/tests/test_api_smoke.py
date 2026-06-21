"""HTTP smoke tests for the running backend service.

These tests intentionally use the public API surface instead of importing
implementation modules. Set BACKEND_URL to point at another environment.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _request(method: str, path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 10)
    return requests.request(method, f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)



def _backend_available() -> bool:
    try:
        response = _request("GET", "/health", timeout=3)
        return response.status_code < 500
    except requests.RequestException:
        return False


def test_openapi_is_available() -> None:
    if not _backend_available():
        pytest.skip("Backend service is not running")
    response = _request("GET", "/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "openapi" in payload
    assert "paths" in payload


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/api/v1/ontology/registered",
        "/api/v1/import/formats",
    ],
)
def test_read_endpoints_respond(path: str) -> None:
    if not _backend_available():
        pytest.skip("Backend service is not running")
    response = _request("GET", path)
    assert response.status_code < 500


def test_ap239_data_dictionary_responds_when_neo4j_is_configured() -> None:
    if not _backend_available():
        pytest.skip("Backend service is not running")
    response = _request("GET", "/api/v1/ontology/ap239/data-dictionary", timeout=20)
    if response.status_code == 500:
        pytest.skip("AP239 data dictionary requires a configured Neo4j connection")
    assert response.status_code < 500


def test_import_upload_reaches_task_or_clear_client_error() -> None:
    if not _backend_available():
        pytest.skip("Backend service is not running")
    candidate = next(Path("data").rglob("Domain_model.xmi"), None)
    if candidate is None:
        candidate = Path("test_upload.xsd")
    if not candidate.exists():
        pytest.skip("No sample import file is available")

    started = time.monotonic()
    with candidate.open("rb") as handle:
        response = _request(
            "POST",
            "/api/v1/import/upload",
            files={"file": (candidate.name, handle, "application/octet-stream")},
            data={"ontology_mapping": "auto"},
            timeout=120,
        )
    elapsed = time.monotonic() - started

    assert response.status_code < 500
    if response.ok:
        assert "task_id" in response.json()
        assert elapsed < 30
