"""Run with: python -m uvicorn backend.ingestion_service.app:app --port 8014."""
from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router

app = create_service_app(title="DEPO Ingestion Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOIngestion",
    capabilities=[
        ServiceCapability("Health", "/ingestion/health", description="Ingestion service health"),
        ServiceCapability("Source profiles", "/source-profiles", description="List reusable ingestion profiles"),
        ServiceCapability("Inspect source", "/source-profiles/inspect", "POST", "Inspect a source schema or sample"),
        ServiceCapability("Engineering schema conversion", "/schema-conversions/inspect", "POST", "Convert EXPRESS, STEP, XMI, or XSD to Turtle"),
        ServiceCapability("Engineering workflow", "/engineering-workflows", "POST", "Convert and register through the ontology service"),
        ServiceCapability("Execute profile", "/source-profiles/{profile_id}/workflow", "POST", "Run governed profile ingestion"),
    ],
))
app.include_router(router, prefix="/api/v1")
