"""Standalone OSLC server/client. Run on port 8015."""
from backend.platform.service_runtime import create_service_app
from backend.routes.oslc_routes import router as server_router
from .router import router as client_router

app = create_service_app(title="DEPO OSLC Service", version="1.0.0")
app.include_router(server_router)
app.include_router(client_router, prefix="/api/v1")
