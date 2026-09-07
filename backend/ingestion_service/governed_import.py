"""Profile-routed, governed source import boundary.

Raw engineering files are retained once, normalized only by a declared
adapter, then submitted to an already approved pipeline job.  This service
never publishes graph data and never creates or approves a job definition.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from backend.artifact_store import ArtifactStore
from backend.ceim.ap242_adapter import ap242_to_ceim_batch
from backend.ceim.contract import contract
from backend.ceim.plmxml_adapter import plmxml_to_ceim_batch
from backend.ceim.qif_adapter import qif_to_ceim_batch
from backend.ceim.reqif_adapter import reqif_to_ceim_batch
from backend.ceim.mbse_adapter import mbse_to_ceim_batch


def profile_for_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    profiles = {
        ".stp": "ap242-step-mbd", ".step": "ap242-step-mbd", ".stpx": "ap242-step-mbd",
        ".reqif": "reqif", ".qif": "qif", ".plmxml": "plmxml",
        ".xmi": "sysml-v1",
    }
    if suffix not in profiles:
        raise ValueError("No governed instance profile is registered for this extension; select a declared source profile for XML, JSON, XMI, XSD, or EXPRESS")
    return profiles[suffix]


class GovernedImportService:
    def __init__(self) -> None:
        self.pipeline_url = os.getenv("DATA_PIPELINE_SERVICE_URL", "http://127.0.0.1:8019/api/v1").rstrip("/")
        self.timeout = float(os.getenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "90"))

    def normalize(self, *, filename: str, content: bytes, profile: str = "auto", source_system: str = "") -> dict[str, Any]:
        if not content:
            raise ValueError("Source content is empty")
        selected = profile_for_filename(filename) if profile in {"", "auto"} else profile.strip().lower()
        adapters = {
            "sysml-v1": lambda: mbse_to_ceim_batch(content, version="1"),
            "sysml-v2": lambda: mbse_to_ceim_batch(content, version="2"),
            "ap242-step-mbd": lambda: ap242_to_ceim_batch(content, filename=filename),
            "reqif": lambda: reqif_to_ceim_batch(content),
            "qif": lambda: qif_to_ceim_batch(content),
            "plmxml": lambda: plmxml_to_ceim_batch(content),
        }
        adapter = adapters.get(selected)
        if adapter is None:
            raise ValueError("The selected profile is not a governed instance profile")
        batch = adapter()
        source = ArtifactStore().ingest_bytes(
            content, filename=filename, kind=f"source-{batch['standard']}",
            media_type="application/json" if selected == "sysml-v2" else "application/xml", provenance={"profile": selected, "source_system": source_system},
        )
        return {
            **batch, "profile": selected, "source_artifact_id": source["artifact_id"],
            "source_system": source_system or None,
        }

    async def run_job(
        self, *, filename: str, content: bytes, job_id: str, job_version: str,
        profile: str = "auto", source_system: str = "", request_id: str = "",
    ) -> dict[str, Any]:
        normalized = self.normalize(filename=filename, content=content, profile=profile, source_system=source_system)
        payload = {
            "standard": normalized["standard"], "representation": "normalized-ceim-v1",
            "ceim_version": normalized.get("ceim_version", contract.version), "entities": normalized["entities"],
            "relationships": normalized["relationships"], "artifact_ids": [normalized["source_artifact_id"]],
            "source_system": source_system or None,
        }
        # A secured deployment must not rely on the caller's browser context
        # reaching an internal service.  The ingestion service uses its scoped
        # execution credential; local disabled-auth remains loopback-only in
        # the data-pipeline service.
        headers = {"X-Request-ID": request_id} if request_id else {}
        execution_token = os.getenv("DATA_PIPELINE_SERVICE_TOKEN", "").strip()
        if execution_token:
            headers["Authorization"] = f"Bearer {execution_token}"
        payload["approved_by"] = os.getenv("DATA_PIPELINE_SERVICE_ACTOR", "governed-ingestion-service")
        payload["approval_token"] = os.getenv("DATA_JOB_EXECUTION_TOKEN", execution_token)
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            response = await client.post(f"{self.pipeline_url}/pipeline/jobs/definitions/{job_id}/{job_version}/run", json=payload)
        if response.status_code == 404:
            raise ValueError(f"Configured job {job_id}:{job_version} was not found; create and approve it before importing")
        if response.status_code == 409:
            raise ValueError(f"Configured job {job_id}:{job_version} is not approved and enabled")
        if response.is_error:
            raise RuntimeError(f"Data pipeline returned HTTP {response.status_code}: {response.text[:500]}")
        result = response.json()
        preview_ids = {e["id"] for e in normalized["entities"][:2000]}
        return {"status": result.get("status", "completed"), "profile": normalized["profile"], "standard": normalized["standard"],
                "source_artifact_id": normalized["source_artifact_id"], "source_summary": normalized["source_summary"],
                "data_job": result.get("configured_job"), "run_manifest": result.get("run_manifest"),
                "validation": result.get("validation"), "mapping": result.get("mapping"),
                "preview": {"entities": normalized["entities"][:2000],
                            "relationships": [r for r in normalized["relationships"] if r.get("source_id") in preview_ids and r.get("target_id") in preview_ids][:10000]},
                "preview_scope": "bounded source normalization, not publication evidence"}


governed_import = GovernedImportService()
