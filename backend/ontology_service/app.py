"""Standalone ontology service entry point.

Run: python -m uvicorn backend.ontology_service.app:app --port 8011
"""
from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router

app = create_service_app(title="DEPO Ontology Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOOntology",
    capabilities=[
        ServiceCapability("Health", "/api/v1/ontologies/health", description="Ontology service health"),
        ServiceCapability("Generate ontology", "/api/v1/ontologies/generate", "POST", "Generate and validate an ontology"),
        ServiceCapability("Quality gate", "/api/v1/ontologies/quality-gate", "POST", "Run governed quality checks"),
        ServiceCapability("Ontology versions", "/api/v1/ontologies/versions", description="List ontology versions"),
        ServiceCapability("Policy evaluation", "/api/v1/ontologies/policies/evaluate", "POST", "Evaluate publication policies"),
        ServiceCapability("Governed merge preview", "/api/v1/ontologies/merges/preview", "POST", "Review an ontology merge before approval"),
        ServiceCapability("Approved ontology merge", "/api/v1/ontologies/merges/{preview_id}/apply", "POST", "Persist an approved merge with provenance"),
    ],
))
app.include_router(router, prefix="/api/v1")
