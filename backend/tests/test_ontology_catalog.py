from __future__ import annotations

import pytest

from backend.ontology_service.catalog import OntologyCatalog


def test_workflow_retry_uses_filtered_lookup_and_skips_identical_graph_comparison(tmp_path, monkeypatch):
    from backend.mesh_store import InMemoryRegistry
    import rdflib.compare
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://unused/test')
    registry = InMemoryRegistry()
    catalog = OntologyCatalog(root=tmp_path, registry=registry)
    content = b'<https://example.test/a> <https://example.test/p> "value" .'
    source = 'engineering-workflow:' + 'a' * 64
    existing = {'ontology_id': 'example_abc', 'source': source, 'prefix': 'example',
                'ontology_name': 'Example', 'description': '', 'lifecycle_status': 'draft',
                'validation': {'rdf_format': 'turtle'}}
    registry.put('example_abc', existing)
    monkeypatch.setattr(catalog, 'list', lambda: pytest.fail('Full catalog scan must not run'))
    monkeypatch.setattr(catalog, 'read_artifact', lambda _: (existing, content))
    monkeypatch.setattr(rdflib.compare, 'isomorphic', lambda *_: pytest.fail('Identical bytes need no graph comparison'))
    result = catalog.register(content=content, filename='example.ttl', prefix='example',
                              ontology_name='Example', source=source)
    assert result['ontology_id'] == 'example_abc'


def test_catalog_validates_rdf_and_records_review_lifecycle(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    record = catalog.register(
        content=b'@prefix ex: <https://example.test/> . ex:Part ex:label "Part" .',
        filename="part.ttl", ontology_name="Part", prefix="part",
    )

    assert record["lifecycle_status"] == "draft"
    assert record["validation"] == {"status": "passed", "rdf_format": "turtle", "triple_count": 1}
    review = catalog.transition(ontology_id=record["ontology_id"], target="in_review", actor="steward")
    approved = catalog.transition(ontology_id=record["ontology_id"], target="approved", actor="steward")
    assert review["lifecycle_status"] == "in_review"
    assert approved["lifecycle_status"] == "approved"


@pytest.mark.parametrize('case', ['equivalent', 'conflict', 'duplicate', 'retired'])
def test_filtered_workflow_retry_preserves_governance_checks(tmp_path, monkeypatch, case):
    from backend.mesh_store import InMemoryRegistry
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://unused/test')
    registry = InMemoryRegistry()
    catalog = OntologyCatalog(root=tmp_path, registry=registry)
    source = 'engineering-workflow:' + 'b' * 64
    retained = b'<https://example.test/a> <https://example.test/p> "value" .'
    incoming = b'@prefix ex: <https://example.test/> . ex:a ex:p "value" .'
    existing = {'ontology_id': 'example_one', 'source': source, 'prefix': 'example',
                'ontology_name': 'Example', 'description': '', 'lifecycle_status': 'draft',
                'validation': {'rdf_format': 'turtle'}}
    if case == 'retired':
        existing['lifecycle_status'] = 'retired'
    registry.put('example_one', existing)
    if case == 'duplicate':
        registry.put('example_two', {**existing, 'ontology_id': 'example_two'})
    if case == 'conflict':
        incoming = b'<https://example.test/a> <https://example.test/p> "different" .'
    monkeypatch.setattr(catalog, 'read_artifact', lambda _: (existing, retained))
    def run():
        return catalog.register(content=incoming, filename='example.ttl', prefix='example',
                                ontology_name='Example', source=source)
    if case == 'equivalent':
        assert run()['ontology_id'] == 'example_one'
    else:
        with pytest.raises(ValueError, match={'conflict': 'conflicts with its artifact',
                'duplicate': 'Multiple ontology', 'retired': 'retired'}[case]):
            run()


def test_catalog_rejects_invalid_ontology_syntax(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    with pytest.raises(ValueError, match="parsing failed"):
        catalog.register(content=b"not turtle [", filename="broken.ttl", ontology_name="Broken", prefix="broken")


def test_catalog_accepts_turtle_serialized_owl(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    record = catalog.register(
        content=b'@prefix owl: <http://www.w3.org/2002/07/owl#> . <https://example.test/onto> a owl:Ontology .',
        filename="ontology.owl", ontology_name="Example", prefix="example",
    )
    assert record["validation"]["rdf_format"] == "turtle"


def test_legacy_catalog_analytics_backfill_is_additive_and_keeps_draft(tmp_path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    record = catalog.register(
        content=(b'@prefix owl: <http://www.w3.org/2002/07/owl#> . '
                 b'@prefix ex: <https://example.test/> . ex:Part a owl:Class . '
                 b'ex:hasPart a owl:ObjectProperty .'),
        filename="legacy.ttl", ontology_name="Legacy", prefix="legacy",
    )
    legacy = catalog.get(record["ontology_id"])
    for field in ("lifecycle_status", "semantic_completeness", "statistics", "validation", "lifecycle_events"):
        legacy.pop(field, None)
    catalog._save_metadata(legacy)

    result = catalog.backfill_analytics(ontology_ids=[record["ontology_id"]], actor="steward")

    assert result["updated"] == 1
    updated = catalog.get(record["ontology_id"])
    assert updated["lifecycle_status"] == "draft"
    assert updated["semantic_completeness"] == "unknown"
    assert updated["statistics"]["classes"] == 1
    assert updated["statistics"]["object_properties"] == 1
    assert "no approval or publication" in updated["lifecycle_events"][-1]["reason"]


def test_invalid_legacy_artifact_cannot_be_approved(tmp_path):
    catalog = OntologyCatalog(root=tmp_path)
    record = catalog.adopt_legacy(ontology_id="legacy", content=b"broken [", filename="old.ttl", ontology_name="Old", prefix="old")
    catalog.transition(ontology_id=record["ontology_id"], target="in_review", actor="steward")
    with pytest.raises(ValueError, match="parsing failed"):
        catalog.transition(ontology_id="legacy", target="approved", actor="steward")
    assert catalog.get("legacy")["lifecycle_status"] == "in_review"


def test_registration_rejects_reserved_metadata_filename(tmp_path):
    instance = OntologyCatalog(root=tmp_path / 'reserved')
    with pytest.raises(ValueError):
        instance.register(content=b'{}', filename='metadata.json', ontology_name='Example', prefix='ex')


def test_registration_rejects_identity_override(tmp_path):
    instance = OntologyCatalog(root=tmp_path / 'override')
    with pytest.raises(ValueError):
        instance.register(content=b'@prefix ex: <https://example.test/> . ex:A ex:p ex:B .',
                          filename='example.ttl', ontology_name='Example', prefix='ex',
                          extra_metadata={'artifact_path': '/outside'})


def test_registration_blocks_remote_jsonld_context():
    with pytest.raises(ValueError):
        OntologyCatalog._parse_ontology(b'{"@context":"https://remote.invalid/context", "@id":"https://example.test/A"}', 'example.jsonld')


def test_registration_blocks_external_xml_entities():
    with pytest.raises(ValueError):
        OntologyCatalog._parse_ontology(b'<!DOCTYPE rdf [<!ENTITY file SYSTEM "file:///secret">]><rdf>&file;</rdf>', 'example.rdf')
