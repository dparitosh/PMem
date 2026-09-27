from backend.agentic_service.telemetry import AgentTelemetry
from backend.mesh_store import InMemoryRegistry


def test_agent_telemetry_summarizes_runs_tools_and_evidence():
    telemetry = AgentTelemetry()
    telemetry.store = InMemoryRegistry("agent-observability-test")

    completed, completed_at = telemetry.start(operation="knowledge_companion", request_id="request-1")
    telemetry.tool_span(completed, tool_id="graph.search", attempt=1, status="completed", duration_ms=12.5)
    telemetry.finish(completed, completed_at, status="completed", evidence_count=3)

    failed, failed_at = telemetry.start(operation="workflow", request_id="request-2", workflow_id="bridge")
    telemetry.tool_span(failed, tool_id="ontology.publish", attempt=1, status="failed", duration_ms=7.5, error_type="HTTPException")
    telemetry.finish(failed, failed_at, status="failed", error_type="HTTPException")

    summary = telemetry.summary()

    assert summary["runs"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert summary["failure_rate"] == 0.5
    assert summary["tool_calls"] == 2
    assert summary["tool_failures"] == 1
    assert summary["evidence_total"] == 3
    assert summary["status"] == "degraded"
    assert summary["alerts"][0]["code"] == "AGENT_FAILURE_RATE_HIGH"
    assert "depo_agent_failure_ratio 0.5" in telemetry.prometheus()
