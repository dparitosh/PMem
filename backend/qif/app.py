"""Standalone engineering schema-set microservice entry point.

Run with: ``python -m uvicorn backend.qif.app:app --port 8010``.
"""
from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router

app = create_service_app(title="Engineering Schema-Set Service", version="1.0.0")
app.include_router(
    create_odata_catalog_router(
        service_name="DEPOEngineeringSchemaSets",
        capabilities=[
            ServiceCapability("Standards", "/api/v1/qif/schema-sets/standards", description="Discover bundled and generic engineering schema-set profiles"),
            ServiceCapability("Schema catalog", "/api/v1/qif/catalog", description="List bundled QIF reference schemas"),
            ServiceCapability("Schema-set upload", "/api/v1/qif/schema-sets/upload", "POST", "Create a generic multi-XSD ontology workflow"),
            ServiceCapability("Workflow tasks", "/api/v1/qif/tasks", description="List ontology-generation workflow tasks"),
        ],
    )
)
app.include_router(router, prefix="/api/v1")
