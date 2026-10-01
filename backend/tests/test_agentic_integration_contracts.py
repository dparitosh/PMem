"""Regression tests for resolved tool authentication and evidence boundaries."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.agentic_service.transport_auth import downstream_headers, downstream_inputs, tool_retry_allowed
from backend.agentic_service.dt_requirements_adapter import assess_manifest
from backend.agentic_service.ontology_orchestrator import plan_bridge


@pytest.mark.parametrize("service,method,key", [
    ("ontology", "POST", "ONTOLOGY_APPROVAL_TOKEN"),
    ("ingestion", "POST", "INGESTION_WRITE_TOKEN"),
    ("qif", "POST", "ONTOLOGY_APPROVAL_TOKEN"),
    ("data_pipeline", "GET", "GRAPH_READ_TOKEN"),
    ("data_products", "GET", "GRAPH_READ_TOKEN"),
])
def test_service_credentials(monkeypatch, service, method, key):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv(key, "server-secret")
    tool = {"service": service, "method": method, "mutates": False}
    assert downstream_headers(SimpleNamespace(headers={}), "http://localhost/api", tool=tool) == {"Authorization": "Bearer server-secret"}
    monkeypatch.delenv(key)
    with pytest.raises(HTTPException) as error:
        downstream_headers(SimpleNamespace(headers={}), "http://localhost/api", tool=tool)
    assert error.value.status_code == 503


def test_registration_uses_ontology_approval(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("ONTOLOGY_APPROVAL_TOKEN", "ontology-secret")
    monkeypatch.setenv("AGENTIC_APPROVAL_TOKEN", "different-secret")
    result = downstream_inputs({"id": "ontology.register", "mutates": True}, {"approval_token": "caller", "approved_by": "forged"}, "verified")
    assert result == {"approval_token": "ontology-secret", "approved_by": "verified"}


def test_retries_use_resolved_mutation_contract():
    for tool in ({"mutates": True}, {}):
        assert not tool_retry_allowed(tool, attempt=1, retries=2, status_code=503)
    assert tool_retry_allowed({"mutates": False}, attempt=1, retries=2, status_code=503)
    assert not tool_retry_allowed({"mutates": False}, attempt=3, retries=2, status_code=503)
    assert not tool_retry_allowed({"mutates": False}, attempt=1, retries=2, status_code=403)


def test_external_steps_and_invalid_stages():
    catalog = {"tools": [{"id": "engineering.inspect"}, {"id": "oslc.graph_rag"}]}
    report = assess_manifest({"steps": [{"agent": "DT_Requirements_Intelligence"}]}, catalog)
    assert report["status"] == "compatible"
    report = assess_manifest({"steps": [{"agent": "DT_Requirements_Intelligence"}, "bad"]}, catalog)
    assert report["status"] == "invalid"
    assert report["validation_errors"]
    assert "Correct" in report["next_action"]


def test_bridge_retains_ambiguity_and_unmatched(monkeypatch):
    monkeypatch.setenv("ONTOLOGY_AGENT_LLM_ENABLED", "false")
    summary = {"term_index": [{"iri": "urn:a:Part", "label": "Pièce", "kind": "Class"},
                              {"iri": "urn:b:Part", "label": "Pièce", "kind": "Class"}]}
    result = plan_bridge({"entities": ["PIÈCE", "Missing"]}, ontology_summary=summary)
    assert result["ambiguous_count"] == result["unmatched_count"] == 1
    assert len(result["alignment_items"]) == 2
    assert result["alignment_items"][0]["candidate_count"] == 2
    assert "domain_range_compatibility" in result["alignment_items"][0]["unresolved_checks"]


def test_bridge_cap_preserves_all_sources(monkeypatch):
    monkeypatch.setenv("ONTOLOGY_AGENT_LLM_ENABLED", "false")
    summary = {"term_index": [{"iri": "urn:Part", "kind": "Class"}]}
    result = plan_bridge({"entities": ["Part"] * 201}, ontology_summary=summary)
    assert len(result["alignment_candidates"]) == 200
    assert len(result["alignment_items"]) == 201
    assert result["candidate_limit_reached"]
    with pytest.raises(ValueError):
        plan_bridge({"entities": ["Part"] * 2001}, ontology_summary=summary)
    with pytest.raises(ValueError):
        plan_bridge({"entities": [{}]}, ontology_summary=summary)
