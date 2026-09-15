"""Small, dependency-light FastAPI service factory.

The factory follows the lifecycle and request-correlation conventions used by
the supplied PDF Intelligence reference, without introducing a task queue.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propagate a client request id or add a new one to every response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def configured_dependency_status() -> dict[str, dict[str, str]]:
    """Perform small, bounded checks for configured shared dependencies.

    The checks intentionally only run when their connection configuration is
    present.  This keeps a service that does not own a dependency deployable,
    while preventing a configured but unavailable PostgreSQL/Neo4j plane from
    being advertised as ready.
    """
    status: dict[str, dict[str, str]] = {}
    database_url = os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL")
    if database_url:
        try:
            import psycopg
            with psycopg.connect(database_url, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            status["postgres"] = {"status": "ready"}
        except Exception as exc:
            status["postgres"] = {"status": "unavailable", "reason": type(exc).__name__}
    neo4j_uri = os.getenv("NEO4J_URI")
    if neo4j_uri:
        try:
            from neo4j import GraphDatabase
            with GraphDatabase.driver(
                neo4j_uri,
                auth=(os.getenv("NEO4J_USER", ""), os.getenv("NEO4J_PASS", "")),
                connection_timeout=3,
            ) as driver:
                driver.verify_connectivity()
            status["neo4j"] = {"status": "ready"}
        except Exception as exc:
            status["neo4j"] = {"status": "unavailable", "reason": type(exc).__name__}
    return status


def create_service_app(*, title: str, version: str, lifespan_hook: Callable[[], AsyncIterator[None]] | None = None) -> FastAPI:
    """Create a service with uniform CORS, lifecycle and correlation behavior."""

    lifespan = None
    if lifespan_hook is not None:
        @asynccontextmanager
        async def lifespan(_: FastAPI):
            async with lifespan_hook():
                yield

    # APIM registration is standardized on OpenAPI 3.0.x across all DEPO services.
    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.openapi_version = "3.0.3"
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )

    @app.get("/healthz", include_in_schema=False)
    def liveness() -> dict[str, str]:
        """Process liveness probe; never depends on an external dependency."""
        return {"status": "ok", "service": title, "version": version}

    @app.get("/readyz", include_in_schema=False)
    def readiness() -> JSONResponse:
        dependencies = configured_dependency_status()
        unavailable = [name for name, item in dependencies.items() if item["status"] != "ready"]
        body = {
            "status": "not_ready" if unavailable else "ready",
            "service": title,
            "version": version,
            "dependencies": dependencies,
        }
        return JSONResponse(status_code=503 if unavailable else 200, content=body)

    return app
