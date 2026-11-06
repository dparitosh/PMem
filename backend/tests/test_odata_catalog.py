from fastapi.testclient import TestClient

from backend.graph_service.app import app as graph_app
from backend.ingestion_service.app import app as ingestion_app
from backend.ontology_service.app import app as ontology_app
from backend.oslc_service.app import app as oslc_app


def test_every_standalone_service_exposes_an_odata_v4_catalog():
    from backend.qif.app import app as qif_app
    from backend.agentic_service.app import app as agentic_app
    from backend.ceim_service.app import app as ceim_app
    from backend.data_catalog_service.app import app as catalog_app
    from backend.data_product_service.app import app as product_app
    from backend.data_pipeline_service.app import app as pipeline_app
    for app in (ontology_app, graph_app, ingestion_app, oslc_app, qif_app,
                agentic_app, ceim_app, catalog_app, product_app, pipeline_app):
        client = TestClient(app)
        document = client.get("/odata")
        metadata = client.get("/odata/$metadata")
        capabilities = client.get("/odata/ServiceCapabilities?$count=true")

        assert document.status_code == 200
        assert document.json()["value"][0]["name"] == "ServiceCapabilities"
        assert document.json()['@odata.context'] == 'http://testserver/odata/$metadata'
        assert client.get('/odata/').json()['@odata.context'] == document.json()['@odata.context']
        assert metadata.status_code == 200
        assert "EntitySet Name=\"ServiceCapabilities\"" in metadata.text
        assert capabilities.status_code == 200
        assert capabilities.json()["@odata.count"] > 0
