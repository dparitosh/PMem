"""Durable Windows-compatible DEPO data-pipeline execution worker."""
from __future__ import annotations

import os
from backend.depo_platform.network import bounded_timeout_seconds
import logging
import signal
import threading

from . import job_definitions, run_records, worker_status
from .execution import execute_claimed_job
from .runner import runner


def run() -> None:
    worker_id = run_records.worker_identity()
    lease_seconds = int(bounded_timeout_seconds('DEPO_PIPELINE_LEASE_SECONDS', default=300, minimum=30))
    poll_seconds = int(bounded_timeout_seconds('DEPO_PIPELINE_POLL_SECONDS', default=5, maximum=60))
    stop = threading.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(event, lambda *_: stop.set())
        except (ValueError, OSError):
            pass
    registered = False
    while not stop.is_set():
        try:
            if not registered:
                worker_status.put(worker_id, status="idle", execution_mode="native-windows-worker")
                registered = True
            record = run_records.claim_next(worker_id=worker_id, lease_seconds=lease_seconds)
        except Exception as exc:
            logging.getLogger(__name__).warning("Pipeline control plane unavailable: %s", type(exc).__name__)
            stop.wait(poll_seconds)
            continue
        try:
            worker_status.put(worker_id, status="busy" if record else "idle",
                              run_id=record["run_id"] if record else None, spark=runner.health())
        except Exception as exc:
            logging.getLogger(__name__).warning("Worker telemetry deferred: %s", type(exc).__name__)
        if not record:
            stop.wait(poll_seconds)
            continue
        heartbeat_stop = threading.Event()
        lease_lost = threading.Event()
        lease_record = [record]
        def renew_lease() -> None:
            stale_seconds = int(bounded_timeout_seconds('DEPO_PIPELINE_WORKER_STALE_SECONDS', default=60, minimum=30))
            while not heartbeat_stop.wait(min(max(1, lease_seconds // 3), stale_seconds / 3)):
                try:
                    lease_record[0] = run_records.heartbeat(lease_record[0], worker_id=worker_id, lease_seconds=lease_seconds)
                except Exception:
                    lease_lost.set()
                    heartbeat_stop.set()
                    return
                try:
                    worker_status.put(worker_id, status="busy", run_id=record["run_id"], spark=runner.health())
                except Exception as exc:
                    logging.getLogger(__name__).warning("Worker telemetry deferred: %s", type(exc).__name__)
        heartbeat_thread = threading.Thread(target=renew_lease, name="depo-pipeline-lease-heartbeat", daemon=True)
        heartbeat_thread.start()
        definition = None
        try:
            definition = job_definitions.get(record["job_id"], record["job_version"])
            if not definition or definition.get("lifecycle_state") != "approved" or not definition.get("enabled"):
                run_records.failed(record, "Job definition is missing, disabled, or no longer approved")
                continue
            retry = definition.get("retry_policy") or {"max_attempts": 1}
            if int(record.get("attempt") or 1) > int(retry.get("max_attempts") or 1):
                run_records.failed(record, "Retry limit exhausted after abandoned execution; inspect retained evidence before explicit replay")
                continue
            payload = run_records.replay_payload(record)
            execute_claimed_job(definition, payload, record, lease_lost=lease_lost)
        except Exception as exc:
            try:
                current_record = run_records.get(record["run_id"])
            except Exception as lookup_error:
                logging.getLogger(__name__).warning("Run recovery deferred: %s", type(lookup_error).__name__)
                current_record = None
            if (current_record and current_record.get("status") == "running"
                    and current_record.get("worker_id") == worker_id
                    and current_record.get("attempt") == record.get("attempt")):
                retry = (definition if 'definition' in locals() and definition else {}).get("retry_policy") or {"max_attempts": 1, "backoff_seconds": 30}
                if int(current_record.get("attempt") or 1) < int(retry.get("max_attempts") or 1):
                    try:
                        run_records.requeue(current_record, message=str(exc), backoff_seconds=int(retry.get("backoff_seconds") or 30))
                    except Exception as recovery_error:
                        logging.getLogger(__name__).warning("Run requeue deferred: %s", type(recovery_error).__name__)
                else:
                    try:
                        run_records.failed(current_record, str(exc))
                    except Exception as recovery_error:
                        logging.getLogger(__name__).warning("Run failure recording deferred: %s", type(recovery_error).__name__)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=5)
            try:
                worker_status.put(worker_id, status="idle", run_id=None, spark=runner.health())
            except Exception as status_error:
                logging.getLogger(__name__).warning("Worker status deferred: %s", type(status_error).__name__)
    runner.shutdown()
    try:
        worker_status.put(worker_id, status="stopped", run_id=None, spark=runner.health())
    except Exception as exc:
        logging.getLogger(__name__).warning("Worker shutdown telemetry deferred: %s", type(exc).__name__)


if __name__ == "__main__":
    run()
