from pathlib import Path

import pytest

from AgentsRegistry.CodedTools.ontology_alignment_plan import run_ontology_alignment_plan as ontology_alignment_plan
from AgentsRegistry.CodedTools.ontology_export import run_ontology_export as ontology_export
from AgentsRegistry.CodedTools.ontology_inspect import run_ontology_inspect as ontology_inspect
from AgentsRegistry.CodedTools.ontology_review import run_ontology_review as ontology_review


ONTOLOGY = """@prefix ex: <http://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:onto a owl:Ontology .
ex:Asset a owl:Class .
ex:Pump a owl:Class ; rdfs:subClassOf ex:Asset .
ex:hasSerial a owl:DatatypeProperty ; rdfs:domain ex:Asset .
ex:pump1 a owl:NamedIndividual, ex:Pump .
"""


@pytest.fixture
def ontology_path(tmp_path: Path) -> Path:
    path = tmp_path / "sample.ttl"
    path.write_text(ONTOLOGY, encoding="utf-8")
    return path


def test_inspect_and_review_asserted_graph(ontology_path: Path):
    summary = ontology_inspect(str(ontology_path))
    assert summary["engine"] == "rdflib"
    assert summary["scope"] == "asserted_graph"
    assert summary["classes"] == 2
    assert summary["datatype_properties"] == 1
    assert summary["individuals"] == 1
    review = ontology_review(str(ontology_path), "schema_and_instances")
    assert review["profile"] == "schema_and_instances"
    assert not any(issue["code"] == "NO_INDIVIDUALS" for issue in review["issues"])


def test_alignment_is_a_plan_only(ontology_path: Path):
    plan = ontology_alignment_plan(
        str(ontology_path),
        {"entities": ["pump"], "attributes": ["serial"], "relationships": [], "metadata": []},
    )
    assert plan["status"] == "draft_mapping_plan"
    assert plan["mapping_targets"]["entity_to_class"] == 1
    assert "required_validations" in plan


def test_export_creates_copy(ontology_path: Path, tmp_path: Path):
    result = ontology_export(str(ontology_path), str(tmp_path / "out"), "nt")
    assert Path(result["output_path"]).is_file()
    assert Path(result["output_path"]) != ontology_path
    with pytest.raises(FileExistsError, match="already exists"):
        ontology_export(str(ontology_path), str(tmp_path / "out"), "nt")


def test_owl_extension_can_contain_turtle(tmp_path: Path):
    path = tmp_path / "turtle-content.owl"
    path.write_text(ONTOLOGY, encoding="utf-8")
    assert ontology_inspect(str(path))["classes"] == 2


def test_explicit_argument_validation(ontology_path: Path, tmp_path: Path):
    with pytest.raises(ValueError, match="profile"):
        ontology_review(str(ontology_path), "wrong")
    with pytest.raises(ValueError, match="export_format"):
        ontology_export(str(ontology_path), str(tmp_path), "wrong")
