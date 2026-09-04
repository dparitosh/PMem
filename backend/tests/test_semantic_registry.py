import pytest

from backend.platform.semantic_registry import release_reference


def test_release_reference_requires_an_approved_semantic_version():
    assert release_reference({"asset_id": "ceim-core", "version": "0.1.0", "lifecycle_status": "approved"}) == {
        "asset_id": "ceim-core", "version": "0.1.0", "lifecycle_status": "approved"
    }
    with pytest.raises(ValueError, match="approved"):
        release_reference({"asset_id": "ceim-core", "version": "0.1.0", "lifecycle_status": "draft"})
    with pytest.raises(ValueError, match="semantic version"):
        release_reference({"asset_id": "ceim-core", "version": "v1", "lifecycle_status": "approved"})
