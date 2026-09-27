"""Durable Windows-compatible DEPO data-pipeline execution worker."""
from __future__ import annotations

import os
import signal
import threading

from . import job_definitions, run_records, worker_status
from .router import execute_claimed_job, runner


def run() -> None:
    worker_id = run_records.worker_identity()
    lease_seconds = max(30, min(int(os.getenv("DEPO_PIPELINE_LEASE_SECONDS", "300")), 3600))
    poll_seconds = max(1, min(int(os.getenv("DEPO_PIPELINE_POLL_SECONDS", "5")), 60))
    stop = threading.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(event, lambda *_: stop.set())
        except (ValueError, OSError):
            pass
    worker_status.put(worker_id, status="idle", execution_mode="native-windows-worker")
    while not stop.is_set():
        record = run_records.claim_next(worker_id=worker_id, lease_seconds=lease_seconds)
        if not record:
            worker_status.put(worker_id, status="idle", spark=runner.health())
            stop.wait(poll_seconds)
            continue
        worker_status.put(worker_id, status="busy", run_id=record["run_id"], spark=runner.health())
        heartbeat_stop = threading.Event()
        lease_record = [record]
        def renew_lease() -> None:
            while not heartbeat_stop.wait(max(10, lease_seconds // 3)):
                try:
                    lease_record[0] = run_records.heartbeat(lease_record[0], worker_id=worker_id, lease_seconds=lease_seconds)
                    worker_status.put(worker_id, status="busy", run_id=record["run_id"], spark=runner.health())
                except Exception:
                    heartbeat_stop.set()
        heartbeat_thread = threading.Thread(target=renew_lease, name="depo-pipeline-lease-heartbeat", daemon=True)
        heartbeat_thread.start()
        definition = None
        try:
            definition = job_definitions.get(record["job_id"], record["job_version"])
            if not definition or definition.get("lifecycle_state") != "approved" or not definition.get("enabled"):
                run_records.failed(record, "Job definition is missing, disabled, or no longer approved")
                continue
            payload = run_records.replay_payload(record)
            execute_claimed_job(definition, payload, record)
        except Exception as exc:
            current_record = run_records.get(record["run_id"])
            if current_record and current_record.get("status") == "running":
                retry = (definition if 'definition' in locals() and definition else {}).get("retry_policy") or {"max_attempts": 1, "backoff_seconds": 30}
                if int(current_record.get("attempt") or 1) < int(retry.get("max_attempts") or 1):
                    run_records.requeue(current_record, message=str(exc), backoff_seconds=int(retry.get("backoff_seconds") or 30))
                else:
                    run_records.failed(current_record, str(exc))
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=5)
            worker_status.put(worker_id, status="idle", run_id=None, spark=runner.health())
    runner.shutdown()
    worker_status.put(worker_id, status="stopped", run_id=None, spark=runner.health())


if __name__ == "__main__":
    run()
