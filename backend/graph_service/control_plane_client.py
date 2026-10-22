"""Read-only adapters to data-job and data-product control-plane services.

GraphQL is a consumer surface: it never creates a Spark session, submits work,
or receives database credentials.  Job execution and publication remain behind
their dedicated, governed HTTP APIs.
"""
from __future__ import annotations

from backend.depo_platform.service_urls import service_url
from urllib.parse import quote

import httpx
from backend.depo_platform.peer_http import peer_response
from backend.depo_platform.network import service_bearer_headers


class ControlPlaneUnavailable(RuntimeError):
    """A configured peer control-plane service cannot be read."""


class ControlPlaneClient:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def _get(self, base_url: str, path: str) -> dict:
        try:
            endpoint = f"{base_url}{path}"
            response = peer_response('GET', endpoint, budget=self.timeout_seconds,
                headers=service_bearer_headers('GRAPH_READ_TOKEN', service_name='control-plane read', endpoint=endpoint))
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, RuntimeError, TimeoutError) as exc:
            raise ControlPlaneUnavailable("Control-plane read unavailable; verify peer readiness and read credentials") from exc
        if not isinstance(payload, dict):
            raise ControlPlaneUnavailable(f"Control-plane read returned an invalid response for {path}")
        return payload

    def job_runs(self, limit: int) -> dict:
        return self._get(
            service_url("DATA_PIPELINE_SERVICE_URL", "http://127.0.0.1:8019/api/v1"),
            f"/pipeline/jobs/runs?limit={max(1, min(limit, 1000))}",
        )

    def job_run(self, run_id: str) -> dict:
        return self._get(
            service_url("DATA_PIPELINE_SERVICE_URL", "http://127.0.0.1:8019/api/v1"),
            f"/pipeline/jobs/runs/{quote(run_id, safe='')}",
        )

    def data_products(self, limit: int = 100) -> dict:
        return self._get(
            service_url("DATA_PRODUCT_SERVICE_URL", "http://127.0.0.1:8017/api/v1"),
            f"/data-products?limit={max(1, min(int(limit), 500))}",
        )

    def data_product(self, product_version: str) -> dict:
        return self._get(
            service_url("DATA_PRODUCT_SERVICE_URL", "http://127.0.0.1:8017/api/v1"),
            f"/data-products/{quote(product_version, safe=':')}",
        )

    def data_product_manifest(self, product_version: str) -> dict:
        return self._get(
            service_url("DATA_PRODUCT_SERVICE_URL", "http://127.0.0.1:8017/api/v1"),
            f"/data-products/{quote(product_version, safe=':')}/manifest",
        )


control_plane_client = ControlPlaneClient()
