from fastapi.testclient import TestClient

from backend.qif.app import app as qif_app
from backend.depo_platform.service_runtime import create_service_app


def test_service_factory_emits_openapi_303() -> None:
    assert create_service_app(title="Contract test", version="1.0.0").openapi()["openapi"] == "3.0.3"


def test_qif_service_exposes_odata_metadata() -> None:
    with TestClient(qif_app) as client:
        response = client.get("/odata/$metadata")
    assert response.status_code == 200
    assert 'Version="4.0"' in response.text
