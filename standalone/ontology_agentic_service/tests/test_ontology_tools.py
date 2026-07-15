from pathlib import Path

import pytest

from ontology_agentic.tools.ontology_tools import (
    ontology_alignment_plan,
    ontology_export,
    ontology_inspect,
    ontology_review,
)


TTL = """@prefix ex: <https://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:onto a owl:Ontology .
ex:Asset a owl:Class .
ex:Pump a owl:Class ; rdfs:subClassOf ex:Asset .
ex:hasCode a owl:DatatypeProperty ; rdfs:domain ex:Asset ; rdfs:range rdfs:Literal .
ex:reviewNote a owl:AnnotationProperty .
ex:pump1 a owl:NamedIndividual, ex:Pump .
"""


def test_canonical_ontology_tools(tmp_path: Path) -> None:
    source = tmp_path / "source.ttl"
    source.write_text(TTL, encoding="utf-8")
    summary = ontology_inspect(source)
    assert summary["parser"] == "rdflib"
    assert summary["classes"] == 2
    assert summary["annotation_properties"] == 1
    assert ontology_review(source)["status"] == "ok"
    plan = ontology_alignment_plan(source, {"entities": [{"name": "pump"}]})
    assert plan["mapping_targets"]["entity_to_class"] == 1
    exported = ontology_export(source, tmp_path / "exports", "jsonld")
    assert Path(exported["output_path"]).is_file()


def test_alignment_rejects_non_array_fields(tmp_path: Path) -> None:
    source = tmp_path / "source.ttl"
    source.write_text(TTL, encoding="utf-8")
    with pytest.raises(ValueError, match="entities must be an array"):
        ontology_alignment_plan(source, {"entities": "pump"})
