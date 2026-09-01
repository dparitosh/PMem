"""Standalone graph service entry point.

Run: python -m uvicorn backend.graph_service.app:app --port 8013
"""
from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router

app = create_service_app(title="DEPO Graph Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOGraph",
    capabilities=[
        ServiceCapability("Health", "/api/v1/graph/health", description="Graph service health"),
        ServiceCapability("Publish ontology", "/api/v1/graph/ontologies/publish", "POST", "Publish a Turtle ontology to the graph"),
        ServiceCapability("Ontology analytics", "/api/v1/graph/ontologies/{ontology_id}/analytics", description="Analyze a live ontology graph"),
        ServiceCapability("Ontology neighborhood", "/api/v1/graph/ontologies/{ontology_id}/neighborhood", description="Retrieve bounded ontology neighbors"),
    ],
))
app.include_router(router, prefix="/api/v1")
