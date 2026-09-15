"""Standalone OSLC server/client. Run on port 8015."""
from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from backend.routes.oslc_routes import router as server_router
from .router import router as client_router
from .lifecycle import router as lifecycle_router

app = create_service_app(title="DEPO OSLC Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOOSLC",
    capabilities=[
        ServiceCapability("Health", "/api/v1/oslc/health", description="OSLC service health"),
        ServiceCapability("Remote catalog", "/api/v1/oslc/remote/catalog", description="Discover a configured OSLC provider catalog"),
        ServiceCapability("Remote query", "/api/v1/oslc/remote/query/{resource_type}", "POST", "Query a configured OSLC provider"),
        ServiceCapability("Stage remote sync", "/api/v1/oslc/remote/sync/{resource_type}", "POST", "Pull and stage a remote OSLC snapshot"),
        ServiceCapability("Stage remote sync", "/api/v1/oslc/remote/sync/{resource_type}", "POST", "Pull and stage a remote OSLC snapshot"),
        ServiceCapability("OSLC server catalog", "/oslc/catalog", description="DEPO OSLC service provider catalog"),
    ],
))
app.include_router(server_router)
app.include_router(lifecycle_router)
app.include_router(client_router, prefix="/api/v1")
