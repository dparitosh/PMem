"""Standalone ontology service entry point.

Run: python -m uvicorn backend.ontology_service.app:app --port 8011
"""
from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from backend.routes.admin_routes import router as admin_router
from backend.routes.metadata_registry_routes import router as metadata_registry_router
from backend.routes.ontology_routes import router as legacy_ontology_router
from .router import router
from .modeling_router import router as modeling_router

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
        ServiceCapability("Legacy catalog migration", "/api/v1/ontologies/migrations/legacy", "POST", "Adopt named legacy ingestion artifacts with stable IDs"),
        ServiceCapability("Legacy analytics backfill", "/api/v1/ontologies/migrations/legacy/analytics", "POST", "Add draft analytics and lifecycle metadata from retained ontology artifacts"),
        ServiceCapability("Register ontology artifact", "/api/v1/ontologies/register", "POST", "Syntax-validate and register a draft RDF/OWL artifact"),
        ServiceCapability("Ontology lifecycle", "/api/v1/ontologies/{ontology_id}/transition", "POST", "Move a draft ontology through review, approval, deprecation, or retirement"),
        ServiceCapability("Business-object context", "/api/v1/ontologies/business-context", "GET", "Inspect Semantica ContextGraph business-object context"),
        ServiceCapability("Semantic metadata registry", "/api/v1/metadata-registry/assets", "GET", "Discover governed semantic assets and releases"),
        ServiceCapability("Register semantic asset", "/api/v1/metadata-registry/assets", "POST", "Create a draft governed semantic asset"),
        ServiceCapability("Semantic asset lifecycle", "/api/v1/metadata-registry/assets/{asset_id}/transition", "POST", "Move an asset through review, approval, deprecation, or retirement with evidence"),
        ServiceCapability("Governed SKOS vocabularies", "/api/v1/ontologies/vocabularies", "GET", "Curate immutable vocabulary releases through steward review, approval, and publication"),
    ],
))
app.include_router(router, prefix="/api/v1")
app.include_router(modeling_router, prefix="/api/v1")
# The SPA still has a substantial, tested ontology-workbench surface on the
# historical `/api/v1/ontology/*` contract. Host that compatibility contract
# in the ontology service (rather than letting calls fall through to the
# retired aggregate application) while new lifecycle APIs use `/ontologies`.
app.include_router(legacy_ontology_router, prefix="/api/v1")
# The operational registry and its guarded maintenance actions own ontology
# graph administration.  Hosting them here prevents the frontend from falling
# back to the retired aggregate service on port 8000.
app.include_router(admin_router, prefix="/api/v1")
app.include_router(metadata_registry_router, prefix="/api/v1")
