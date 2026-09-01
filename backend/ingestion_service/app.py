"""Run with: python -m uvicorn backend.ingestion_service.app:app --port 8014."""
from backend.platform.service_runtime import create_service_app
from .router import router

app = create_service_app(title="DEPO Ingestion Service", version="1.0.0")
app.include_router(router, prefix="/api/v1")
