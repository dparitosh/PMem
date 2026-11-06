from backend.oslc_service.ontology_shapes import catalog_shape
from backend.ontology_service.catalog import OntologyCatalog


def test_catalog_shape_retains_draft_and_declarations(monkeypatch):
    turtle = b'@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:Part> a owl:Class . <urn:name> a owl:DatatypeProperty .'
    monkeypatch.setattr(OntologyCatalog, "read_artifact", lambda self, identifier: (
        {"original_filename": "x.ttl", "lifecycle_status": "draft", "semantic_completeness": "partial"}, turtle))
    result = catalog_shape("sample", "https://gateway.example")
    assert result["lifecycle_status"] == "draft"
    assert result["describes"] == ["urn:Part"]
    assert result["properties"][0]["propertyDefinition"] == "urn:name"
    assert "occurs" not in result["properties"][0]
