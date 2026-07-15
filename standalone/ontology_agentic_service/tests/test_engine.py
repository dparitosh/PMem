from pathlib import Path

import pytest

from ontology_agentic.runtime.engine import OntologyWorkflowEngine


TTL = """@prefix ex: <https://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:Asset a owl:Class .
ex:code a owl:DatatypeProperty .
"""


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "source.ttl"
    path.write_text(TTL, encoding="utf-8")
    return path


def test_registry_contains_only_canonical_agents() -> None:
    assert OntologyWorkflowEngine().registry.names() == [
        "ontology_alignment_agent",
        "ontology_export_agent",
        "ontology_intake_agent",
        "ontology_review_agent",
    ]


def test_unknown_workflow_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown workflow"):
        OntologyWorkflowEngine().run_workflow("unknown", {})


def test_intake_requires_ontology_path() -> None:
    with pytest.raises(ValueError, match="ontology_path"):
        OntologyWorkflowEngine().run_agent("ontology_intake_agent", {})


def test_lifecycle_runs_intake_review_and_alignment(tmp_path: Path) -> None:
    result = OntologyWorkflowEngine().run_workflow(
        "ontology_lifecycle",
        {"ontology_path": str(_source(tmp_path)), "instance_metadata": {}},
    )
    assert result["status"] == "completed"
    assert [step["agent"] for step in result["steps"]] == [
        "ontology_intake_agent",
        "ontology_review_agent",
        "ontology_alignment_agent",
    ]


def test_lifecycle_stops_on_blocking_review(tmp_path: Path) -> None:
    source = tmp_path / "class-only.ttl"
    source.write_text(
        "@prefix ex: <https://example.test/> . "
        "@prefix owl: <http://www.w3.org/2002/07/owl#> . "
        "ex:Asset a owl:Class .",
        encoding="utf-8",
    )
    result = OntologyWorkflowEngine().run_workflow(
        "ontology_lifecycle",
        {"ontology_path": str(source)},
    )
    assert result["status"] == "review_required"
    assert [step["agent"] for step in result["steps"]] == [
        "ontology_intake_agent",
        "ontology_review_agent",
    ]


def test_export_requires_output_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="output_dir"):
        OntologyWorkflowEngine().run_agent(
            "ontology_export_agent",
            {"ontology_path": str(_source(tmp_path))},
        )
