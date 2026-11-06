import pytest
from backend.depo_platform.metadata_repository import MetadataRepository


def test_rejects_invalid_actor_before_connecting():
    with pytest.raises(ValueError):
        MetadataRepository().save('a', {'asset_id': 'a'}, expected_revision=0, actor='')


def test_rejects_mismatched_identity():
    with pytest.raises(ValueError):
        MetadataRepository().save('a', {'asset_id': 'b'}, expected_revision=0, actor='operator')
