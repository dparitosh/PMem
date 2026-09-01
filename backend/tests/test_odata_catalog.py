from fastapi.testclient import TestClient

from backend.graph_service.app import app as graph_app
from backend.ingestion_service.app import app as ingestion_app
from backend.ontology_service.app import app as ontology_app
from backend.oslc_service.app import app as oslc_app


def test_every_standalone_service_exposes_an_odata_v4_catalog():
    for app in (ontology_app, graph_app, ingestion_app, oslc_app):
        client = TestClient(app)
        document = client.get("/odata")
        metadata = client.get("/odata/$metadata")
        capabilities = client.get("/odata/ServiceCapabilities?$count=true")

        assert document.status_code == 200
        assert document.json()["value"][0]["name"] == "ServiceCapabilities"
        assert metadata.status_code == 200
        assert "EntitySet Name=\"ServiceCapabilities\"" in metadata.text
        assert capabilities.status_code == 200
        assert capabilities.json()["@odata.count"] > 0
