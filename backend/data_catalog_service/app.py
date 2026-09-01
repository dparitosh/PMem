from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
app = create_service_app(title="DEPO Data Catalog Service", version="1.0.0")
app.include_router(create_odata_catalog_router(service_name="DEPODataCatalog", capabilities=[ServiceCapability("Data products", "/api/v1/catalog/products", description="Discover governed data products"), ServiceCapability("Product version", "/api/v1/catalog/products/{product_id}", description="Read product versions")]))
app.include_router(router, prefix="/api/v1")
