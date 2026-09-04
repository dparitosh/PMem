"""Opt-in supervisor for replayable, configured data-processing jobs.

It never embeds source payloads in definitions.  A scheduled run reuses a
retained immutable input from a prior governed run and delegates execution to
the same bounded job dispatcher used by the OpenAPI route.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from . import job_definitions, run_records


class ScheduledJobSupervisor:
    def __init__(self, execute: Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any]]) -> None:
        self._execute = execute
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error = ""
        self._runs_started = 0

    @staticmethod
    def _enabled() -> bool:
        return os.getenv("DEPO_PIPELINE_SCHEDULER_ENABLED", "false").strip().lower() == "true"

    @staticmethod
    def _seconds_since(value: str | None) -> float:
        if not value:
            return float("inf")
        try:
            return max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds())
        except ValueError:
            return float("inf")

    def health(self) -> dict[str, Any]:
        return {"enabled": self._enabled(), "running": bool(self._thread and self._thread.is_alive()), "runs_started": self._runs_started, "last_error": self._last_error or None}

    def start(self) -> None:
        if not self._enabled() or self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="depo-data-job-supervisor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(10):
            try:
                self.scan_once()
            except Exception as exc:  # supervisor must not take down the API
                self._last_error = str(exc)

    def scan_once(self) -> None:
        for definition in job_definitions.all_definitions():
            schedule = definition.get("schedule") or {}
            if definition.get("lifecycle_state") != "approved" or not definition.get("enabled") or not schedule:
                continue
            lock_key = f"scheduled:{definition['job_id']}:{definition['version']}"
            with job_definitions.store.advisory_lock(lock_key) as acquired:
                if not acquired:
                    continue
                prior = run_records.get(str(schedule.get("replay_run_id") or ""))
                if not prior or prior.get("job_id") != definition["job_id"] or prior.get("job_version") != definition["version"]:
                    self._last_error = f"Scheduled job {definition['job_id']} has no compatible replay input"
                    continue
                latest = next((run for run in run_records.list_runs(limit=1000) if run.get("job_id") == definition["job_id"] and run.get("job_version") == definition["version"]), None)
                if latest and self._seconds_since(latest.get("started_at")) < int(schedule["interval_seconds"]):
                    continue
                payload = {**run_records.replay_payload(prior), "execution_actor": "pipeline-scheduler"}
                retry = definition.get("retry_policy") or {"max_attempts": 1, "backoff_seconds": 30}
                for attempt in range(int(retry["max_attempts"])):
                    try:
                        self._execute(definition, payload, f"scheduled:{definition['job_id']}:{int(time.time())}")
                        self._runs_started += 1
                        self._last_error = ""
                        break
                    except Exception as exc:
                        self._last_error = f"{definition['job_id']} attempt {attempt + 1}: {exc}"
                        if attempt + 1 < int(retry["max_attempts"]):
                            self._stop.wait(int(retry["backoff_seconds"]))
