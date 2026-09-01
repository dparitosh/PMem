"""Standalone engineering schema-set microservice entry point.

Run with: ``python -m uvicorn backend.qif.app:app --port 8010``.
"""
from backend.platform.service_runtime import create_service_app
from .router import router

app = create_service_app(title="Engineering Schema-Set Service", version="1.0.0")
app.include_router(router, prefix="/api/v1")
