from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
app = create_service_app(title="DEPO Data Product Service", version="1.0.0")
app.include_router(create_odata_catalog_router(service_name="DEPODataProducts", capabilities=[ServiceCapability("Preview", "/api/v1/data-products/preview", "POST", "Validate product contract and lineage"), ServiceCapability("Publish", "/api/v1/data-products/publish", "POST", "Publish approved data product"), ServiceCapability("Data products", "/api/v1/data-products", description="List product versions")]))
app.include_router(router, prefix="/api/v1")
