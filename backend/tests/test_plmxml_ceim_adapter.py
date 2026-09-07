from pathlib import Path

from backend.ceim.contract import contract
from backend.ceim.plmxml_adapter import plmxml_to_ceim_batch
from backend.ceim_service.app import app
from fastapi.testclient import TestClient


FIXTURE = Path("D:/Githuv_repo/PLMXML/EBOM-Export/Motor_EBOM.xml")


def test_teamcenter_plmxml_normalizes_to_a_valid_ceim_batch():
    if not FIXTURE.is_file():
        return
    batch = plmxml_to_ceim_batch(FIXTURE.read_bytes())
    assert batch["standard"] == "plmxml"
    assert batch["source_summary"]["parts"] > 0
    assert batch["entities"]
    assert batch["relationships"]
    report = contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])
    assert report["conforms"] is True


def test_teamcenter_plmxml_adapter_is_registered_in_the_openapi_service():
    if not FIXTURE.is_file():
        return
    response = TestClient(app).post(
        "/api/v1/ceim/adapters/plmxml/normalize",
        files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "application/xml")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["standard"] == "plmxml"
    assert payload["representation"] == "normalized-ceim-v1"
    assert payload["source_artifact_id"].startswith("sha256:")
