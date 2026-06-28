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
