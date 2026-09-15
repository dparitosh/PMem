import pytest
from backend.data_catalog_service.product_contract import validate_revision


@pytest.mark.parametrize("field,value", [("manifest", {"digest": "changed"}), ("classification", "public"), ("semantic_releases", [])])
def test_replacement_of_published_evidence_is_rejected(field, value):
    original = {"manifest": {"digest": "original"}, "classification": "internal", "semantic_releases": ["v1"], "lifecycle_state": "published"}
    with pytest.raises(ValueError, match="immutable"):
        validate_revision(original, {**original, field: value})


def test_revoke_and_retry_preserve_version_content():
    original = {"product_id": "p", "version": "1", "updated_at": "yesterday", "manifest": {"digest": "original"}, "lifecycle_state": "published"}
    revoked = {**original, "lifecycle_state": "revoked"}
    validate_revision(original, revoked)
    validate_revision(revoked, revoked)
    with pytest.raises(ValueError, match="reactivated"):
        validate_revision(revoked, original)
