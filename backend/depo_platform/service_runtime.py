"""Small, dependency-light FastAPI service factory.

The factory follows the lifecycle and request-correlation conventions used by
the supplied PDF Intelligence reference, without introducing a task queue.
"""
from __future__ import annotations

from backend.depo_platform.request_bodies import BrowserSessionBody, RotateCredentialBody

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
            from .postgres_schema import connect_timeout_seconds, statement_options
            with psycopg.connect(database_url, connect_timeout=connect_timeout_seconds(), options=statement_options()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            status["postgres"] = {"status": "ready"}
        except Exception as exc:
            status["postgres"] = {"status": "unavailable", "reason": type(exc).__name__}
    neo4j_uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL")
    if "neo4j" in dependencies and neo4j_uri:
        try:
            from neo4j import GraphDatabase, Query
            from backend.core.db_config import get_config, _driver_kwargs
            from .network import bounded_timeout_seconds
            config = get_config()
            probe_timeout = bounded_timeout_seconds('DEPO_READINESS_TIMEOUT_SECONDS', default=3, maximum=30)
            options = _driver_kwargs(config)
            options.update(connection_timeout=probe_timeout, connection_acquisition_timeout=probe_timeout, max_transaction_retry_time=0)
            auth = None if config.auth_mode == 'none' else (config.username, config.password)
            with GraphDatabase.driver(
                neo4j_uri,
                auth=auth,
                **options,
            ) as driver:
                driver.verify_connectivity()
                with driver.session(database=config.database) as session:
                    session.run(Query("RETURN 1", timeout=probe_timeout)).consume()
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
        from .credentials import PROFILES
        check = app.openapi_schema.get('paths', {}).get('/auth/credential-check', {}).get('get')
        if check is not None:
            check['x-depo-credential-check'] = {'profile_parameter': 'profile', 'supported_profiles': sorted(PROFILES - {'GRAPH_READ_TOKEN'}), 'mutates': False}
            check['security'] = [{'BearerKey': []}, {'ApiKey': []}]
        for path, method in [('/auth/browser-session', 'post'), ('/auth/credentials', 'get'), ('/auth/admin-access', 'get'), ('/auth/credentials/{profile}', 'post'), ('/auth/credentials/{profile}', 'delete')]:
            operation = app.openapi_schema.get('paths', {}).get(path, {}).get(method)
            if operation is not None:
                operation['security'] = [{'ApiKey': []}]
                operation['x-depo-authorization'] = {'credential_profiles': ['ADMIN_API_KEY'], 'resolution': 'explicit'}
        renewal = app.openapi_schema.get('paths', {}).get('/auth/browser-session/renew', {}).get('post')
        if renewal is not None:
            renewal['security'] = [{'BearerKey': []}]
            renewal['x-depo-authorization'] = {'credential_profiles': ['GRAPH_READ_TOKEN'], 'resolution': 'explicit', 'browser_session_only': True}
        return app.openapi_schema
    app.openapi = compatible_openapi
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID", "X-Session-ID", "Ocp-Apim-Subscription-Key"],
        expose_headers=["Content-Disposition", "X-Request-ID", "X-Session-ID", "X-Session-Expires-At", "X-DEPO-Run-ID", "X-DEPO-Run-Kind", "OData-Version"],
    )

    from .authorization import graph_read_identity

    @app.get('/auth/credential-check', summary='Validate a workflow credential without executing a write')
    def credential_check(request: Request, profile: str) -> dict[str, str]:
        from fastapi import HTTPException
        from .authorization import service_write_identity
        if profile not in {'DATA_JOB_EXECUTION_TOKEN', 'SPEED_PATH_APPROVAL_TOKEN', 'ADMIN_API_KEY', 'GRAPH_PUBLICATION_TOKEN', 'DATA_PRODUCT_APPROVAL_TOKEN', 'CEIM_RESOLUTION_APPROVAL_TOKEN', 'CATALOG_SERVICE_TOKEN', 'DATA_JOB_APPROVAL_TOKEN', 'ARTIFACT_RETENTION_APPROVAL_TOKEN', 'CEIM_PUBLISH_APPROVAL_TOKEN', 'INGESTION_WRITE_TOKEN', 'AGENTIC_APPROVAL_TOKEN', 'ONTOLOGY_APPROVAL_TOKEN', 'SPEED_EVENT_TOKEN', 'SPARQL_FEDERATION_APPROVAL_TOKEN', 'VOCABULARY_APPROVAL_TOKEN'}:
            raise HTTPException(422, 'Unsupported credential profile')
        if profile == 'ADMIN_API_KEY':
            # Async admin validation is provided by the dedicated endpoint below.
            raise HTTPException(422, 'Use /auth/admin-access for ADMIN_API_KEY')
        service_write_identity(request, token_env=profile, default_actor='credential-check')
        return {'status': 'authorized', 'profile': profile}

    @app.get('/auth/admin-access')
    async def admin_access(request: Request):
        from backend.routes.admin_routes import require_admin_api_key
        await require_admin_api_key(request)
        return {'status': 'authorized', 'profile': 'ADMIN_API_KEY'}

    @app.post('/auth/credentials/{profile}')
    async def rotate_credential(profile: str, payload: RotateCredentialBody, request: Request):
        from fastapi import HTTPException
        from datetime import datetime
        from .credentials import uses_postgres, verify_key, register_key
        if not uses_postgres():
            raise HTTPException(409, 'Enable DEPO_CREDENTIAL_STORE=postgres and initialize the schema first')
        actor = verify_key('ADMIN_API_KEY', request.headers.get('x-api-key', ''))
        try:
            expiry = datetime.fromisoformat(str(payload['expires_at']).replace('Z', '+00:00')) if payload.get('expires_at') else None
            register_key(profile, payload.get('key', ''), payload.get('actor', ''), expiry, audit_actor=actor)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {'status': 'registered', 'profile': profile}

    @app.post('/auth/browser-session', summary='Connect registered service scopes for fifteen minutes')
    def browser_session(request: Request, payload: BrowserSessionBody):
        from fastapi import HTTPException
        from .credentials import uses_postgres
        from .browser_credentials import create_session
        if os.getenv('AUTH_MODE', 'token').lower() != 'token' or not uses_postgres():
            raise HTTPException(409, 'Browser service sessions require token authentication and PostgreSQL credential storage')
        include_writes = payload.get('include_writes', False)
        if type(include_writes) is not bool:
            raise HTTPException(422, 'include_writes must be a boolean')
        include_maintenance = payload.get('include_maintenance', False)
        if type(include_maintenance) is not bool:
            raise HTTPException(422, 'include_maintenance must be a boolean')
        return JSONResponse(content=create_session(request.headers.get('x-api-key', ''), include_writes, include_maintenance), headers={'Cache-Control': 'no-store'})

    @app.delete('/auth/browser-session', summary='Disconnect this browser service session')
    def disconnect_browser_session(request: Request):
        from .browser_credentials import delete_session
        header = request.headers.get('authorization', '')
        delete_session(header[7:].strip() if header.lower().startswith('bearer ') else '')
        return {'status': 'disconnected'}

    @app.post('/auth/browser-session/renew', summary='Renew an active browser session within its absolute lifetime')
    def renew_browser_session(request: Request):
        from fastapi import HTTPException
        from .credentials import uses_postgres
        from .browser_credentials import renew_session
        if os.getenv('AUTH_MODE', 'token').lower() != 'token' or not uses_postgres():
            raise HTTPException(409, 'Renewal requires token authentication and PostgreSQL credential storage')
        header = request.headers.get('authorization', '')
        token = header[7:].strip() if header.lower().startswith('bearer ') else ''
        return JSONResponse(content=renew_session(token), headers={'Cache-Control': 'no-store'})

    @app.get('/auth/credentials')
    def credential_status(request: Request):
        from fastapi import HTTPException
        from .credentials import uses_postgres, verify_key, connection
        if not uses_postgres():
            raise HTTPException(409, 'Central credentials are not enabled')
        verify_key('ADMIN_API_KEY', request.headers.get('x-api-key', ''))
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT profile,actor,expires_at,revoked,updated_at FROM depo_api_credentials ORDER BY profile')
            return {'profiles': [{'profile': row[0], 'actor': row[1], 'expires_at': row[2], 'revoked': row[3], 'updated_at': row[4]} for row in cursor.fetchall()]}

    @app.delete('/auth/credentials/{profile}')
    def revoke_credential(profile: str, request: Request):
        from fastapi import HTTPException
        from .credentials import uses_postgres, verify_key, connection, PROFILES
        if not uses_postgres():
            raise HTTPException(409, 'Central credentials are not enabled')
        actor = verify_key('ADMIN_API_KEY', request.headers.get('x-api-key', ''))
        if profile not in PROFILES or profile == 'ADMIN_API_KEY':
            raise HTTPException(422, 'Unknown profile or administrator revocation would lock out recovery; rotate the admin key instead')
        with connection() as db, db.transaction(), db.cursor() as cursor:
            cursor.execute('UPDATE depo_api_credentials SET revoked=true,updated_at=now() WHERE profile=%s', (profile,))
            if not cursor.rowcount:
                raise HTTPException(404, 'Credential profile not registered')
            cursor.execute('INSERT INTO depo_api_credential_events(profile,action,actor) VALUES (%s,%s,%s)', (profile, 'revoke', actor))
        return {'status': 'revoked', 'profile': profile}

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
