from pathlib import Path

import pytest


pytest.importorskip("owlready2")

from AgentsRegistry.CodedTools.ontology_owlready2_tools import owlready2_analyze


RDF_XML = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:ex="http://example.test/">
  <owl:Ontology rdf:about="http://example.test/"/>
  <owl:Class rdf:about="http://example.test/Asset"/>
  <owl:NamedIndividual rdf:about="http://example.test/pump1">
    <rdf:type rdf:resource="http://example.test/Asset"/>
  </owl:NamedIndividual>
</rdf:RDF>
"""


def test_owlready2_structural_analysis_uses_isolated_world(tmp_path: Path):
    path = tmp_path / "sample.owl"
    path.write_text(RDF_XML, encoding="utf-8")
    result = owlready2_analyze(str(path))
    assert result["engine"] == "owlready2"
    assert result["world_scope"] == "isolated"
    assert result["remote_imports_allowed"] is False
    assert result["reasoning_run"] is False
    assert result["before_reasoning"]["classes"] == 1
    assert result["before_reasoning"]["individuals"] == 1
