from pathlib import Path

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
