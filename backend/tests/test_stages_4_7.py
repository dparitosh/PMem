"""Validation checks; estimated legacy load metrics are not publication evidence."""
from backend.Services.pipeline_stages_4_7 import OntologyValidationService


def test_validation_counts_actual_graph_not_supplied_estimates(monkeypatch):
    from backend.Services.owl_generation_service import OWLGenerationService
    monkeypatch.setattr(OWLGenerationService, 'validate_with_shacl', lambda _: {'conforms': True})
    ttl = '''@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:Part a owl:Class . ex:revision a owl:DatatypeProperty .'''
    result = OntologyValidationService.validate(ttl, {'entity_count':150, 'owl_triple_count':500})
    assert result.valid is True
    assert (result.schema_triples, result.class_count, result.property_count) == (2,1,1)
    assert result.errors == 0


def test_invalid_rdf_is_a_validation_failure():
    result = OntologyValidationService.validate('ex:Part a rdfs:Class .', {})
    assert result.valid is False
    assert result.errors == 1
    assert result.issues
