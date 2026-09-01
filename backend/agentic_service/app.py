from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
app = create_service_app(title="DEPO Agentic Control Plane", version="1.0.0")
app.include_router(create_odata_catalog_router(service_name="DEPOAgentic", capabilities=[ServiceCapability("Agents", "/api/v1/agents"), ServiceCapability("Tools", "/api/v1/tools"), ServiceCapability("Plans", "/api/v1/plans", "POST", "Validate agent tool invocation")]))
app.include_router(router)
