from backend.qif.standards import detect_standard, get_standard, public_standards
from fastapi.testclient import TestClient
from backend.qif.app import app


def test_multi_xsd_standard_profiles_cover_engineering_standards():
    identifiers = {profile["id"] for profile in public_standards()}
    assert {"qif-3", "ap242", "ap239", "ap243", "plmxml", "generic-xsd"} <= identifiers
    assert detect_standard(["AP242Model.xsd", "common.xsd"]) == "ap242"
    assert detect_standard(["customer-extension.xsd"]) == "generic-xsd"
    assert get_standard("plmxml")["prefix"] == "plmxml"


def test_schema_set_api_exposes_profiles():
    response = TestClient(app).get("/api/v1/qif/schema-sets/standards")
    assert response.status_code == 200
    assert response.json()["count"] >= 8
