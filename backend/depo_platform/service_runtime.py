"""Small, dependency-light FastAPI service factory.

The factory follows the lifecycle and request-correlation conventions used by
the supplied PDF Intelligence reference, without introducing a task queue.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from collections.abc import Collection
from typing import AsyncIterator, Callable

from fastapi import Depends, FastAPI, Request
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
    from urllib.parse import urlsplit
    configured = os.getenv("ALLOWED_ORIGINS", "")
    origins = list(dict.fromkeys(origin.strip() for origin in configured.split(',') if origin.strip()))
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            parsed.port
            valid = (parsed.scheme in {'http', 'https'} and parsed.hostname
                     and not parsed.username and not parsed.password and not parsed.path
                     and not parsed.query and not parsed.fragment and '*' not in origin
                     and not any(char in origin for char in '<>\\')
                     and not any(char.isspace() for char in origin))
        except ValueError:
            valid = False
        if not valid:
            raise RuntimeError('ALLOWED_ORIGINS must contain exact HTTP/HTTPS origins without paths or wildcards')
    return origins


def configured_dependency_status(dependencies: Collection[str] = ("postgres", "neo4j")) -> dict[str, dict[str, str]]:
    """Perform small, bounded checks for configured shared dependencies.

    The checks intentionally only run when their connection configuration is
    present.  This keeps a service that does not own a dependency deployable,
    while preventing a configured but unavailable PostgreSQL/Neo4j plane from
    being advertised as ready.
    """
    status: dict[str, dict[str, str]] = {}
    production = any(os.getenv(key, '').strip().lower() in {'prod', 'production'}
                     for key in ('DEPO_ENV', 'ENVIRONMENT', 'APP_ENV', 'DEPLOYMENT_ENV'))
    database_url = os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL")
    if "postgres" in dependencies and database_url:
        try:
            import psycopg
            with psycopg.connect(database_url, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            status["postgres"] = {"status": "ready"}
        except Exception as exc:
            status["postgres"] = {"status": "unavailable", "reason": type(exc).__name__}
    neo4j_uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL")
    if "neo4j" in dependencies and neo4j_uri:
        try:
            from neo4j import GraphDatabase, Query
            auth = None if os.getenv("NEO4J_AUTH_MODE", "token").lower() == "none" else (
                os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", ""), os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD", "")
            )
            with GraphDatabase.driver(
                neo4j_uri,
                auth=auth,
                connection_timeout=3,
                max_transaction_retry_time=0,
            ) as driver:
                driver.verify_connectivity()
                with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
                    session.run(Query("RETURN 1", timeout=3)).consume()
            status["neo4j"] = {"status": "ready"}
        except Exception as exc:
            status["neo4j"] = {"status": "unavailable", "reason": type(exc).__name__}
    if production:
        for dependency in dependencies:
            if dependency not in status:
                status[dependency] = {"status": "unavailable", "reason": "MissingConfiguration"}
    return status


def create_service_app(
    *,
    title: str,
    version: str,
    lifespan_hook: Callable[[], AsyncIterator[None]] | None = None,
    readiness_check: Callable | None = None,
    dependencies: Collection[str] = ("postgres", "neo4j"),
) -> FastAPI:
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
    from .openapi_contract import normalize_openapi, describe_security
    original_openapi = app.openapi
    def compatible_openapi():
        app.openapi_schema = describe_security(normalize_openapi(original_openapi()), app.routes)
        return app.openapi_schema
    app.openapi = compatible_openapi
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID", "X-Session-ID", "Ocp-Apim-Subscription-Key"],
        expose_headers=["X-Request-ID", "X-Session-ID", "X-Session-Expires-At", "X-DEPO-Run-ID", "OData-Version"],
    )

    from .authorization import graph_read_identity

    @app.get("/auth/access", summary="Verify service read authentication without querying shared stores")
    def authenticated_access(identity: str = Depends(graph_read_identity)) -> dict[str, str]:
        return {"status": "authorized", "service": title}

    @app.get("/healthz", include_in_schema=False)
    def liveness() -> dict[str, str]:
        """Process liveness probe; never depends on an external dependency."""
        return {"status": "ok", "service": title, "version": version}

    @app.get("/readyz", include_in_schema=False)
    def readiness() -> JSONResponse:
        dependencies = readiness_check() if readiness_check else {}
        if not any(item['status'] != 'ready' for item in dependencies.values()):
            dependencies.update(configured_dependency_status(dependencies=dependencies_to_check))
        unavailable = [name for name, item in dependencies.items() if item["status"] != "ready"]
        body = {
            "status": "not_ready" if unavailable else "ready",
            "service": title,
            "version": version,
            "dependencies": dependencies,
        }
        return JSONResponse(status_code=503 if unavailable else 200, content=body)

    dependencies_to_check = tuple(dependencies)
    unsupported = set(dependencies_to_check) - {"postgres", "neo4j"}
    if unsupported:
        raise ValueError(f"Unsupported readiness dependencies: {sorted(unsupported)}")
    return app
