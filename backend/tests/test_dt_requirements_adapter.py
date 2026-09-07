from backend.agentic_service.dt_requirements_adapter import assess_manifest


def test_dt_requirements_manifest_reports_oslc_and_missing_capabilities():
    report = assess_manifest(
        {
            "name": "IIF_DT Design-to-Build AI Validation",
            "entry_agent": "DT_Design_To_Build_Orchestrator",
            "sequence": [
                {"agent": "DT_Requirements_Intelligence"},
                {"agent": "DT_Quality_Director"},
            ],
        },
        {"agents": [], "tools": [{"id": "engineering.inspect"}, {"id": "oslc.graph_rag"}]},
    )

    assert report["status"] == "partial"
    assert report["mappings"][0]["status"] == "compatible"
    assert "pipeline.telemetry" in report["missing_tools"]
    assert report["write_boundary"].startswith("Canonical publication API")


def test_empty_manifest_is_safe_and_deterministic():
    report = assess_manifest({}, {"agents": [], "tools": []})

    assert report["status"] == "compatible"
    assert report["mappings"] == []
