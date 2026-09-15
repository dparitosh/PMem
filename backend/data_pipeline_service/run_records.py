"""Durable run manifests for configured data jobs.

The registry retains hashes and reproducibility metadata, never arbitrary user
payloads. Source bytes remain the responsibility of the immutable artifact
store and are referenced by artifact id in production job definitions.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry


store = PostgresRegistry("data_job_runs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _input_count(payload: dict[str, Any]) -> int:
    if payload.get("artifact_id"):
        return 1
    if isinstance(payload.get("documents"), list):
        return len(payload["documents"])
    if isinstance(payload.get("records"), list):
        return len(payload["records"])
    return len(list(payload.get("entities") or [])) + len(list(payload.get("relationships") or []))


def start(definition: dict[str, Any], payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    checkpoint = payload.get("checkpoint")
    if checkpoint is not None and not isinstance(checkpoint, dict):
        raise ValueError("checkpoint must be an object when supplied")
    next_checkpoint = payload.get("next_checkpoint")
    if next_checkpoint is not None and not isinstance(next_checkpoint, dict):
        raise ValueError("next_checkpoint must be an object when supplied")
    raw_payload = dict(payload)
    replay_of = str(raw_payload.pop("replay_of", "") or "") or None
    executed_by = str(raw_payload.pop("execution_actor", "") or "") or None
    source_standard = str(payload.get("standard") or payload.get("source_standard") or "").strip().lower() or None
    if source_standard is None:
        records = payload.get("records")
        if isinstance(records, list):
            standards = {
                str(item.get("source_standard") or "").strip().lower()
                for item in records if isinstance(item, dict) and item.get("source_standard")
            }
            # A mixed-standard batch must remain visibly mixed instead of being
            # mislabeled as whichever record happened to be first.
            if len(standards) == 1:
                source_standard = standards.pop()
    source_system = str(payload.get("source_system") or "").strip() or None
    supplied_artifact_ids = payload.get("artifact_ids") or []
    if not isinstance(supplied_artifact_ids, list) or any(not isinstance(item, str) or not item.strip() for item in supplied_artifact_ids):
        raise ValueError("artifact_ids must be a list of non-empty artifact identifiers")
    raw_artifact = ArtifactStore().ingest_bytes(
        json.dumps(raw_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"),
        filename=f"{definition['job_id']}-{definition['version']}-input.json",
        kind="data-job-input",
        media_type="application/json",
        provenance={"job_id": definition["job_id"], "job_version": definition["version"], "correlation_id": correlation_id},
    )
    record = {
        "run_id": run_id,
        "job_id": definition["job_id"],
        "job_version": definition["version"],
        "job_type": definition["job_type"],
        "quality_profile": definition.get("quality_profile"),
        "quality_profile": definition.get("quality_profile"),
        "status": "running",
        "correlation_id": correlation_id,
        "replay_of": replay_of,
        "executed_by": executed_by,
        "source_standard": source_standard,
        "source_system": source_system,
        "started_at": _now(),
        "input_manifest": {
            "contract": definition["input_contract"],
            "payload_digest": _digest(raw_payload),
            "record_count": _input_count(payload),
            "artifact_ids": sorted(set([*supplied_artifact_ids, raw_artifact["artifact_id"]])),
            "raw_payload_artifact_id": raw_artifact["artifact_id"],
        },
        "checkpoint": checkpoint,
        "output_manifest": None,
    }
    return store.put(run_id, record)


def replay_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Load the exact retained input used by a prior run for deterministic replay."""
    artifact_id = str((record.get("input_manifest") or {}).get("raw_payload_artifact_id") or "")
    if not artifact_id:
        raise ValueError("Run does not retain a replayable input artifact")
    _, path = ArtifactStore().resolve(artifact_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Retained run input is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError("Retained run input must be an object")
    return {**payload, "replay_of": record["run_id"]}


def complete(record: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    result_artifact = ArtifactStore().ingest_bytes(
        json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"),
        filename=f"{record['job_id']}-{record['job_version']}-{record['run_id']}-result.json",
        kind="data-job-output",
        media_type="application/json",
        provenance={"run_id": record["run_id"], "job_id": record["job_id"], "job_version": record["job_version"], "correlation_id": record.get("correlation_id")},
    )
    contracts = {
        "normalize-ceim": "normalized-ceim-batch-v1",
        "data-quality-assessment": "data-quality-report-v1",
        "schema-analytics-product": "schema-analytics-data-product-draft-v1",
        "validate-semantic-batch": "semantic-validation-report-v1",
        "normalize-unstructured-ceim": "semantic-validation-report-v1",
        "validate-unstructured-evidence": "validated-unstructured-evidence-v1",
        "enrich-document-evidence": "document-graph-proposal-v1",
        "rdf-quality-statistics": "rdf-quality-report-v1",
        "rdf-deduplicate-serialize": "canonical-ntriples-v1",
    }
    output = {
        "contract": contracts.get(record["job_type"], "quality-summary-v1"),
        "result_digest": _digest(result),
        "result_artifact_id": result_artifact["artifact_id"],
        "counts": dict(result.get("counts") or result.get("quality") or {}),
        "partition_artifacts": dict(result.get("partition_artifacts") or {}),
    }
    source_standard = result.get("standard") or record.get("source_standard")
    if source_standard:
        output["source_standard"] = str(source_standard)
    if record.get("source_system"):
        output["source_system"] = record["source_system"]
    if result.get("mapping"):
        output["mapping_digest"] = result["mapping"]
    if isinstance(result.get("validation"), dict):
        output["validation_status"] = "conforms" if result["validation"].get("conforms") else "nonconformant"
    if isinstance(result.get("data_product_draft"), dict):
        draft = result["data_product_draft"]
        output["data_product_draft"] = {
            "contract": draft.get("contract"), "name": draft.get("name"),
            "artifacts": list(draft.get("artifacts") or []),
            "quality_status": draft.get("quality_status"),
            "publication_requirements": list(draft.get("publication_requirements") or []),
        }
    retained_payload = replay_payload(record)
    next_checkpoint = retained_payload.get("next_checkpoint")
    if next_checkpoint is not None:
        output["checkpoint_candidate"] = next_checkpoint
        output["checkpoint_state"] = "awaiting_approved_publication"
    completed = {**record, "status": result.get("status", "completed"), "completed_at": _now(), "output_manifest": output}
    return store.put(record["run_id"], completed)


def failed(record: dict[str, Any], message: str) -> dict[str, Any]:
    return store.put(record["run_id"], {**record, "status": "failed", "completed_at": _now(), "failure": {"message": message}})


def publication_succeeded(record: dict[str, Any], publication: dict[str, Any]) -> dict[str, Any]:
    """Advance a candidate checkpoint only after canonical publication succeeds."""
    output = dict(record.get("output_manifest") or {})
    if output.get("checkpoint_state") == "advanced":
        return record
    candidate = output.get("checkpoint_candidate")
    if candidate is None:
        raise ValueError("Run does not contain a checkpoint candidate")
    if publication.get("status") != "published":
        raise ValueError("Canonical publication did not report success")
    advanced_at = _now()
    output.update({
        "checkpoint_state": "advanced",
        "checkpoint_advanced_at": advanced_at,
        "publication_digest": _digest(publication),
        "publication": publication,
    })
    return store.put(record["run_id"], {
        **record, "checkpoint": candidate, "checkpoint_advanced_at": advanced_at,
        "output_manifest": output,
    })


def get(run_id: str) -> dict[str, Any] | None:
    return store.get(run_id)


def list_runs(*, limit: int = 100) -> list[dict[str, Any]]:
    records = sorted(store.all().values(), key=lambda item: item.get("started_at", ""), reverse=True)
    return records[:max(1, min(limit, 1000))]


def telemetry_summary(*, limit: int = 100) -> dict[str, Any]:
    """Return UI-ready, durable evidence for data-processing job telemetry.

    This intentionally reports job execution and data-quality outcomes only.
    It is not browser or application usage telemetry, and it never exposes an
    artifact payload or grants publication authority.
    """
    runs = list_runs(limit=limit)

    def count(record: dict[str, Any], *names: str) -> int:
        values = (record.get("output_manifest") or {}).get("counts") or {}
        return next((int(values[name]) for name in names if values.get(name) is not None), 0)

    return {
        "scope": "recent_runs",
        "limit": limit,
        "scope": "recent_runs",
        "limit": limit,
        "runs": len(runs),
        "completed_runs": sum(1 for run in runs if run.get("status") == "completed"),
        "failed_runs": sum(1 for run in runs if run.get("status") == "failed"),
        "records_input": sum(int((run.get("input_manifest") or {}).get("record_count") or 0) for run in runs),
        "records_accepted": sum(count(run, "accepted_records", "records_accepted", "normalized_entities", "accepted_documents", "valid_ntriples") for run in runs),
        "records_rejected": sum(count(run, "rejected_records", "records_rejected", "rejected_documents", "malformed_lines") for run in runs),
        "runs_with_checkpoint": sum(1 for run in runs if run.get("checkpoint") is not None),
        "runs_with_lineage": sum(1 for run in runs if run.get("correlation_id")),
        "recent_runs": runs,
    }
