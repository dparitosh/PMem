import re

import pytest

from backend.ontology_service.intelligence import SemanticIntelligence


class MemoryRegistry:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = value

    def all(self):
        return dict(self.values)


def test_sdk_alias_preserves_authenticated_service_principal_and_retry_identity(tmp_path):
    registry = MemoryRegistry()
    service = SemanticIntelligence(tmp_path, registry)
    snapshot = service.create_merge_version(ontology={'ontology_id': 'merged_1'}, author='deployment-bootstrap')
    assert snapshot['author'] == 'deployment-bootstrap'
    assert snapshot['metadata']['authenticated_author'] == 'deployment-bootstrap'
    assert snapshot['metadata']['author_representation'] == 'service-principal-alias'
    assert re.fullmatch(r'principal-[0-9a-f]{32}@principals\.pmem\.invalid', snapshot['sdk_author'])
    assert service.create_merge_version(ontology={'ontology_id': 'merged_1'}, author='other-principal') == snapshot
    # Hydrate the real Semantica manager from the retained snapshot, too.
    assert service.list_versions()
    assert len(registry.values) == 1


def test_email_author_remains_unchanged(tmp_path):
    service = SemanticIntelligence(tmp_path, MemoryRegistry())
    result = service.create_version(ontology={}, label='v1', author='qa@example.org', description='Test baseline')
    assert result['author'] == result['sdk_author'] == 'qa@example.org'


def test_empty_author_does_not_create_version(tmp_path):
    registry = MemoryRegistry()
    with pytest.raises(ValueError, match='author is required'):
        SemanticIntelligence(tmp_path, registry).create_version(ontology={}, label='v1', author=' ', description='Test baseline')
    assert not registry.values
