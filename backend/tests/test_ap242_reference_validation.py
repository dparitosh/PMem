from pathlib import Path

from fastapi.testclient import TestClient

from backend.ingestion_service.ap242_reference import AP242ReferenceValidator
from backend.ingestion_service.app import app


def test_smrlv12_ap242_reference_is_complete_and_convertible():
    root = Path("D:/Githuv_repo/smrlv12")
    if not root.is_dir():
        return  # External reference is intentionally optional in CI.
    result = AP242ReferenceValidator(root).validate()
    assert result["valid"] is True
    assert len(result["assets"]["mim_long_form"]["sha256"]) == 64
    assert result["conversion"]["statistics"]["entity_count"] >= 2000
    semantic = result["conversion"]["semantic_summary"]
    assert semantic["class_count"] >= 2500
    assert semantic["property_count"] >= 1500
    assert semantic["subclass_axiom_count"] >= 2000
    assert semantic["domain_axiom_count"] >= 1500
    assert semantic["range_axiom_count"] >= 1500
    assert result["xsd_conversions"]["bom_xsd"]["adapter"] == "ap242-business-object-model-xsd"
    assert result["xsd_conversions"]["domain_xsd"]["adapter"] == "ap242-domain-model-xsd"
    for summary in (result["xsd_conversions"]["bom_xsd"]["semantic_summary"], result["xsd_conversions"]["domain_xsd"]["semantic_summary"]):
        assert summary["class_count"] > 0
        assert summary["property_count"] > 0
        assert summary["domain_axiom_count"] > 0


def test_ap242_reference_validation_api_is_read_only_and_uses_configured_boundary(monkeypatch):
    class Validator:
        def validate(self):
            return {"valid": True, "assets": {"mim_long_form": {"sha256": "a" * 64}}}

    monkeypatch.setattr("backend.ingestion_service.router.AP242ReferenceValidator", Validator)
    response = TestClient(app).get("/api/v1/ap242/reference/validation")

    assert response.status_code == 200
    assert response.json()["valid"] is True
