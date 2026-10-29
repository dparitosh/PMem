"""Cross-layer retained-file recovery with real parsing and merge preparation."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Graph

from backend.artifact_store import ArtifactStore
from backend.ontology_service import catalog as module
from backend.ontology_service.catalog import OntologyCatalog


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    store = ArtifactStore(tmp_path / 'artifacts')
    monkeypatch.setattr(module, 'artifact_store', store)
    catalog = OntologyCatalog(root=tmp_path / 'catalog')
    records = [catalog.register(content=(f'@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:{name}> a owl:Class .').encode(),
                                filename=name+'.ttl', ontology_name=name, prefix=name) for name in ('part', 'process')]
    return catalog, store, records


def test_restart_browse_reasoning_digest_and_merge_use_retained_artifacts(deployment, tmp_path, monkeypatch):
    from backend.ontology_service.domain.taxonomy import OntologyTaxonomyService
    from backend.ontology_service.domain.reasoning import OntologyReasoningService
    from backend.ontology_service.merge_service import GovernedMergeService
    original, _, records = deployment
    digests = {row['ontology_id']: original.artifact_digest(row['ontology_id']) for row in records}
    for row in records:
        Path(row['artifact_path']).unlink()
    cold = OntologyCatalog(root=original.root)
    monkeypatch.setattr(module, 'catalog', cold)
    for row in records:
        identifier = row['ontology_id']
        context = OntologyTaxonomyService._semantic_context(identifier)
        assert OntologyTaxonomyService._parse_rdf(context['meta'], context['file_path'])['nodes']
        assert Graph().parse(OntologyReasoningService.semantic_context(identifier)['file_path'], format='turtle')
        assert cold.artifact_digest(identifier) == digests[identifier]
        assert cold.get(identifier)['lifecycle_status'] == 'draft'
    merge = GovernedMergeService(cold, SimpleNamespace(), tmp_path)
    result = merge._preview({'source_ontology_ids': [row['ontology_id'] for row in records]}, defer_semantics=True)
    assert len(result['sources']) == 2
    assert result['semantic_checks']['status'] == 'pending'  # No validation or approval is invented by recovery.


def test_relocated_catalog_resolves_by_identity_not_old_absolute_path(deployment, tmp_path):
    original, _, records = deployment
    row = records[0]
    content = Path(row['artifact_path']).read_bytes()
    Path(row['artifact_path']).unlink()
    relocated = OntologyCatalog(root=tmp_path / 'new-catalog')
    relocated._save_metadata(row)
    metadata, restored = relocated.read_artifact(row['ontology_id'])
    assert restored == content
    assert Path(metadata['artifact_path']).is_relative_to(relocated.root)
    before = Path(metadata['artifact_path']).stat().st_mtime_ns
    assert relocated.read_artifact(row['ontology_id'])[1] == content
    assert Path(metadata['artifact_path']).stat().st_mtime_ns == before


def test_corrupt_retained_content_does_not_become_valid_source(deployment):
    catalog, store, records = deployment
    row = records[0]
    _, retained = store.resolve(row['artifact_id'])
    Path(row['artifact_path']).unlink()
    retained.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='immutable artifact_id'):
        catalog.read_artifact(row['ontology_id'])
    assert not Path(row['artifact_path']).exists()


def test_missing_both_copies_remains_an_explicit_failure(deployment):
    catalog, store, records = deployment
    row = records[0]
    _, retained = store.resolve(row['artifact_id'])
    Path(row['artifact_path']).unlink()
    retained.unlink()
    with pytest.raises(ValueError, match='not found'):
        catalog.read_artifact(row['ontology_id'])


def test_external_files_are_never_adopted_as_owned_artifacts(deployment, tmp_path):
    catalog, _, records = deployment
    row = records[0]
    external = tmp_path / 'external.ttl'
    external.write_text('private')
    with pytest.raises(ValueError, match='outside its catalog'):
        catalog.resolve_artifact_path(row['ontology_id'], {**row, 'artifact_path': str(external)})
