"""Standalone ontology service entry point.

Run: python -m uvicorn backend.ontology_service.app:app --port 8011
"""
from backend.platform.service_runtime import create_service_app
from .router import router

app = create_service_app(title="DEPO Ontology Service", version="1.0.0")
app.include_router(router, prefix="/api/v1")
