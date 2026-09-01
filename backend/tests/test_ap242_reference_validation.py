from pathlib import Path

from backend.ingestion_service.ap242_reference import AP242ReferenceValidator


def test_smrlv12_ap242_reference_is_complete_and_convertible():
    root = Path("D:/Githuv_repo/smrlv12")
    if not root.is_dir():
        return  # External reference is intentionally optional in CI.
    result = AP242ReferenceValidator(root).validate()
    assert result["valid"] is True
    assert len(result["assets"]["mim_long_form"]["sha256"]) == 64
    assert result["conversion"]["statistics"]["entity_count"] >= 2000
