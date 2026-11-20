"""Standalone OSLC server/client. Run on port 8015."""
from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from backend.routes.oslc_routes import router as server_router
from .router import router as client_router
from .lifecycle import router as lifecycle_router
from .change_control import router as change_control_router
from .change_commands import router as change_commands_router
from .release_changes import router as release_changes_router
from .automation import router as automation_router

# Lifecycle resources and the default TRS store are PostgreSQL-backed. Keep
# readiness aligned with the capabilities advertised by this service.
app = create_service_app(title="DEPO OSLC Service", version="1.0.0", dependencies=("postgres", "neo4j"))
app.include_router(create_odata_catalog_router(
    service_name="DEPOOSLC",
    capabilities=[
        ServiceCapability("OSLC lifecycle capabilities", "/api/v1/oslc/capabilities", description="Service-wide tracking, frozen baseline and retained automation evidence"),
        ServiceCapability("Frozen release configurations", "/oslc/change-control/configurations", description="Read-only paginated release baseline collection"),
        ServiceCapability("Workflow automation discovery", "/oslc/automation", description="Discover retained workflow plans, requests and execution results"),
        ServiceCapability("Automation request", "/oslc/automation/requests", "POST", "Submit authorized retained-input replay to the existing worker"),
        ServiceCapability("Source-to-release request", "/api/v1/change-control/releases", "POST", "Freeze exact source evidence and ordered native operation scopes in one CR"),
        ServiceCapability("Source-to-release coordination", "/api/v1/change-control/releases/{identifier}", "POST", "Review, authorize, rebase or verify a coordinated native release"),
        ServiceCapability("Release configuration", "/oslc/change-control/configurations/{identifier}", description="Read immutable configuration selections and context"),
        ServiceCapability("Health", "/api/v1/oslc/health", description="OSLC service health"),
        ServiceCapability("Remote catalog", "/api/v1/oslc/remote/catalog", description="Discover a configured OSLC provider catalog"),
        ServiceCapability("Remote query", "/api/v1/oslc/remote/query/{resource_type}", "POST", "Query a configured OSLC provider"),
        ServiceCapability("Stage remote sync", "/api/v1/oslc/remote/sync/{resource_type}", "POST", "Pull and stage a remote OSLC snapshot"),
        ServiceCapability("OSLC server catalog", "/oslc/catalog", description="DEPO OSLC service provider catalog"),
        ServiceCapability("Ontology publication request", "/api/v1/change-control/publications/{ontology_id}/request", description="Inspect the native reviewed ontology release"),
        ServiceCapability("Ontology publication command", "/api/v1/change-control/publications/{ontology_id}/request", "POST", "Route verified decisions to the native publication queue"),
        ServiceCapability("Pipeline publication request", "/api/v1/change-control/pipeline/{run_id}/request", description="Inspect retained accepted partition scope"),
        ServiceCapability("Pipeline publication command", "/api/v1/change-control/pipeline/{run_id}/request", "POST", "Route verified partition publication decisions to its native service"),
        ServiceCapability("Product release request", "/api/v1/change-control/product_changes/{product_version}/request", description="Inspect exact native product release scope"),
        ServiceCapability("Product release command", "/api/v1/change-control/product_changes/{product_version}/request", "POST", "Route verified release decisions and delivery reconciliation"),
        ServiceCapability("Mapping change request", "/api/v1/change-control/bridges/{preview_id}/request", description="Read retained mapping candidate scope and request state"),
        ServiceCapability("Mapping change command", "/api/v1/change-control/bridges/{preview_id}/request", "POST", "Route verified mapping review and publication decisions to the native service"),
        ServiceCapability("Merge change request", "/api/v1/change-control/merges/{preview_id}/request", description="Read the native retained merge request and exact draft scope"),
        ServiceCapability("Merge change command", "/api/v1/change-control/merges/{preview_id}/request", "POST", "Submit, review and authorize a native merged draft with verified approval access"),
        ServiceCapability("Change control evidence", "/api/v1/change-control/records", description="Read retained review, execution and delivery evidence across workspaces"),
    ],
))
app.include_router(server_router)
app.include_router(lifecycle_router)
app.include_router(change_control_router)
app.include_router(change_commands_router)
app.include_router(client_router, prefix="/api/v1")

app.include_router(release_changes_router)

app.include_router(automation_router)
