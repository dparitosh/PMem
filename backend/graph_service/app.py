"""Standalone graph service entry point.

Run: python -m uvicorn backend.graph_service.app:app --port 8013
"""
from backend.platform.service_runtime import create_service_app
from .router import router

app = create_service_app(title="DEPO Graph Service", version="1.0.0")
app.include_router(router, prefix="/api/v1")
