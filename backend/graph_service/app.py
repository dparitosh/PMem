"""Standalone graph service entry point.

Run: python -m uvicorn backend.graph_service.app:app --port 8013
"""
from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
from .context_router import router as context_router
from .graphql_router import router as graphql_router
from .sparql_router import router as sparql_router
from .federation_router import router as federation_router

app = create_service_app(title="DEPO Graph Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOGraph",
    capabilities=[
        ServiceCapability("Health", "/api/v1/graph/health", description="Graph service health"),
        ServiceCapability("Explorer overview", "/api/v1/graph/overview", description="Retrieve a bounded explorer-ready graph view"),
        ServiceCapability("Graph search", "/api/v1/graph/search", description="Retrieve score-ranked semantic resources through a bounded parameterized query"),
        ServiceCapability("Ontology projection", "/api/v1/graph/ontologies/{ontology_id}/projection", description="Retrieve a bounded ontology graph view"),
        ServiceCapability("Graph traversal", "/api/v1/graph/traversal/{iri}", description="Retrieve a bounded RDF-resource neighborhood"),
        ServiceCapability("Publish ontology", "/api/v1/graph/ontologies/publish", "POST", "Publish a Turtle ontology to the graph"),
        ServiceCapability("Ontology analytics", "/api/v1/graph/ontologies/{ontology_id}/analytics", description="Analyze a live ontology graph"),
        ServiceCapability("Ontology neighborhood", "/api/v1/graph/ontologies/{ontology_id}/neighborhood", description="Retrieve bounded ontology neighbors"),
        ServiceCapability("Change impact", "/recommendations/change-impact", "POST", "Trace bounded semantic impact from the graph"),
        ServiceCapability("Similarity recommendations", "/recommendations/similar-parts", "POST", "Find graph terms with lexical and type similarity"),
        ServiceCapability("Manufacturing context", "/recommendations/manufacturing", "POST", "Find manufacturing process context from the graph"),
        ServiceCapability("GraphQL read API", "/api/v1/graphql", "POST", "Read bounded graph projections, governed Spark job manifests, and data-product manifests"),
        ServiceCapability("SPARQL read API", "/api/v1/sparql", "POST", "Execute bounded SELECT/ASK queries over one governed ontology projection"),
        ServiceCapability("SPARQL federation peers", "/api/v1/sparql/federation/peers", "POST", "Register and approve an allow-listed HTTPS SPARQL peer"),
    ],
))
app.include_router(router, prefix="/api/v1")
app.include_router(context_router)
app.include_router(graphql_router)
app.include_router(sparql_router)
app.include_router(federation_router)

from .bridge_router import router as bridge_router
app.include_router(bridge_router, prefix="/api/v1")
