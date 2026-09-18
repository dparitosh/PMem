from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
app = create_service_app(title="DEPO Data Catalog Service", version="1.0.0")
app.include_router(create_odata_catalog_router(service_name="DEPODataCatalog", capabilities=[ServiceCapability("Data products", "/api/v1/catalog/products", description="Discover governed product versions"), ServiceCapability("Product history", "/api/v1/catalog/products/{product_id}", description="Read immutable product versions and latest pointer"), ServiceCapability("Register product version", "/api/v1/catalog/products/{product_id}/versions/{version}", "PUT", "Register an approved immutable product version"), ServiceCapability("Artifact retention", "/api/v1/catalog/artifacts/retention", description="Read governed retention, tier, legal-hold and purge evidence")]))
app.include_router(router, prefix="/api/v1")
