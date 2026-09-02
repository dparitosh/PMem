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
    def readiness() -> dict[str, str]:
        """HTTP readiness probe for orchestration.

        Dependency-specific readiness remains available from each service's
        explicit health endpoint so a slow remote graph does not restart an
        otherwise healthy API process.
        """
        return {"status": "ready", "service": title, "version": version}

    return app
