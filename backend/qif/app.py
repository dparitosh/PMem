"""Standalone QIF microservice entry point.

Run with: ``python -m uvicorn backend.qif.app:app --port 8010``.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .router import router

app = FastAPI(title="QIF Workflow Service", version="1.0.0", description="Task-based QIF schema-to-ontology processing service")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(router, prefix="/api/v1")
