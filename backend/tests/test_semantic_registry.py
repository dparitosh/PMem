import pytest

from backend.depo_platform.semantic_registry import release_reference


def test_release_reference_requires_an_approved_semantic_version():
    assert release_reference({"asset_id": "ceim-core", "version": "0.1.0", "lifecycle_status": "approved"}) == {
        "asset_id": "ceim-core", "version": "0.1.0", "lifecycle_status": "approved"
    }
    with pytest.raises(ValueError, match="approved"):
        release_reference({"asset_id": "ceim-core", "version": "0.1.0", "lifecycle_status": "draft"})
    with pytest.raises(ValueError, match="semantic version"):
        release_reference({"asset_id": "ceim-core", "version": "v1", "lifecycle_status": "approved"})


def test_release_reference_accepts_registry_generated_digit_leading_uuid():
    value={"asset_id":"3c27e6d6-7ad5-4955-bc82-b8885c78a052","version":"1.0.0","lifecycle_status":"approved"}
    assert release_reference(value)==value
    for unsafe in ("3invalid", "../asset", "3c27e6d6-7ad5-4955-bc82-b8885c78a052?token=x"):
        with pytest.raises(ValueError):
            release_reference({**value,"asset_id":unsafe})
