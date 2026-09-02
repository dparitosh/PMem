"""Standalone graph service entry point.

Run: python -m uvicorn backend.graph_service.app:app --port 8013
"""
from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
from .context_router import router as context_router

app = create_service_app(title="DEPO Graph Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOGraph",
    capabilities=[
        ServiceCapability("Health", "/api/v1/graph/health", description="Graph service health"),
        ServiceCapability("Explorer overview", "/api/v1/graph/overview", description="Retrieve a bounded explorer-ready graph view"),
        ServiceCapability("Ontology projection", "/api/v1/graph/ontologies/{ontology_id}/projection", description="Retrieve a bounded ontology graph view"),
        ServiceCapability("Graph traversal", "/api/v1/graph/traversal/{iri}", description="Retrieve a bounded RDF-resource neighborhood"),
        ServiceCapability("Publish ontology", "/api/v1/graph/ontologies/publish", "POST", "Publish a Turtle ontology to the graph"),
        ServiceCapability("Ontology analytics", "/api/v1/graph/ontologies/{ontology_id}/analytics", description="Analyze a live ontology graph"),
        ServiceCapability("Ontology neighborhood", "/api/v1/graph/ontologies/{ontology_id}/neighborhood", description="Retrieve bounded ontology neighbors"),
        ServiceCapability("Change impact", "/recommendations/change-impact", "POST", "Trace bounded semantic impact from the graph"),
        ServiceCapability("Similarity recommendations", "/recommendations/similar-parts", "POST", "Find graph terms with lexical and type similarity"),
        ServiceCapability("Manufacturing context", "/recommendations/manufacturing", "POST", "Find manufacturing process context from the graph"),
    ],
))
app.include_router(router, prefix="/api/v1")
app.include_router(context_router)
