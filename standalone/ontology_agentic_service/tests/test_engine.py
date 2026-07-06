from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import ontology_agentic.runtime.engine as engine_module
from ontology_agentic.runtime.engine import OntologyWorkflowEngine


def test_registry_has_default_agents() -> None:
    engine = OntologyWorkflowEngine()
    names = engine.registry.names()
    assert "ontology_intake_agent" in names
    assert "ontology_orchestrator_agent" in names


def test_workflow_rejects_unknown_workflow() -> None:
    engine = OntologyWorkflowEngine()
    try:
        engine.run_workflow("unknown", {})
    except KeyError:
        assert True
    else:
        assert False


def test_intake_requires_ontology_path() -> None:
    engine = OntologyWorkflowEngine()
    try:
        engine.run_agent("ontology_intake_agent", {})
    except ValueError as exc:
        assert "ontology_path" in str(exc)
    else:
        assert False


def test_depo_registered_ontologies_workflow(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    monkeypatch.setattr(
        engine_module,
        "depo_list_registered_ontologies",
        lambda base_url=None: {"status": "success", "ontologies": [{"ontology_id": "mbseout"}]},
    )

    result = engine.run_workflow("depo_registered_ontologies", {})
    assert result["status"] == "completed"
    assert result["steps"][0]["output"]["ontologies"][0]["ontology_id"] == "mbseout"


def test_depo_semantic_workflow_requires_remote_workflow_id() -> None:
    engine = OntologyWorkflowEngine()
    try:
        engine.run_workflow("depo_semantic_workflow", {"payload": {}})
    except ValueError as exc:
        assert "depo_workflow_id" in str(exc)
    else:
        assert False


def test_depo_import_export_workflow(monkeypatch, tmp_path) -> None:
    engine = OntologyWorkflowEngine()
    monkeypatch.setattr(
        engine_module,
        "depo_export_import_owl",
        lambda task_id, export_format="ttl", output_dir=None, base_url=None: {
            "task_id": task_id,
            "format": export_format,
            "saved_to": str(tmp_path / "out.ttl"),
        },
    )

    result = engine.run_workflow(
        "depo_import_export",
        {"task_id": "task-1", "export_format": "ttl", "output_dir": str(tmp_path)},
    )
    assert result["status"] == "completed"
    assert result["steps"][0]["output"]["task_id"] == "task-1"

def test_depo_graph_search_workflow_single(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    calls = {}

    def fake_search(search, ontology_prefix="", base_url=None):
        calls["search"] = search
        calls["ontology_prefix"] = ontology_prefix
        calls["base_url"] = base_url
        return {"nodes": [{"name": "REQ-001"}], "links": []}

    monkeypatch.setattr(engine_module, "depo_graph_search", fake_search)

    result = engine.run_workflow(
        "depo_graph_search",
        {"search": "REQ-*", "ontology_prefix": "ap242", "depo_api_base_url": "http://localhost:8000"},
    )

    assert result["status"] == "completed"
    assert result["mode"] == "single"
    assert calls == {"search": "REQ-*", "ontology_prefix": "ap242", "base_url": "http://localhost:8000"}
    assert result["steps"][0]["output"]["nodes"][0]["name"] == "REQ-001"


def test_depo_graph_search_workflow_many(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    calls = {}

    def fake_search_many(names=None, search=None, base_url=None):
        calls["names"] = names
        calls["search"] = search
        calls["base_url"] = base_url
        return {"nodes": [{"name": "Part A"}, {"name": "Part B"}], "links": []}

    monkeypatch.setattr(engine_module, "depo_graph_search_many", fake_search_many)

    result = engine.run_workflow(
        "depo_graph_search",
        {"names": ["Part", "REQ-*"], "depo_api_base_url": "http://localhost:8000"},
    )

    assert result["status"] == "completed"
    assert result["mode"] == "multi"
    assert calls == {"names": ["Part", "REQ-*"], "search": None, "base_url": "http://localhost:8000"}
    assert len(result["steps"][0]["output"]["nodes"]) == 2


def test_depo_graph_search_requires_query() -> None:
    engine = OntologyWorkflowEngine()
    try:
        engine.run_workflow("depo_graph_search", {})
    except ValueError as exc:
        assert "search or names" in str(exc)
    else:
        assert False

def test_depo_oslc_catalog_workflow(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    monkeypatch.setattr(
        engine_module,
        "depo_oslc_catalog",
        lambda base_url=None: {"type": "oslc:ServiceProviderCatalog", "serviceProviders": []},
    )

    result = engine.run_workflow("depo_oslc", {"action": "catalog", "depo_api_base_url": "http://localhost:8000"})

    assert result["status"] == "completed"
    assert result["action"] == "catalog"
    assert result["steps"][0]["output"]["type"] == "oslc:ServiceProviderCatalog"


def test_depo_oslc_query_workflow(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    calls = {}

    def fake_query(resource_type="resources", query_params=None, base_url=None):
        calls["resource_type"] = resource_type
        calls["query_params"] = query_params
        calls["base_url"] = base_url
        return {"type": "oslc:QueryResult", "members": [{"name": "REQ-001"}]}

    monkeypatch.setattr(engine_module, "depo_oslc_query_resources", fake_query)

    result = engine.run_workflow(
        "depo_oslc",
        {
            "action": "query",
            "resource_type": "resources",
            "query_params": {"oslc.searchTerms": "REQ", "oslc.pageSize": 20},
            "depo_api_base_url": "http://localhost:8000",
        },
    )

    assert result["status"] == "completed"
    assert calls == {
        "resource_type": "resources",
        "query_params": {"oslc.searchTerms": "REQ", "oslc.pageSize": 20},
        "base_url": "http://localhost:8000",
    }
    assert result["steps"][0]["output"]["members"][0]["name"] == "REQ-001"


def test_depo_oslc_rejects_bad_query_params() -> None:
    engine = OntologyWorkflowEngine()
    try:
        engine.run_workflow("depo_oslc", {"action": "query", "query_params": "bad"})
    except ValueError as exc:
        assert "query_params" in str(exc)
    else:
        assert False

def test_step_inspect_workflow(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    calls = {}

    def fake_inspect(path_value, include_entity_sample=True, sample_size=20):
        calls["path_value"] = path_value
        calls["include_entity_sample"] = include_entity_sample
        calls["sample_size"] = sample_size
        return {"format": "p21", "entity_count": 4, "cad_summary": {"products": 1}}

    monkeypatch.setattr(engine_module, "inspect_step_file", fake_inspect)

    result = engine.run_workflow("step_inspect", {"step_path": "D:/sample.stp", "sample_size": 5})

    assert result["status"] == "completed"
    assert calls == {"path_value": "D:/sample.stp", "include_entity_sample": True, "sample_size": 5}
    assert result["steps"][0]["output"]["entity_count"] == 4


def test_step_export_workflow(monkeypatch) -> None:
    engine = OntologyWorkflowEngine()
    calls = {}

    def fake_export(path_value, output_path=None, base_uri="", namespace_prefix="step", include_pmi=True):
        calls["path_value"] = path_value
        calls["output_path"] = output_path
        calls["base_uri"] = base_uri
        calls["namespace_prefix"] = namespace_prefix
        calls["include_pmi"] = include_pmi
        return {"success": True, "stats": {"output_file": "D:/out.ttl"}}

    monkeypatch.setattr(engine_module, "export_step_to_ttl", fake_export)

    result = engine.run_workflow(
        "step_export",
        {"step_path": "D:/sample.stp", "output_path": "D:/out.ttl", "namespace_prefix": "ap242"},
    )

    assert result["status"] == "completed"
    assert calls["path_value"] == "D:/sample.stp"
    assert calls["output_path"] == "D:/out.ttl"
    assert calls["namespace_prefix"] == "ap242"
    assert result["steps"][0]["output"]["success"] is True


def test_step_workflow_requires_path() -> None:
    engine = OntologyWorkflowEngine()
    try:
        engine.run_workflow("step_inspect", {})
    except ValueError as exc:
        assert "step_path" in str(exc)
    else:
        assert False
