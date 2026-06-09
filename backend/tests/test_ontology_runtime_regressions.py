from pathlib import Path

from backend.Services.owlready_runtime import OwlreadyOntologyRuntime
from backend.Services.ontology_taxonomy_service import OntologyTaxonomyService
from backend.Services.ontology_validator import OntologyValidator


def test_validate_file_wrapper_accepts_ttl(tmp_path: Path):
    ttl_path = tmp_path / "mini.ttl"
    ttl_path.write_text(
        """
        @prefix ex: <http://example.com/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

        ex:onto a owl:Ontology ; rdfs:label "Mini" .
        ex:Thing a owl:Class ; rdfs:label "Thing" .
        """,
        encoding="utf-8",
    )

    report = OntologyValidator().validate_file(str(ttl_path))

    assert report.source == str(ttl_path)
    assert report.stats["owl_classes"] == 1
    assert report.is_valid


def test_parse_rdf_handles_owl_extension_with_turtle_payload(tmp_path: Path):
    owl_path = tmp_path / "mini.owl"
    owl_path.write_text(
        """
        @prefix ex: <http://example.com/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

        ex:onto a owl:Ontology ; rdfs:label "Mini" .
        ex:Parent a owl:Class ; rdfs:label "Parent" .
        ex:Child a owl:Class ; rdfs:label "Child" ; rdfs:subClassOf ex:Parent .
        """,
        encoding="utf-8",
    )
    meta = {"prefix": "mini", "ontology_id": "mini_1"}

    parsed = OntologyTaxonomyService._parse_rdf(meta, owl_path)

    assert parsed is not None
    assert parsed["nodes"]
    assert any(node["label"] == "Child" for node in parsed["nodes"])
    assert any(edge["mapping_type"] == "subClassOf" for edge in parsed["edges"])


def test_owlready_reasoning_extracts_classes_properties_and_individuals(tmp_path: Path):
    if not OwlreadyOntologyRuntime.is_available():
        import pytest
        pytest.skip("owlready2 is not installed in this Python environment")

    owl_path = tmp_path / "reasoning.owl"
    owl_path.write_text(
        """<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
                 xmlns:owl="http://www.w3.org/2002/07/owl#"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
                 xmlns:ex="http://example.com/reason#">
          <owl:Ontology rdf:about="http://example.com/reason"/>
          <owl:Class rdf:about="http://example.com/reason#Part">
            <rdfs:label>Part</rdfs:label>
          </owl:Class>
          <owl:Class rdf:about="http://example.com/reason#Fastener">
            <rdfs:label>Fastener</rdfs:label>
            <rdfs:subClassOf rdf:resource="http://example.com/reason#Part"/>
          </owl:Class>
          <owl:ObjectProperty rdf:about="http://example.com/reason#hasChild">
            <rdfs:label>has child</rdfs:label>
            <rdfs:domain rdf:resource="http://example.com/reason#Part"/>
            <rdfs:range rdf:resource="http://example.com/reason#Part"/>
          </owl:ObjectProperty>
          <owl:DatatypeProperty rdf:about="http://example.com/reason#partNumber">
            <rdfs:label>part number</rdfs:label>
            <rdfs:domain rdf:resource="http://example.com/reason#Part"/>
            <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
          </owl:DatatypeProperty>
          <owl:NamedIndividual rdf:about="http://example.com/reason#bolt1">
            <rdf:type rdf:resource="http://example.com/reason#Fastener"/>
            <rdfs:label>Bolt 1</rdfs:label>
          </owl:NamedIndividual>
        </rdf:RDF>
        """,
        encoding="utf-8",
    )

    result = OwlreadyOntologyRuntime.inspect_ontology(owl_path, "reason")

    assert result["status"] == "success"
    assert result["engine"] == "owlready2"
    assert result["summary"]["classes"] == 2
    assert result["summary"]["object_properties"] == 1
    assert result["summary"]["datatype_properties"] == 1
    assert result["summary"]["individuals"] == 1
    assert any(edge["type"] == "subClassOf" for edge in result["subclass_edges"])
    assert result["object_properties"][0]["domain"][0]["label"] == "Part"
    assert result["object_properties"][0]["range"][0]["label"] == "Part"


def test_owlready_reasoning_ignores_unavailable_external_imports(tmp_path: Path):
    if not OwlreadyOntologyRuntime.is_available():
        import pytest
        pytest.skip("owlready2 is not installed in this Python environment")

    owl_path = tmp_path / "with_import.owl"
    owl_path.write_text(
        """<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
                 xmlns:owl="http://www.w3.org/2002/07/owl#">
          <owl:Ontology rdf:about="http://example.com/local">
            <owl:imports rdf:resource="http://example.invalid/missing/import"/>
          </owl:Ontology>
          <owl:Class rdf:about="http://example.com/local#LocalClass">
            <rdfs:label>Local Class</rdfs:label>
          </owl:Class>
        </rdf:RDF>
        """,
        encoding="utf-8",
    )

    result = OwlreadyOntologyRuntime.inspect_ontology(owl_path, "local")

    assert result["status"] == "success"
    assert result["summary"]["classes"] == 1
    assert result["classes"][0]["label"] == "Local Class"


def test_taxonomy_payload_includes_reasoning_summary(tmp_path: Path, monkeypatch):
    if not OwlreadyOntologyRuntime.is_available():
        import pytest
        pytest.skip("owlready2 is not installed in this Python environment")

    owl_path = tmp_path / "mini.owl"
    owl_path.write_text(
        """<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
                 xmlns:owl="http://www.w3.org/2002/07/owl#">
          <owl:Ontology rdf:about="http://example.com/mini"/>
          <owl:Class rdf:about="http://example.com/mini#Parent">
            <rdfs:label>Parent</rdfs:label>
          </owl:Class>
          <owl:Class rdf:about="http://example.com/mini#Child">
            <rdfs:label>Child</rdfs:label>
            <rdfs:subClassOf rdf:resource="http://example.com/mini#Parent"/>
          </owl:Class>
        </rdf:RDF>
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        OntologyTaxonomyService,
        "_resolve_metadata",
        staticmethod(lambda _identifier: {
            "ontology_id": "mini_1",
            "ontology_name": "Mini",
            "prefix": "mini",
            "file_path": str(owl_path),
            "original_filename": "mini.owl",
        }),
    )

    taxonomy = OntologyTaxonomyService.get_taxonomy("mini_1")
    reasoning = OntologyTaxonomyService.get_reasoning("mini_1")

    assert taxonomy["extraction_source"] == "owlready2"
    assert taxonomy["reasoning_summary"]["classes"] == 2
    assert reasoning["summary"]["subclass_edges"] == 1


def test_taxonomy_and_reasoning_share_the_same_context_resolution(tmp_path: Path, monkeypatch):
    owl_path = tmp_path / "shared.owl"
    owl_path.write_text(
        """<?xml version="1.0"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
                 xmlns:owl="http://www.w3.org/2002/07/owl#">
          <owl:Ontology rdf:about="http://example.com/shared"/>
          <owl:Class rdf:about="http://example.com/shared#Thing">
            <rdfs:label>Thing</rdfs:label>
          </owl:Class>
        </rdf:RDF>
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        OntologyTaxonomyService,
        "_resolve_metadata",
        staticmethod(lambda _identifier: {
            "ontology_id": "shared_1",
            "ontology_name": "Shared",
            "prefix": "shared",
            "file_path": str(owl_path),
            "original_filename": "shared.owl",
        }),
    )

    taxonomy = OntologyTaxonomyService.get_taxonomy("shared_1")
    reasoning = OntologyTaxonomyService.get_reasoning("shared_1")

    assert taxonomy["prefix"] == "shared"
    assert reasoning["prefix"] == "shared"
    assert taxonomy["ontology_id"] == reasoning["ontology_id"] == "shared_1"


def test_owlready_unsupported_payload_is_structured(tmp_path: Path):
    if not OwlreadyOntologyRuntime.is_available():
        import pytest
        pytest.skip("owlready2 is not installed in this Python environment")

    broken_path = tmp_path / "broken.owl"
    broken_path.write_text("this is not rdf", encoding="utf-8")

    result = OwlreadyOntologyRuntime.inspect_ontology(broken_path, "broken")

    assert result["engine"] == "owlready2"
    assert result["available"] is True
    assert result["status"] in {"unsupported", "success"}
    assert "diagnostics" in result
    if result["status"] == "unsupported":
        assert result["summary"]["classes"] == 0
        assert result["diagnostics"][0]["category"] == "load"
