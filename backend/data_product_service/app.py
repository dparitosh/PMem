from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
app = create_service_app(title="DEPO Data Product Service", version="1.0.0")
app.include_router(create_odata_catalog_router(service_name="DEPODataProducts", capabilities=[ServiceCapability("Preview", "/api/v1/data-products/preview", "POST", "Validate immutable artifact references and product contract"), ServiceCapability("Publish", "/api/v1/data-products/publish", "POST", "Package and publish an approved data product"), ServiceCapability("Reconcile", "/api/v1/data-products/reconcile", "POST", "Reconcile durable pending catalog registrations"), ServiceCapability("Retry catalog", "/api/v1/data-products/{product_version}/retry-catalog", "POST", "Retry an outbox-style catalog registration"), ServiceCapability("Manifest", "/api/v1/data-products/{product_version}/manifest", description="Read immutable package manifest"), ServiceCapability("Download", "/api/v1/data-products/{product_version}/download", description="Download immutable product package")]))
app.include_router(router, prefix="/api/v1")
