"""Durable, content-free operational telemetry for agent and tool execution."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.mesh_store import PostgresRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentTelemetry:
    def __init__(self) -> None:
        self.store = PostgresRegistry("agentic_observability")

    def start(self, *, operation: str, request_id: str = "", session_id: str = "", workflow_id: str = "") -> tuple[dict[str, Any], float]:
        run_id = f"agent-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}"
        record = {
            "run_id": run_id,
            "operation": operation,
            "workflow_id": workflow_id,
            "request_id": str(request_id or ""),
            "session_id": str(session_id or ""),
            "status": "running",
            "started_at": _now(),
            "model": os.getenv("LLM_MODEL") or os.getenv("AZURE_OPENAI_DEPLOYMENT") or "deterministic",
            "prompt_version": os.getenv("AGENT_PROMPT_VERSION", "1"),
            "tool_spans": [],
            "evidence_count": 0,
        }
        self.store.put(run_id, record)
        return record, time.perf_counter()

    def tool_span(self, record: dict[str, Any], *, tool_id: str, attempt: int, status: str, duration_ms: float, error_type: str = "") -> None:
        record.setdefault("tool_spans", []).append({
            "tool_id": tool_id,
            "attempt": int(attempt),
            "status": status,
            "duration_ms": round(float(duration_ms), 2),
            "error_type": str(error_type or ""),
        })
        self.store.put(record["run_id"], record)

    def finish(self, record: dict[str, Any], started: float, *, status: str, evidence_count: int = 0, error_type: str = "") -> dict[str, Any]:
        record.update({
            "status": status,
            "finished_at": _now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "evidence_count": max(0, int(evidence_count)),
            "error_type": str(error_type or ""),
        })
        return self.store.put(record["run_id"], record)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.recent(limit)

    def summary(self, limit: int = 500) -> dict[str, Any]:
        runs = self.recent(limit)
        completed = [item for item in runs if item.get("status") == "completed"]
        failed = [item for item in runs if item.get("status") == "failed"]
        durations = [float(item.get("duration_ms") or 0) for item in runs if item.get("status") != "running"]
        tool_spans = [span for item in runs for span in item.get("tool_spans", [])]
        failure_rate = round(len(failed) / len(runs), 4) if runs else 0.0
        threshold = max(0.0, min(float(os.getenv("AGENT_FAILURE_RATE_ALERT_THRESHOLD", "0.2")), 1.0))
        stuck_seconds = max(60, int(os.getenv("AGENT_STUCK_RUN_SECONDS", "900")))
        now = datetime.now(timezone.utc)
        stuck = []
        for item in runs:
            if item.get("status") != "running":
                continue
            try:
                age = (now - datetime.fromisoformat(str(item.get("started_at")))).total_seconds()
            except (TypeError, ValueError):
                age = stuck_seconds + 1
            if age > stuck_seconds:
                stuck.append(item)
        alerts = []
        if runs and failure_rate >= threshold:
            alerts.append({"code": "AGENT_FAILURE_RATE_HIGH", "value": failure_rate, "threshold": threshold})
        if stuck:
            alerts.append({"code": "AGENT_RUN_STUCK", "count": len(stuck), "threshold_seconds": stuck_seconds})
        return {
            "status": "degraded" if alerts else "ok",
            "alerts": alerts,
            "window_limit": min(max(1, int(limit)), 1000),
            "runs": len(runs),
            "running": sum(1 for item in runs if item.get("status") == "running"),
            "completed": len(completed),
            "failed": len(failed),
            "failure_rate": failure_rate,
            "average_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "tool_calls": len(tool_spans),
            "tool_failures": sum(1 for span in tool_spans if span.get("status") == "failed"),
            "evidence_total": sum(int(item.get("evidence_count") or 0) for item in runs),
        }

    def prometheus(self) -> str:
        values = self.summary()
        lines = [
            "# HELP depo_agent_runs_total Agent runs in the bounded telemetry window.",
            "# TYPE depo_agent_runs_total gauge",
            f"depo_agent_runs_total {values['runs']}",
            "# TYPE depo_agent_failures_total gauge",
            f"depo_agent_failures_total {values['failed']}",
            "# TYPE depo_agent_failure_ratio gauge",
            f"depo_agent_failure_ratio {values['failure_rate']}",
            "# TYPE depo_agent_duration_milliseconds gauge",
            f"depo_agent_duration_milliseconds {values['average_duration_ms']}",
            "# TYPE depo_agent_tool_calls_total gauge",
            f"depo_agent_tool_calls_total {values['tool_calls']}",
            "# TYPE depo_agent_tool_failures_total gauge",
            f"depo_agent_tool_failures_total {values['tool_failures']}",
            "# TYPE depo_agent_evidence_total gauge",
            f"depo_agent_evidence_total {values['evidence_total']}",
        ]
        return "\n".join(lines) + "\n"


telemetry = AgentTelemetry()
