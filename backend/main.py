from typing import Any, Dict
import os
import sys
import asyncio
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Request, APIRouter, Query, BackgroundTasks
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from starlette.concurrency import run_in_threadpool
import logging as _logging
from logging.handlers import RotatingFileHandler
import json
import re
from pathlib import Path as FileSystemPath

# ✅ Load environment variables from .env file
load_dotenv()

# 🔒 MEDIUM PRIORITY: Enhanced logging configuration
def setup_logging():
    """
    🔒 MEDIUM PRIORITY: Configure production-grade logging
    - Structured logging format
    - Sensitive data filtering
    - File rotation (max 10MB, keep 5 backups)
    - Separate error log
    """
    # Create logs directory
    logs_dir = 'logs'
    os.makedirs(logs_dir, exist_ok=True)
    
    # Logging format with timestamps and context
    formatter = _logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Root logger setup
    root_logger = _logging.getLogger()
    root_logger.setLevel(_logging.INFO)
    if root_logger.handlers:
        return root_logger
    
    # Console handler
    console_handler = _logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handlers are useful, but they must not prevent FastAPI startup if
    # Windows has a stale lock on a log file.
    for log_name, level in (('app.log', _logging.INFO), ('error.log', _logging.ERROR)):
        try:
            file_handler = RotatingFileHandler(
                os.path.join(logs_dir, log_name),
                maxBytes=10*1024*1024,
                backupCount=5
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except OSError as exc:
            root_logger.warning("File logging disabled for %s: %s", log_name, exc)
    
    return root_logger

logger = setup_logging()

try:
    from .Services.runtime_state_store import (
        allow_request as allow_shared_request,
        acquire_session_lease,
        delete_chat_job as delete_shared_chat_job,
        delete_session as delete_shared_session,
        get_chat_job as get_shared_chat_job,
        get_session as get_shared_session,
        list_chat_jobs as list_shared_chat_jobs,
        save_chat_job as save_shared_chat_job,
        save_session as save_shared_session,
        release_session_lease,
    )
except ImportError:
    from Services.runtime_state_store import (
        allow_request as allow_shared_request,
        acquire_session_lease,
        delete_chat_job as delete_shared_chat_job,
        delete_session as delete_shared_session,
        get_chat_job as get_shared_chat_job,
        get_session as get_shared_session,
        list_chat_jobs as list_shared_chat_jobs,
        save_chat_job as save_shared_chat_job,
        save_session as save_shared_session,
        release_session_lease,
    )

# Sensitive data patterns to filter from logs
SENSITIVE_PATTERNS = [
    r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
    r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
    r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
    r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
]

def sanitize_log_message(message: str) -> str:
    """🔒 Remove sensitive data from log messages"""
    if not isinstance(message, str):
        return str(message)
    
    for pattern in SENSITIVE_PATTERNS:
        message = re.sub(pattern, r'\1***REDACTED***', message, flags=re.IGNORECASE)
    
    return message

_CYPHER_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_cypher_identifier(value: str, *, default: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return default
    if not _CYPHER_IDENTIFIER_PATTERN.fullmatch(candidate):
        logger.warning("Unsafe Cypher identifier '%s' replaced with '%s'", candidate, default)
        return default
    return candidate


def _graph_service_unavailable(endpoint: str, exc: Exception) -> HTTPException:
    logger.warning("%s unavailable: %s", endpoint, exc)
    return HTTPException(
        status_code=503,
        detail={
            "status": "unavailable",
            "endpoint": endpoint,
            "message": str(exc),
        },
    )

_index_preparer = None
_index_preparer_load_error = None


def _load_index_preparer():
    """Load graph embedding dependencies only when the index task is enabled."""
    global _index_preparer, _index_preparer_load_error
    if _index_preparer is not None:
        return _index_preparer
    try:
        from .Services.graph_embeddings import ensure_indexes_standalone
    except Exception as import_error:
        try:
            from Services.graph_embeddings import ensure_indexes_standalone
        except Exception as full_error:
            _index_preparer_load_error = full_error
            logger.warning("Index pre-creation module unavailable: %s", import_error)
            return None
    _index_preparer = ensure_indexes_standalone
    return _index_preparer

try:
    from .Services.agent_memory_service import AgentMemoryService
except Exception:
    try:
        from Services.agent_memory_service import AgentMemoryService
    except Exception as _agent_memory_exc:
        logger.warning("Agent memory service unavailable: %s", _agent_memory_exc)
        AgentMemoryService = None

_chat_generate_response = None
_chat_generate_response_stream = None
_chat_load_error = None


def _load_chat_generators():
    """Load the optional GraphRAG stack on first chat use, not API startup."""
    global _chat_generate_response, _chat_generate_response_stream, _chat_load_error
    if _chat_generate_response is not None and _chat_generate_response_stream is not None:
        return _chat_generate_response, _chat_generate_response_stream
    try:
        from .agent.chat import generate_response as response_fn, generate_response_stream as stream_fn
    except Exception as import_error:
        try:
            from agent.chat import generate_response as response_fn, generate_response_stream as stream_fn
        except Exception as full_error:
            _chat_load_error = full_error
            logger.warning("Agent chat module not available; using lazy Ollama fallback: %s", import_error)

            def _format_graph_context_for_fallback(graph_context) -> str:
                if not graph_context:
                    return ""
                try:
                    return "Current graph context:\n" + json.dumps(graph_context, indent=2, default=str)[:3500]
                except Exception:
                    return f"Current graph context: {str(graph_context)[:3500]}"

            def _live_graph_context_for_fallback(message: str, graph_context=None):
                """Resolve a small Neo4j context when the optional agent stack is absent.

                The browser normally sends a graph snapshot, but external clients do not
                have that snapshot. Keep this lookup bounded and read-only so the fallback
                remains GraphRAG-grounded without requiring LangChain integrations.
                """
                if isinstance(graph_context, dict):
                    visible = graph_context.get("visibleGraph") or graph_context.get("visible_graph") or graph_context
                    if isinstance(visible, dict) and (visible.get("nodes") or visible.get("links") or visible.get("relationships")):
                        return graph_context
                try:
                    try:
                        from .Services.graph_view_service import GraphViewService
                    except Exception:
                        from Services.graph_view_service import GraphViewService

                    text = str(message or "").strip()
                    candidates = []
                    for value in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{2,}", text):
                        lowered = value.lower()
                        if lowered not in {
                            "what", "which", "where", "when", "why", "how", "show", "find",
                            "list", "with", "from", "this", "that", "about", "impact", "analysis",
                            "context", "graph", "please", "does", "have", "give", "and", "the",
                        } and value not in candidates:
                            candidates.append(value)
                    for candidate in candidates[:8]:
                        payload = GraphViewService.get_contextual_subgraph(
                            search=candidate,
                            limit=24,
                            search_mode="broader",
                            expand_neighbors=True,
                        )
                        if payload and (payload.get("nodes") or payload.get("relationships")):
                            return {
                                "source": "backend-neo4j-context",
                                "query": message,
                                "contextualGraph": payload,
                            }
                except Exception as exc:
                    logger.warning("Live Neo4j fallback context unavailable: %s", exc)
                return graph_context

            async def response_fn(session_id: str, message: str, graph_context=None) -> str:
                from Services.ollama_service import get_ollama_service
                try:
                    prompt = message
                    live_context = _live_graph_context_for_fallback(message, graph_context)
                    context_text = _format_graph_context_for_fallback(live_context)
                    if context_text:
                        prompt = f"{context_text}\n\nUser question: {message}"
                    response = get_ollama_service().query(prompt)
                    return response or "I couldn't generate a response. Please try again."
                except Exception as exc:
                    logger.error("Fallback chat error: %s: %s", type(exc).__name__, exc, exc_info=True)
                    return "I encountered an error processing your request. Please try again later."

            def stream_fn(session_id: str, message: str, graph_context=None):
                async def _stream():
                    from Services.ollama_service import get_ollama_service
                    try:
                        prompt = message
                        live_context = _live_graph_context_for_fallback(message, graph_context)
                        context_text = _format_graph_context_for_fallback(live_context)
                        if context_text:
                            prompt = f"{context_text}\n\nUser question: {message}"
                        response = get_ollama_service().query(prompt)
                        if response:
                            for index in range(0, len(response), 6):
                                yield f"data: {json.dumps({'token': response[index:index + 6]})}\n\n"
                        yield f"data: {json.dumps({'done': True})}\n\n"
                    except Exception as exc:
                        logger.error("Fallback stream error: %s: %s", type(exc).__name__, exc, exc_info=True)
                        yield f"data: {json.dumps({'error': 'Error processing your request'})}\n\n"
                        yield f"data: {json.dumps({'done': True})}\n\n"
                return _stream()

        _chat_load_error = _chat_load_error or import_error
    _chat_generate_response = response_fn
    _chat_generate_response_stream = stream_fn
    return _chat_generate_response, _chat_generate_response_stream


async def generate_response(session_id: str, message: str, graph_context=None):
    response_fn, _ = _load_chat_generators()
    return await response_fn(session_id, message, graph_context)


def generate_response_stream(session_id: str, message: str, graph_context=None):
    _, stream_fn = _load_chat_generators()
    return stream_fn(session_id, message, graph_context)

try:
    from .core.graph import graph, get_graph_schema, cleanup_graph_connection
    # from .models.schema import ChatRequest, ChatResponse, ResetRequest, TextSearchRequest, ChatWithCypherResponse
    # from .agent.memory import reset_memory
    from .models.schema import ChatRequest, ChatResponse, TextSearchRequest
    from .data_ingestion import router as ingestion_router
    from .Services.unified_import_router import router as unified_import_router, ontology_router as ontology_upload_router
    from .routes.ontology_routes import router as ontology_router
    from .routes.oslc_routes import router as oslc_router
    from .routes.threedxml_routes import router as threedxml_router
    from .routes.admin_routes import router as admin_router
    from .qif.router import router as qif_router
    from .routes.sysml_v2_routes import router as sysml_v2_router
    from .routes.metadata_registry_routes import router as metadata_registry_router
    try:
        from .Services.documents_api import router as documents_router
    except Exception:
        documents_router = None
    from .Services.oslc_trs_service import OSLCTRSService
except ImportError:
    # Script mode (python backend/main.py): add project root for backend.* imports.
    _backend_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_backend_dir)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from backend.core.graph import graph, get_graph_schema, cleanup_graph_connection
    from backend.models.schema import ChatRequest, ChatResponse, TextSearchRequest
    from backend.data_ingestion import router as ingestion_router
    from backend.Services.unified_import_router import router as unified_import_router, ontology_router as ontology_upload_router
    from backend.routes.ontology_routes import router as ontology_router
    from backend.routes.oslc_routes import router as oslc_router
    from backend.routes.threedxml_routes import router as threedxml_router
    from backend.routes.admin_routes import router as admin_router
    from backend.qif.router import router as qif_router
    from backend.routes.sysml_v2_routes import router as sysml_v2_router
    from backend.routes.metadata_registry_routes import router as metadata_registry_router
    try:
        from backend.Services.documents_api import router as documents_router
        from backend.Services.oslc_trs_service import OSLCTRSService
    except Exception:
        documents_router = None

# Optional imports - gracefully handle missing modules
try:
    from langchain_neo4j import Neo4jGraph
except ImportError:
    Neo4jGraph = None
    import logging
    logging.getLogger(__name__).warning("langchain_neo4j not available")

from pydantic import BaseModel
from contextlib import asynccontextmanager

class TextSearchRequest(BaseModel):
    search: str
    ontology_prefix: str = ""


def _normalize_search_term(value: str) -> str:
    normalized = re.sub(r"\*+", "", str(value or "")).strip().lower()
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", normalized)


GRAPH_SEARCH_PROPERTY_KEYS = [
    "name",
    "title",
    "code",
    "label",
    "identifier",
    "requirement_id",
    "part_number",
    "catalogue_id",
    "item_id",
    "uid",
    "id",
]

GRAPH_SEARCH_RELATIONSHIP_PROPERTY_KEYS = [
    "name",
    "label",
    "type",
    "semantic_role",
    "target_source_id",
]


class WorkflowExecuteRequest(BaseModel):
    workflow_id: str
    payload: dict = {}

#graph = Neo4jPropertyGraphStore(
#    url = os.getenv('Neo4j_url'),
#    username=os.getenv('Neo4j_user'),
#    password=os.getenv('Neo4j_password'),
#    #url = "neo4j+ssc://b76c70fa.databases.neo4j.io",
#    database = "mbse-sysml"
#)

def _startup_flag(name: str, default: bool = True) -> bool:
    """Read a boolean startup setting without making deployments brittle."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


async def _prepare_neo4j_indexes(app: FastAPI) -> None:
    """Prepare optional indexes without blocking Uvicorn from accepting requests."""
    preparer = _load_index_preparer()
    if preparer is None:
        app.state.neo4j_index_status = "unavailable"
        return

    app.state.neo4j_index_status = "running"
    try:
        await asyncio.to_thread(preparer)
    except Exception as exc:
        app.state.neo4j_index_status = "failed"
        logger.warning("Neo4j index preflight failed after startup: %s", exc)
    else:
        app.state.neo4j_index_status = "ready"
        logger.info("Neo4j index preflight completed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bind the API first. Index creation can involve a database connection and
    # must not delay health checks, OpenAPI, or the first UI request.
    index_task = None
    app.state.neo4j_index_status = "disabled"
    if _startup_flag("PREPARE_NEO4J_INDEXES_ON_STARTUP", default=True):
        index_task = asyncio.create_task(_prepare_neo4j_indexes(app))
        app.state.neo4j_index_task = index_task
    try:
        from .qif.task_service import task_service
    except ImportError:
        from backend.qif.task_service import task_service
    try:
        recovery = task_service.recover_pending()
        logger.info("QIF workflow recovery: %s", recovery)
    except Exception as exc:
        logger.warning("QIF workflow recovery skipped: %s", exc)
    try:
        yield
    finally:
        logger.info("Application shutting down...")
        if index_task is not None and not index_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(index_task), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Neo4j index preflight did not finish before shutdown")
                index_task.cancel()
            except Exception as exc:
                logger.debug("Neo4j index preflight ended during shutdown: %s", exc)
        try:
            cleanup_graph_connection()
        except Exception as e:
            logger.error(f"Error during shutdown cleanup: {e}")
        logger.info("Application shutdown complete")


app = FastAPI(
    title="Depo Ontology API",
    version="1.0.0",
    lifespan=lifespan,
    description="OpenAPI 3.1.0 - Semantic data import pipeline with ontology management, file parsing, and Neo4j integration",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "ontology",
            "description": "Ontology file management (XSD/XMI upload, metadata capture, storage)",
        },
        {
            "name": "data-import",
            "description": "Data import pipeline operations (upload, preview, status tracking, commit)",
        },
        {
            "name": "mapping",
            "description": "Ontology mapping and alignment operations",
        },
    ],
    contact={
        "name": "API Support",
        "url": "https://github.com/",
    },
    license_info={
        "name": "Proprietary",
    },
)

# 🔒 SECURITY: Rate limiting to prevent brute force attacks
from collections import defaultdict
from time import time as unix_time

request_counts = defaultdict(list)  # Track requests per IP: {ip: [timestamp, timestamp, ...]}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "100"))  # max requests per window
RATE_LIMIT_SKIP_LOCAL_READS = os.getenv("RATE_LIMIT_SKIP_LOCAL_READS", "true").lower() == "true"
RATE_LIMITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

class RateLimitMiddleware:
    """Simple in-memory rate limiter for single-instance deployments"""
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Get client IP
        client_ip = scope.get("client", ("unknown", 0))[0]
        method = (scope.get("method") or "GET").upper()
        path = scope.get("path", "")
        current_time = unix_time()

        is_loopback_client = client_ip in {"127.0.0.1", "::1", "localhost"}
        is_read_request = method not in RATE_LIMITED_METHODS
        if RATE_LIMIT_SKIP_LOCAL_READS and is_loopback_client and is_read_request:
            await self.app(scope, receive, send)
            return

        if is_read_request:
            await self.app(scope, receive, send)
            return
        
        # Use shared SQLite state so the limit is consistent across workers.
        if not allow_shared_request(client_ip, current_time, RATE_LIMIT_WINDOW, RATE_LIMIT_MAX):
            logger.warning("Rate limit exceeded for %s %s from %s", method, path, client_ip)
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [[b"content-type", b"application/json"]],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"detail": "Too many requests. Please try again later."}',
            })
            return
        
        await self.app(scope, receive, send)

app.add_middleware(RateLimitMiddleware)

# 🔒 SECURITY: Session security - timeout and rotation
from uuid import uuid4
from collections import defaultdict

SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "1800"))  # 30 minutes default
session_store = {}  # In-memory session store: {session_id: {created_at, last_accessed_at, user_data}}
session_ips = defaultdict(list)  # Track IPs per session for rotation detection

class SessionSecurityMiddleware:
    """
    🔒 SESSION SECURITY: Implement session timeout and rotation
    - Sessions expire after inactivity
    - Sessions are rotated on authentication
    - Prevents session fixation attacks
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Get or create session ID
        headers = dict(scope.get("headers", []))
        session_id = headers.get(b"x-session-id", b"").decode()
        supplied_session_id = bool(session_id)
        client_ip = scope.get("client", ("unknown", 0))[0]
        
        current_time = unix_time()
        
        # Check shared session validity; the local dictionaries remain a small hot cache.
        session = session_store.get(session_id) if session_id else None
        shared_session = get_shared_session(session_id) if session_id else None
        if shared_session:
            session = {
                'created_at': shared_session['created_at'],
                'last_accessed_at': shared_session['last_accessed_at'],
                'data': {},
            }
            session_ips[session_id] = shared_session.get('ips', [])

        if session_id and session and current_time - session.get('last_accessed_at', current_time) <= SESSION_TIMEOUT:
            
            # Check for IP change (session fixation detection)
            if client_ip not in session_ips[session_id]:
                # IP changed - rotate session
                logger.warning(f"Session IP mismatch detected. Rotating session. Old IP: {session_ips[session_id]}, New IP: {client_ip}")
                old_session_id = session_id
                session_id = str(uuid4())
                session_store[session_id] = session
                session_ips[session_id] = [client_ip]
                session_store.pop(old_session_id, None)
                session_ips.pop(old_session_id, None)
                delete_shared_session(old_session_id)
            
            # Update last accessed time
            session['last_accessed_at'] = current_time
            session_store[session_id] = session
            save_shared_session(session_id, session.get('created_at', current_time), current_time, session_ips[session_id])
        else:
            # Create new session
            if session_id:
                delete_shared_session(session_id)
            session_id = str(uuid4())
            session_store[session_id] = {
                'created_at': current_time,
                'last_accessed_at': current_time,
                'data': {}
            }
            session_ips[session_id] = [client_ip]
            save_shared_session(session_id, current_time, current_time, [client_ip])
        
        # Pass session ID to app via scope
        scope['session_id'] = session_id
        scope['session_id_supplied'] = supplied_session_id

        async def send_with_session(message):
            if message.get("type") == "http.response.start":
                headers_out = list(message.get("headers") or [])
                headers_out.append((b"x-session-id", session_id.encode("ascii")))
                message = {**message, "headers": headers_out}
            await send(message)

        await self.app(scope, receive, send_with_session)

app.add_middleware(SessionSecurityMiddleware)


def _bind_chat_session(http_request: Request, requested_session_id: str) -> str:
    """Bind chat payloads to the server-issued session carried by the header."""
    server_session_id = http_request.scope.get("session_id")
    if not server_session_id:
        raise HTTPException(status_code=401, detail="A valid client session is required")
    if http_request.scope.get("session_id_supplied") and requested_session_id != server_session_id:
        raise HTTPException(status_code=403, detail="Chat session does not match the client session")
    return server_session_id

# 🔒 SECURITY: HTTP Security Headers Middleware
class SecurityHeadersMiddleware:
    """
    🔒 MEDIUM PRIORITY: Add security headers to all responses
    - Content-Security-Policy: Prevent XSS attacks
    - X-Frame-Options: Prevent clickjacking
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-XSS-Protection: Legacy XSS protection
    - Strict-Transport-Security: Force HTTPS
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                
                # Add security headers
                security_headers = [
                    # Content Security Policy - prevent XSS
                    (b"content-security-policy", b"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; connect-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com;"),
                    # Prevent clickjacking
                    (b"x-frame-options", b"SAMEORIGIN"),
                    # Prevent MIME sniffing
                    (b"x-content-type-options", b"nosniff"),
                    # Legacy XSS protection
                    (b"x-xss-protection", b"1; mode=block"),
                    # Referrer Policy
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    # Feature Policy / Permissions-Policy
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
                ]
                
                # Add HSTS only if on HTTPS (based on X-Forwarded-Proto)
                request_headers = dict(scope.get("headers", []))
                if request_headers.get(b"x-forwarded-proto") == b"https":
                    security_headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                
                headers.extend(security_headers)
                message["headers"] = headers
            
            await send(message)
        
        await self.app(scope, receive, send_with_headers)

app.add_middleware(SecurityHeadersMiddleware)

# 🔒 MEDIUM PRIORITY: Request logging middleware
class RequestLoggingMiddleware:
    """
    Log all API requests with method, endpoint, status, and response time
    Excludes sensitive data from logs
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        import time
        start_time = time.time()
        
        # Get request info
        method = scope.get("method", "")
        path = scope.get("path", "")
        client_ip = scope.get("client", ("unknown", 0))[0]
        
        # Skip logging for health checks
        if path in ["/health", "/docs", "/openapi.json"]:
            await self.app(scope, receive, send)
            return
        
        status_code = 200
        
        async def send_with_logging(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
        
        try:
            await self.app(scope, receive, send_with_logging)
        finally:
            duration = time.time() - start_time
            
            # Log with appropriate level based on status code
            log_level = "INFO" if 200 <= status_code < 400 else "WARNING"
            log_msg = f"{method} {path} - Status: {status_code} - Duration: {duration:.3f}s - IP: {client_ip}"
            
            if log_level == "INFO":
                logger.info(log_msg)
            else:
                logger.warning(log_msg)

class PerformanceMonitoringMiddleware:
    """
    🔒 MEDIUM PRIORITY: Monitor and track request performance
    - Logs slow requests (>1000ms)
    - Tracks metrics for performance analysis
    - Identifies bottlenecks in API endpoints
    """
    
    # Request performance metrics (optional: sends to monitoring service)
    SLOW_REQUEST_THRESHOLD = 1000  # 1 second in milliseconds
    
    def __init__(self, app):
        self.app = app
        self.metrics = {
            'total_requests': 0,
            'slow_requests': 0,
            'endpoint_times': {}  # { 'GET /api/endpoint': [time1, time2, ...] }
        }
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        import time
        start_time = time.time()
        
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        
        # Skip monitoring for health checks and static assets
        if path in ["/health", "/ready", "/docs", "/openapi.json"] or path.startswith("/static/"):
            await self.app(scope, receive, send)
            return
        
        status_code = 200
        
        async def send_with_monitoring(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
        
        try:
            await self.app(scope, receive, send_with_monitoring)
        finally:
            duration_ms = (time.time() - start_time) * 1000
            endpoint_key = f"{method} {path}"
            
            # Track metrics
            self.metrics['total_requests'] += 1
            
            if endpoint_key not in self.metrics['endpoint_times']:
                self.metrics['endpoint_times'][endpoint_key] = []
            
            self.metrics['endpoint_times'][endpoint_key].append(duration_ms)
            
            # Log slow requests (>1000ms)
            if duration_ms > self.SLOW_REQUEST_THRESHOLD:
                self.metrics['slow_requests'] += 1
                logger.warning(
                    f"SLOW REQUEST: {method} {path} took {duration_ms:.0f}ms (status {status_code})"
                )
            
            # Additional performance insight for very slow requests (>5s)
            if duration_ms > 5000:
                avg_time = sum(self.metrics['endpoint_times'][endpoint_key]) / len(self.metrics['endpoint_times'][endpoint_key])
                logger.error(
                    f"CRITICAL SLOW: {endpoint_key} - Duration: {duration_ms:.0f}ms, "
                    f"Avg: {avg_time:.0f}ms, Requests: {len(self.metrics['endpoint_times'][endpoint_key])}"
                )
    
    def get_metrics(self):
        """Return current performance metrics for monitoring/debugging"""
        summary = {}
        for endpoint, times in self.metrics['endpoint_times'].items():
            if times:
                summary[endpoint] = {
                    'count': len(times),
                    'min': min(times),
                    'max': max(times),
                    'avg': sum(times) / len(times)
                }
        
        return {
            'total_requests': self.metrics['total_requests'],
            'slow_requests': self.metrics['slow_requests'],
            'endpoints': summary
        }

class CacheControlMiddleware:
    """
    🔒 MEDIUM PRIORITY: Add appropriate cache control headers to responses
    - Static assets: Cache for 1 year (immutable)
    - HTML: Validate with server (no-cache)
    - API responses: Cache graph data (5 minutes), no-cache for uploads/mutations
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        
        async def send_with_cache(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                
                # Determine cache strategy based on path and method
                cache_control = None
                
                if path.startswith("/static/") or path.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2")):
                    # Static assets: Cache for 1 year (31536000 seconds)
                    cache_control = "public, max-age=31536000, immutable"
                elif path.endswith(".html") or path in ["/", ""]:
                    # HTML: Always validate with server
                    cache_control = "no-cache, no-store, must-revalidate, max-age=0"
                elif method == "GET":
                    # GET requests: Cache for 5 minutes with revalidation
                    if path.startswith("/graphvis") or path.startswith("/api/graph"):
                        cache_control = "public, max-age=300"  # 5 minutes
                    elif path.startswith("/api/") and "search" not in path:
                        cache_control = "public, max-age=60"  # 1 minute for API
                else:
                    # POST/PUT/DELETE: Don't cache mutations
                    cache_control = "no-cache, no-store, must-revalidate, max-age=0"
                
                # Add cache control header if determined
                if cache_control:
                    # Check if Cache-Control header already exists
                    has_cache_control = any(
                        name.lower() == b"cache-control" for name, _ in headers
                    )
                    if not has_cache_control:
                        headers.append((b"cache-control", cache_control.encode()))
                
                # Add ETag support (for client-side caching validation)
                message["headers"] = headers
            
            await send(message)
        
        await self.app(scope, receive, send_with_cache)

app.add_middleware(CacheControlMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# ⏱️ TIMEOUT HANDLING: Request timeout management for long-running operations
class TimeoutMiddleware:
    """
    ⏱️ CRITICAL FIX: Handle request timeouts for long-running endpoints
    - Import operations: 5 minutes (300s)
    - Chat/streaming: 5 minutes (300s)
    - Graph operations: 5 minutes (300s)
    - All others: 1 minute (60s)
    """
    
    def __init__(self, app):
        self.app = app
        # Endpoint-specific timeout mappings
        import_timeout = int(os.getenv('IMPORT_REQUEST_TIMEOUT_SECONDS', os.getenv('REQUEST_IMPORT_TIMEOUT_SECONDS', '3600')))
        ontology_timeout = int(os.getenv('ONTOLOGY_REQUEST_TIMEOUT_SECONDS', str(import_timeout)))
        graph_timeout = int(os.getenv('GRAPH_REQUEST_TIMEOUT_SECONDS', '300'))
        self.endpoint_timeouts = {
            '/api/v1/import': import_timeout,
            '/api/import': import_timeout,      # Legacy route
            '/data-import': import_timeout,     # Legacy route
            '/api/v1/ontology/upload': ontology_timeout,
            '/api/ontology/upload': ontology_timeout,     # Legacy route
            '/chat': int(os.getenv('CHAT_REQUEST_TIMEOUT_SECONDS', '900')),  # 15 min default for chat responses
            '/chat-stream': int(os.getenv('CHAT_STREAM_TIMEOUT_SECONDS', '900')),  # 15 min default for streaming responses
            '/graphvis': graph_timeout,
            '/graphfilter': graph_timeout,
        }
        self.default_timeout = 60  # Keep unmatched endpoints fast-failing by default
    
    def get_timeout_for_path(self, path: str) -> int:
        """Get appropriate timeout for the given path"""
        # Check exact matches first
        if path in self.endpoint_timeouts:
            return self.endpoint_timeouts[path]
        
        # Check prefix matches
        for endpoint_prefix, timeout in self.endpoint_timeouts.items():
            if path.startswith(endpoint_prefix):
                return timeout
        
        return self.default_timeout
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        timeout_seconds = self.get_timeout_for_path(path)
        
        try:
            # Wrap app call with timeout
            async with asyncio.timeout(timeout_seconds):
                await self.app(scope, receive, send)
        except asyncio.TimeoutError:
            # Send timeout response if not already sent
            try:
                await send({
                    "type": "http.response.start",
                    "status": 504,  # Gateway Timeout
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": f'{{"detail": "Request timeout after {timeout_seconds}s"}}'.encode(),
                })
            except Exception as e:
                logger.error(f"Error sending timeout response: {e}")

app.add_middleware(TimeoutMiddleware)

# ✅ SECURE: Load allowed origins from environment with fallback.
# Include localhost, loopback, and the configured/LAN frontend host so the app
# works when the UI is opened locally but calls a LAN-bound backend URL.
def _build_allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    origins = {origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()}
    raw_ports = os.getenv("FRONTEND_PORTS", os.getenv("FRONTEND_PORT", "3000"))
    ports = set()
    for raw_port in raw_ports.split(","):
        try:
            port = int(raw_port.strip())
            if 1 <= port <= 65535:
                ports.add(port)
        except (TypeError, ValueError):
            continue
    ports.add(3000)
    for host in ("localhost", "127.0.0.1", os.getenv("APP_HOST", "").strip()):
        if host:
            for port in ports:
                origins.add(f"http://{host}:{port}")
                origins.add(f"https://{host}:{port}")
    return sorted(origins)


allowed_origins = _build_allowed_origins()

# Add CORS middleware last so it wraps error responses too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],
)

# 🔒 SECURITY: Neo4j query timeout configuration
NEO4J_QUERY_TIMEOUT = int(os.getenv("NEO4J_QUERY_TIMEOUT", "300"))  # 5 minutes default
NEO4J_DRIVER_TIMEOUT = 60  # Connection timeout

# Chat/session timing controls
# Extended timeouts for Ollama model inference and streaming responses
CHAT_REQUEST_TIMEOUT_SECONDS = int(os.getenv("CHAT_REQUEST_TIMEOUT_SECONDS", "900"))  # 15 min
CHAT_STREAM_TIMEOUT_SECONDS = int(os.getenv("CHAT_STREAM_TIMEOUT_SECONDS", "900"))  # 15 min
SESSION_LOCK_TIMEOUT_SECONDS = int(os.getenv("SESSION_LOCK_TIMEOUT_SECONDS", "15"))  # Allow slower systems
SESSION_LOCK_TTL_SECONDS = int(os.getenv("SESSION_LOCK_TTL_SECONDS", "1800"))
CHAT_JOB_TTL_SECONDS = int(os.getenv("CHAT_JOB_TTL_SECONDS", "3600"))
CHAT_JOB_MAX_COUNT = int(os.getenv("CHAT_JOB_MAX_COUNT", "200"))

_CHAT_JOBS: dict[str, dict] = {}
_CHAT_JOBS_LOCK = asyncio.Lock()


async def _cleanup_chat_jobs() -> None:
    now = time.time()
    async with _CHAT_JOBS_LOCK:
        persisted_jobs = {job.get("job_id"): job for job in list_shared_chat_jobs() if job.get("job_id")}
        _CHAT_JOBS.update(persisted_jobs)
        expired = [job_id for job_id, job in _CHAT_JOBS.items()
                   if (now - float(job.get("updated_at") or job.get("created_at") or now)) > CHAT_JOB_TTL_SECONDS]
        for job_id in expired:
            _CHAT_JOBS.pop(job_id, None)
            delete_shared_chat_job(job_id)
        if len(_CHAT_JOBS) > CHAT_JOB_MAX_COUNT:
            overflow = len(_CHAT_JOBS) - CHAT_JOB_MAX_COUNT
            oldest = sorted(_CHAT_JOBS.items(), key=lambda item: item[1].get("updated_at") or item[1].get("created_at") or 0)[:overflow]
            for job_id, _ in oldest:
                _CHAT_JOBS.pop(job_id, None)


async def _update_chat_job(job_id: str, **updates) -> None:
    async with _CHAT_JOBS_LOCK:
        job = _CHAT_JOBS.get(job_id) or get_shared_chat_job(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = time.time()
        _CHAT_JOBS[job_id] = job
        save_shared_chat_job(job_id, job)


async def _execute_chat_job(job_id: str, session_id: str, message: str, graph_context=None) -> None:
    await _update_chat_job(job_id, status="running", started_at=time.time())
    try:
        async with _session_lock(session_id):
            result = await _run_with_timeout(
                generate_response,
                CHAT_REQUEST_TIMEOUT_SECONDS,
                session_id,
                message,
                graph_context,
            )
        if AgentMemoryService is not None:
            try:
                AgentMemoryService.record_chat_turn(
                    session_id=session_id,
                    user_message=message,
                    assistant_response=result,
                    graph_context=graph_context,
                    status="completed",
                )
                AgentMemoryService.record_reasoning_trace(
                    session_id=session_id,
                    task="async_chat_job",
                    tool_name="knowledge_companion",
                    input_payload={"job_id": job_id, "message": message, "graph_context_present": bool(graph_context)},
                    result_summary={"response_length": len(str(result or "")), "status": "completed"},
                    success=True,
                )
            except Exception as memory_exc:
                logger.warning("Agent memory chat job record skipped: %s", memory_exc)
        await _update_chat_job(job_id, status="completed", completed_at=time.time(), response=result)
    except asyncio.TimeoutError:
        logger.warning("Chat job timed out for session %s job %s", session_id, job_id)
        await _update_chat_job(job_id, status="timeout", completed_at=time.time(), error="Chat request timed out. Please retry with a narrower question.")
    except HTTPException as exc:
        await _update_chat_job(job_id, status="failed", completed_at=time.time(), error=str(exc.detail))
    except Exception as exc:
        logger.error("Chat job failed for session %s job %s: %s", session_id, job_id, exc, exc_info=True)
        await _update_chat_job(job_id, status="failed", completed_at=time.time(), error="Failed to process chat request. Please try again later.")

_SESSION_LOCKS: dict[str, asyncio.Lock] = {}
_SESSION_LOCK_LAST_USED: dict[str, float] = {}
_SESSION_LOCK_GUARD = asyncio.Lock()


async def _get_session_lock(session_id: str) -> asyncio.Lock:
    now = time.monotonic()
    async with _SESSION_LOCK_GUARD:
        stale_ids = [
            sid
            for sid, ts in _SESSION_LOCK_LAST_USED.items()
            if (now - ts) > SESSION_LOCK_TTL_SECONDS and sid in _SESSION_LOCKS and not _SESSION_LOCKS[sid].locked()
        ]
        for sid in stale_ids:
            _SESSION_LOCKS.pop(sid, None)
            _SESSION_LOCK_LAST_USED.pop(sid, None)

        lock = _SESSION_LOCKS.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_LOCKS[session_id] = lock
        _SESSION_LOCK_LAST_USED[session_id] = now
        return lock


@asynccontextmanager
async def _session_lock(session_id: str):
    lock = await _get_session_lock(session_id)
    owner = f"{os.getpid()}:{id(lock)}:{uuid4()}"
    try:
        await asyncio.wait_for(lock.acquire(), timeout=SESSION_LOCK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=429,
            detail="Another request is in progress for this session. Please retry shortly.",
        ) from exc

    shared_acquired = False
    try:
        deadline = time.monotonic() + SESSION_LOCK_TIMEOUT_SECONDS
        lease_ttl = max(SESSION_LOCK_TTL_SECONDS, CHAT_REQUEST_TIMEOUT_SECONDS + 60, CHAT_STREAM_TIMEOUT_SECONDS + 60)
        while time.monotonic() < deadline:
            shared_acquired = await asyncio.to_thread(acquire_session_lease, session_id, owner, lease_ttl)
            if shared_acquired:
                break
            await asyncio.sleep(0.1)
        if not shared_acquired:
            raise HTTPException(
                status_code=429,
                detail="Another request is in progress for this session. Please retry shortly.",
            )
        yield
    finally:
        if shared_acquired:
            await asyncio.to_thread(release_session_lease, session_id, owner)
        if lock.locked():
            lock.release()
        _SESSION_LOCK_LAST_USED[session_id] = time.monotonic()


async def _run_with_timeout(func, timeout_seconds: int, *args):
    # Handle both sync and async functions
    if asyncio.iscoroutinefunction(func):
        # For async functions, call directly
        return await asyncio.wait_for(func(*args), timeout=timeout_seconds)
    else:
        # For sync functions, run in thread pool
        return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=timeout_seconds)


async def _stream_with_timeout(session_id: str, message: str, graph_context=None):
    stream_iter = None
    response_parts: list[str] = []
    stream_failed = False
    memory_recorded = False

    async def record_completed_stream() -> None:
        nonlocal memory_recorded
        if memory_recorded or stream_failed or AgentMemoryService is None:
            return
        assistant_response = "".join(response_parts)
        try:
            await asyncio.to_thread(
                AgentMemoryService.record_chat_turn,
                session_id=session_id,
                user_message=message,
                assistant_response=assistant_response,
                graph_context=graph_context,
                status="completed",
            )
            await asyncio.to_thread(
                AgentMemoryService.record_reasoning_trace,
                session_id=session_id,
                task="chat-stream",
                tool_name="knowledge_companion",
                input_payload={"message": message, "graph_context_present": bool(graph_context)},
                result_summary={"response_length": len(assistant_response), "status": "completed"},
                success=True,
            )
            memory_recorded = True
        except Exception as memory_exc:
            logger.warning("Agent memory stream record skipped: %s", memory_exc)

    try:
        async with _session_lock(session_id):
            stream_iter = generate_response_stream(session_id, message, graph_context)
            deadline = time.monotonic() + CHAT_STREAM_TIMEOUT_SECONDS
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                try:
                    event = await asyncio.wait_for(stream_iter.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    break
                for line in str(event or "").splitlines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[5:].strip())
                    except (TypeError, ValueError):
                        continue
                    if payload.get("token"):
                        response_parts.append(str(payload["token"]))
                    if payload.get("error"):
                        stream_failed = True
                    if payload.get("done") and not stream_failed:
                        await record_completed_stream()
                yield event
            if response_parts and not stream_failed:
                await record_completed_stream()
    except asyncio.TimeoutError:
        logger.warning("Chat stream timed out for session %s", session_id)
        yield f"data: {json.dumps({'error': 'Chat stream timed out. Please retry with a narrower or more specific question.'})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except HTTPException as exc:
        error_detail = str(exc.detail) if exc.detail else "Request failed"
        yield f"data: {json.dumps({'error': error_detail})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as exc:
        logger.error("Chat stream wrapper error for session %s: %s", session_id, exc, exc_info=True)
        error_msg = f"Error processing your request: {type(exc).__name__}. Try rephrasing your question or check the component name exists in the system."
        yield f"data: {json.dumps({'error': error_msg})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
    finally:
        if stream_iter is not None:
            try:
                await stream_iter.aclose()
            except Exception:
                pass

# 🔒 MEDIUM PRIORITY: Simple API Key Authentication
# ✅ ERROR HANDLING: Global exception handler to prevent stack trace leakage
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return safe error messages."""
    # Log full error internally for debugging
    logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}", exc_info=True)
    
    # Return safe error message to client without exposing stack trace
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please contact support if the problem persists.",
            "status": "error",
            "error_code": "INTERNAL_SERVER_ERROR",
            "path": request.url.path,
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Keep client errors predictable without exposing implementation details."""
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    if exc.status_code >= 500:
        detail = "An internal server error occurred. Please try again later."
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "detail": detail,
            "status": "error",
            "error_code": f"HTTP_{exc.status_code}",
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return one validation shape for every API route."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "path": request.url.path,
            "errors": exc.errors(),
        },
    )

def safe_error(endpoint: str, error: Exception):
    """Log error internally and return safe error message."""
    logger.error(f"{endpoint} error: {type(error).__name__}: {str(error)}", exc_info=True)
    raise HTTPException(
        status_code=500, 
        detail="An error occurred processing your request. Please try again later."
    )

def normalize_ontology_prefix(results: list) -> list:
    """
    Normalize ontology prefix in response results.
    Ensures all nodes have both 'prefix' and 'ontology_prefix' fields set consistently.
    
    Problem: Some ontologies (e.g., SPLM) have ontology_prefix but not prefix property.
    Solution: Copy ontology_prefix value to prefix field if prefix is missing.
    
    This fixes inconsistency where MBSE has both fields but SPLM only has ontology_prefix.
    """
    if not results:
        return results
    
    normalized = []
    for row in results:
        normalized_row = dict(row)
        
        # Normalize source node (n)
        if normalized_row.get('n') and isinstance(normalized_row['n'], dict):
            n = normalized_row['n']
            if n.get('properties'):
                props = dict(n['properties'])
                # If prefix is missing but ontology_prefix exists, copy it
                if 'ontology_prefix' in props and 'prefix' not in props:
                    props['prefix'] = props['ontology_prefix']
                    n['properties'] = props
        
        # Normalize target node (m)
        if normalized_row.get('m') and isinstance(normalized_row['m'], dict):
            m = normalized_row['m']
            if m.get('properties'):
                props = dict(m['properties'])
                # If prefix is missing but ontology_prefix exists, copy it
                if 'ontology_prefix' in props and 'prefix' not in props:
                    props['prefix'] = props['ontology_prefix']
                    m['properties'] = props
        
        normalized.append(normalized_row)
    
    return normalized

# 🔒 MEDIUM PRIORITY: API Versioning
# Create v1 router for all main API endpoints
# Allows for future v2 with breaking changes while maintaining backward compatibility
api_v1 = APIRouter(prefix="/api/v1", tags=["v1"])

# Versioning strategy:
# - All current endpoints use /api/v1/* to enable future /api/v2/* without breaking clients
# - Old /api/* endpoints kept for backward compatibility (deprecated in logs)
# - New clients should use /api/v1/* explicitly

app.include_router(ingestion_router, prefix="/api/v1", tags=["v1-ingestion"])
app.include_router(unified_import_router, prefix="/api/v1", tags=["v1-data-import"])
app.include_router(ontology_upload_router, prefix="/api/v1", tags=["v1-ontology-upload"])
app.include_router(ontology_router, prefix="/api/v1", tags=["v1-ontology"])
app.include_router(oslc_router)
app.include_router(threedxml_router, prefix="/api/v1", tags=["v1-3dxml"])
app.include_router(admin_router, prefix="/api/v1", tags=["v1-admin"])
app.include_router(qif_router, prefix="/api/v1", tags=["v1-qif"])
app.include_router(sysml_v2_router, prefix="/api/v1", tags=["v1-sysml-v2"])
app.include_router(metadata_registry_router, prefix="/api/v1", tags=["v1-metadata-registry"])
if documents_router is not None:
    app.include_router(documents_router, prefix="/api/v1", tags=["v1-documents"])
else:
    logger.warning("Documents router not mounted because document pipeline imports are unavailable")

# API versioning enabled: All endpoints use /api/v1/* for consistent routing
# Legacy /api/* routes have been deprecated and removed (June 2026)
# All clients must use /api/v1/* prefix for API requests
logger.info("API v1 routing enabled. All clients must use /api/v1/* prefix for API requests.")

# NOTE: shutdown cleanup moved to lifespan handler above (FastAPI lifespan)

# ✅ CRITICAL: Health check endpoints
@app.get("/health")
def health():
    """Liveness probe - is the service running? (Kubernetes, load balancers use this)"""
    return {"status": "alive", "service": "depo-onto-engine"}

@app.get("/ready")
def readiness():
    """Readiness probe - is the service ready to accept requests?"""
    try:
        # Quick check that Neo4j connection works
        graph.query("RETURN 1 as test LIMIT 1")
        return {
            "status": "ready",
            "service": "depo-onto-engine",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "service": "depo-onto-engine",
                "database": "disconnected",
                "message": "Service is starting up or database is unavailable"
            }
        )



@app.get("/schema")
def schema():
    """Return node labels, relationship types, their properties, and display-name keys.
    Cached in-memory on the backend (10 min TTL)."""
    try:
        return get_graph_schema()
    except Exception as e:
        logger.error(f"Schema endpoint error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "endpoint": "/schema",
                "message": "Neo4j database temporarily unavailable. Schema will load when database is connected.",
            },
        )


@app.post("/chat/validate")
async def chat_validate(http_request: Request, request: ChatRequest):
    """Validate external chat request payloads without invoking the LLM."""
    session_id = _bind_chat_session(http_request, request.session_id)
    return {
        "status": "ok",
        "session_id": session_id,
        "message_length": len(request.message),
        "graph_context_present": bool(request.graph_context),
        "execute_endpoint": "/chat",
        "stream_endpoint": "/chat-stream",
    }


@app.post("/chat/jobs")
async def chat_job_submit(http_request: Request, request: ChatRequest, background_tasks: BackgroundTasks):
    """Submit an asynchronous chat job for external apps that cannot wait on long LLM calls."""
    if generate_response is None:
        raise HTTPException(status_code=503, detail="Chat service is unavailable. Please check backend configuration.")
    session_id = _bind_chat_session(http_request, request.session_id)
    await _cleanup_chat_jobs()
    now = time.time()
    job_id = f"chatjob-{uuid4()}"
    async with _CHAT_JOBS_LOCK:
        _CHAT_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "session_id": session_id,
            "message_length": len(request.message),
            "created_at": now,
            "updated_at": now,
            "poll_endpoint": f"/chat/jobs/{job_id}",
        }
        save_shared_chat_job(job_id, _CHAT_JOBS[job_id])
    background_tasks.add_task(_execute_chat_job, job_id, session_id, request.message, request.graph_context)
    return JSONResponse(status_code=202, content={
        "status": "accepted",
        "job_id": job_id,
        "session_id": session_id,
        "poll_endpoint": f"/chat/jobs/{job_id}",
        "message": "Chat job accepted. Poll the job endpoint for completion.",
    })


@app.get("/chat/jobs/{job_id}")
async def chat_job_status(http_request: Request, job_id: str):
    """Return async chat job status and response when complete."""
    await _cleanup_chat_jobs()
    async with _CHAT_JOBS_LOCK:
        job = dict(_CHAT_JOBS.get(job_id) or get_shared_chat_job(job_id) or {})
    if not job:
        raise HTTPException(status_code=404, detail=f"Chat job not found or expired: {job_id}")
    if not http_request.scope.get("session_id_supplied") or job.get("session_id") != http_request.scope.get("session_id"):
        raise HTTPException(status_code=403, detail="Chat job is not available for this client session")
    return job


@app.post("/chat", response_model=ChatResponse)
async def chat(http_request: Request, request: ChatRequest):
    if generate_response is None:
        raise HTTPException(status_code=503, detail="Chat service is unavailable. Please check backend configuration.")
    session_id = _bind_chat_session(http_request, request.session_id)

    try:
        async with _session_lock(session_id):
            result = await _run_with_timeout(
                generate_response,
                CHAT_REQUEST_TIMEOUT_SECONDS,
                session_id,
                request.message,
                request.graph_context,
            )
        if AgentMemoryService is not None:
            try:
                AgentMemoryService.record_chat_turn(
                    session_id=session_id,
                    user_message=request.message,
                    assistant_response=result,
                    graph_context=request.graph_context,
                    status="completed",
                )
                AgentMemoryService.record_reasoning_trace(
                    session_id=session_id,
                    task="chat",
                    tool_name="knowledge_companion",
                    input_payload={"message": request.message, "graph_context_present": bool(request.graph_context)},
                    result_summary={"response_length": len(str(result or "")), "status": "completed"},
                    success=True,
                )
            except Exception as memory_exc:
                logger.warning("Agent memory chat record skipped: %s", memory_exc)
        return ChatResponse(session_id=session_id, response=result)
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning("Chat request timed out for session %s", session_id)
        raise HTTPException(status_code=504, detail="Chat request timed out. Please retry with a narrower question.")
    except Exception as e:
        logger.error(f"Chat endpoint error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process chat request. Please try again later.")


@app.post("/chat-stream")
async def chat_stream(http_request: Request, request: ChatRequest):
    """Streaming chat endpoint — returns Server-Sent Events (text/event-stream).
    Each event is a JSON object:
      {"token": "..."}   — next text chunk
      {"status": "..."}  — tool-call status label
      {"done": true}     — stream finished
      {"error": "..."}   — error message
    """
    if generate_response_stream is None:
        raise HTTPException(status_code=503, detail="Chat stream service is unavailable. Please check backend configuration.")
    session_id = _bind_chat_session(http_request, request.session_id)

    return StreamingResponse(
        _stream_with_timeout(session_id, request.message, request.graph_context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/chat/health")
@app.get("/chat/status")
async def chat_health():
    return {
        "status": "ok" if generate_response is not None else "unavailable",
        "chat_post_available": generate_response is not None,
        "chat_stream_available": generate_response_stream is not None,
        "session_id_required": False,
        "session_id_behavior": "The server issues a session id in X-Session-ID; clients should return it on subsequent requests.",
        "methods": {
            "ask": "POST /chat",
            "stream": "POST /chat-stream",
            "submit_job": "POST /chat/jobs",
            "poll_job": "GET /chat/jobs/{job_id}",
            "sample_queries": "GET /chat/sample-queries",
            "health": "GET /chat/health",
            "status": "GET /chat/status",
            "validate": "POST /chat/validate",
            "capabilities": "GET /chat/capabilities",
        },
    }


@app.get("/api/v1/agent-memory/status")
async def agent_memory_status():
    """Return graph-native agent memory availability and operating mode."""
    if AgentMemoryService is None:
        return {
            "enabled": False,
            "status": "unavailable",
            "message": "Agent memory service could not be imported.",
        }
    return {"status": "ok", **AgentMemoryService.status()}


@app.get("/api/v1/agent-memory/sessions/{session_id}/context")
async def agent_memory_session_context(request: Request, session_id: str, limit: int = Query(6, ge=1, le=20)):
    """Return compact recent memory for a chat session."""
    if AgentMemoryService is None:
        raise HTTPException(status_code=503, detail="Agent memory service unavailable")
    if not request.scope.get("session_id_supplied") or request.scope.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="Session context is not available for this client session")
    return AgentMemoryService.recent_context(session_id, limit=limit)


@app.get("/chat/capabilities")
async def chat_capabilities():
    return {
        "name": "knowledge-companion",
        "integration_pattern": "POST for question execution, GET for discovery/health/sample prompts",
        "endpoints": {
            "validate": {
                "method": "POST",
                "path": "/chat/validate",
                "description": "Validates Teamcenter/AWC or external request body without invoking the model.",
                "body": {
                    "session_id": "string optional; use the server-issued X-Session-ID header",
                    "message": "string",
                    "graph_context": "object optional"
                }
            },
            "async_job": {
                "method": "POST",
                "path": "/chat/jobs",
                "description": "Submits a long-running chat request and returns a job id for polling.",
                "poll": "GET /chat/jobs/{job_id}"
            },
            "ask": {
                "method": "POST",
                "path": "/chat",
                "body": {
                    "session_id": "string optional; use the server-issued X-Session-ID header",
                    "message": "string",
                    "graph_context": "optional object",
                },
            },
            "stream": {
                "method": "POST",
                "path": "/chat-stream",
                "body": {
                    "session_id": "string optional; use the server-issued X-Session-ID header",
                    "message": "string",
                    "graph_context": "optional object",
                },
            },
            "sample_queries": {
                "method": "GET",
                "path": "/chat/sample-queries",
            },
            "health": {
                "method": "GET",
                "path": "/chat/health",
            },
        },
        "notes": [
            "Use POST /chat for Teamcenter action-handler invocations that execute a user question.",
            "Use GET companion endpoints for readiness checks, UI bootstrap, and integration discovery.",
            "GET should not be used for prompt execution because prompts can be large and may carry graph context.",
        ],
    }


@app.get("/chat/sample-queries")
async def get_sample_queries():
    """Return dynamically generated sample queries based on actual Neo4j data.

    Picks representative entities from each domain:
      - ProvidedPart  → motor component queries
      - GeneralOperation / HeaderOperation → assembly process queries
      - MbseNode Class → SysML MBSE queries
      - UseCase → use-case queries
    Falls back to ontology-registry-driven templates when the graph is empty.
    """
    try:
        from chains.cypher import query_cypher
        from Services.ontology_upload_manager import OntologyUploadManager
        try:
            registry = OntologyUploadManager.list_ontologies_with_neo4j_counts(graph)
        except Exception:
            registry = OntologyUploadManager.list_ontologies()

        def _fetch(cypher):
            try:
                return [r.get("name") for r in query_cypher(cypher) if r.get("name")]
            except Exception:
                return []

        parts       = _fetch("""
            MATCH (n)
            WHERE n.name IS NOT NULL
              AND (any(lbl IN labels(n) WHERE lbl IN ['ProvidedPart', 'Part', 'Product', 'ProductRevision']) OR toLower(coalesce(n.element_type, '')) CONTAINS 'part')
            RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 5
        """)
        operations  = _fetch("""
            MATCH (n)
            WHERE n.name IS NOT NULL
              AND (any(lbl IN labels(n) WHERE lbl IN ['GeneralOperation', 'HeaderOperation', 'LoadingOperation', 'Process']) OR toLower(coalesce(n.element_type, '')) CONTAINS 'operation')
            RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 3
        """)
        assemblies  = _fetch("""
            MATCH (n)
            WHERE n.name IS NOT NULL
              AND (any(lbl IN labels(n) WHERE lbl IN ['ManufacturingAssembly', 'Assembly']) OR toLower(coalesce(n.element_type, '')) CONTAINS 'assembly')
            RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 2
        """)
        requirements = _fetch("""
            MATCH (n)
            WHERE n.name IS NOT NULL
              AND (any(lbl IN labels(n) WHERE lbl IN ['Requirement', 'RequirementRevision']) OR toLower(coalesce(n.name, '')) CONTAINS 'requirement' OR toLower(coalesce(n.element_type, '')) CONTAINS 'requirement')
            RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 5
        """)
        mbse_cls    = _fetch("MATCH (n) WHERE n.name IS NOT NULL AND size(n.name) > 3 AND any(lbl IN labels(n) WHERE lbl IN ['Class', 'MbseNode']) RETURN n.name AS name ORDER BY n.name LIMIT 3")
        use_cases   = _fetch("MATCH (n) WHERE n.name IS NOT NULL AND size(n.name) > 3 AND any(lbl IN labels(n) WHERE lbl IN ['UseCase', 'MbseNode']) RETURN n.name AS name LIMIT 2")
        packages    = _fetch("MATCH (n) WHERE n.name IS NOT NULL AND NOT n.name STARTS WITH 'Basic' AND any(lbl IN labels(n) WHERE lbl IN ['Package', 'MbseNode']) RETURN n.name AS name LIMIT 2")
        generic_entities = _fetch("""
            MATCH (n)
            WHERE n.name IS NOT NULL
              AND NOT any(lbl IN labels(n) WHERE lbl IN ['DatasheetChunk', 'GraphChunk', 'OntologyClass', 'ObjectProperty', 'DatatypeProperty'])
            RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 8
        """)
        ontology_rows = (registry.get("ontologies", []) if isinstance(registry, dict) else [])[:3]
        ontology_names = [
            str(row.get("ontology_name") or row.get("name") or row.get("prefix") or row.get("ontology_id") or "").strip()
            for row in ontology_rows
            if str(row.get("ontology_name") or row.get("name") or row.get("prefix") or row.get("ontology_id") or "").strip()
        ]

        data_available = any([parts, operations, assemblies, requirements, mbse_cls, use_cases, ontology_names, generic_entities])

        if data_available:
            part1  = parts[0]       if parts       else (generic_entities[0] if generic_entities else "selected part")
            part2  = parts[1]       if len(parts) > 1 else (generic_entities[1] if len(generic_entities) > 1 else part1)
            part3  = parts[2]       if len(parts) > 2 else (generic_entities[2] if len(generic_entities) > 2 else part1)
            asm1   = assemblies[0]  if assemblies  else (generic_entities[0] if generic_entities else "selected assembly")
            op1    = operations[0]  if operations  else "#170_Operation-FDA Unit Electric A"
            cls1   = mbse_cls[0]    if mbse_cls    else "Variable Speed Drive"
            cls2   = mbse_cls[1]    if len(mbse_cls) > 1 else "Sugar Production Plant"
            uc1    = use_cases[0]   if use_cases   else (requirements[0] if requirements else "selected requirement")
            pkg1   = packages[0]    if packages    else "2 Functional Analysis"
            onto1  = ontology_names[0] if ontology_names else "the selected ontology"
            onto2  = ontology_names[1] if len(ontology_names) > 1 else onto1

            sample_queries = []
            if assemblies:
                sample_queries.extend([
                    f'What are all the parts in the "{asm1}" and in what sequence are they assembled?',
                    f'Show the complete assembly operation sequence for "{asm1}"',
                ])
            if parts:
                sample_queries.extend([
                    f'Recommend manufacturing processes for "{part1}"',
                    f'Find parts similar to "{part2}" that could be substituted',
                    f'What operations does "{part3}" go through during assembly?',
                    f'Analyse change impact if "{part1}" is modified',
                ])
            if requirements:
                sample_queries.append(f'Trace requirement context and downstream realization for "{uc1}"')
            if mbse_cls or use_cases:
                sample_queries.extend([
                    f'What are the SysML requirements related to "{cls1}"?',
                    f'Show all use cases and actors in the "{pkg1}" package',
                    f'Trace the MBSE requirements for use case "{uc1}"',
                    f'Which SysML blocks are associated with "{cls2}"?',
                ])
            if generic_entities:
                sample_queries.extend([
                    f'Show one-hop graph context for "{generic_entities[0]}"',
                    f'Find traceability links around "{generic_entities[min(1, len(generic_entities)-1)]}"',
                ])
            sample_queries.extend([
                f'What ontology classes does "{onto1}" expose?',
                f'Compare the taxonomy of "{onto1}" and "{onto2}"',
            ])
            sample_queries = sample_queries[:8]
        else:
            # Registry-driven fallbacks for empty graphs
            ontology1 = ontology_names[0] if ontology_names else "the selected ontology"
            ontology2 = ontology_names[1] if len(ontology_names) > 1 else ontology1
            sample_queries = [
                f'Show the ontology graph for "{ontology1}"',
                f'List the classes, properties, and individuals in "{ontology1}"',
                f'Show the taxonomy for "{ontology1}"',
                f'Find the active ontology scopes available in this workspace',
                f'Compare "{ontology1}" and "{ontology2}" for overlapping concepts',
                'Recommend manufacturing processes for the selected part',
                'Find similar parts using the currently loaded graph data',
                'Analyse change impact for a selected entity in the active ontology scope',
            ]

        all_entities = parts + operations + assemblies + requirements + mbse_cls + use_cases + generic_entities
        return JSONResponse({
            "queries": sample_queries,
            "data_available": data_available,
            "entity_count": len(all_entities),
            "sample_entities": all_entities[:8],
            "ontology_scopes": ontology_names,
        })

    except Exception as e:
        logger.error(f"Sample queries error: {e}", exc_info=True)
        return JSONResponse({
            "queries": [
                'Show the ontology graph for the selected ontology',
                'List the classes, properties, and individuals in the selected ontology',
                'Show the taxonomy for the selected ontology',
                'Find the active ontology scopes available in this workspace',
                'Compare two loaded ontologies for overlapping concepts',
                'Recommend manufacturing processes for the selected part',
                'Find similar parts using the currently loaded graph data',
                'Analyse change impact for a selected entity in the active ontology scope',
            ],
            "data_available": False,
            "error": "Could not fetch dynamic queries from database",
        })


# @app.post("/reset")
# def reset(request: ResetRequest):
#     reset_memory(request.session_id)
#     return {"status": "ok"}

# @app.post("/chat-with-cypher", response_model=ChatWithCypherResponse)
# def chat_with_cypher(request: ChatRequest):
#     """Enhanced chat endpoint that returns both response and raw Cypher results"""
#     try:
#         result = generate_response_with_cypher(request.session_id, request.message)
#         return ChatWithCypherResponse(
#             session_id=result["session_id"],
#             response=result["response"],
#             raw_results=result["raw_results"]
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

from backend.core.graphvis_cache import graphvis_cache as _graphvis_cache
_GRAPHVIS_CACHE_TTL = 60  # 60 seconds — short enough that deleting Neo4j clears within a minute
from backend.core.graphvis_cache import GRAPHVIS_CACHE_ENABLED as _GRAPHVIS_CACHE_ENABLED

from backend.core.graphvis_cache import invalidate_graphvis_cache

@app.get("/health/neo4j")
async def check_neo4j_health():
    """Health check endpoint to verify Neo4j connectivity"""
    try:
        loop = asyncio.get_event_loop()

        def _official_driver_probe():
            try:
                from backend.core.db_config import get_config, get_driver
            except Exception:
                from core.db_config import get_config, get_driver
            config = get_config()
            with get_driver().session(database=config.database) as session:
                record = session.run("RETURN 1 AS ok").single()
                return record and record.get("ok") == 1

        result = await asyncio.wait_for(
            loop.run_in_executor(None, _official_driver_probe),
            timeout=5.0
        )
        is_connected = bool(result)
        if not is_connected:
            invalidate_graphvis_cache()
            return JSONResponse(status_code=503, content={
                "status": "unhealthy",
                "error_code": "NEO4J_UNAVAILABLE",
                "neo4j_connected": False,
                "timestamp": time.time(),
            })
        return {
            "status": "healthy",
            "neo4j_connected": True,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.warning(f"Neo4j health check failed: {type(e).__name__}: {str(e)}")
        # Invalidate cache on health check failure
        invalidate_graphvis_cache()
        return JSONResponse(status_code=503, content={
            "status": "unhealthy",
            "error_code": "NEO4J_UNAVAILABLE",
            "neo4j_connected": False,
            "detail": "Neo4j is unavailable.",
            "timestamp": time.time()
        })

@app.get("/graphvis")
async def get_entire_graph():
    import asyncio, time
    now = time.monotonic()
    if _GRAPHVIS_CACHE_ENABLED and _graphvis_cache["data"] is not None and (now - _graphvis_cache["ts"]) < _GRAPHVIS_CACHE_TTL:
        cached = _graphvis_cache["data"]
        has_edges = any(isinstance(row, dict) and row.get("r") for row in cached)
        if has_edges:
            return {"results": cached}

    connected_query = """
        MATCH (n)-[r]->(m)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
        RETURN
          {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          {elementId: elementId(r), type: type(r), properties: properties(r),
           start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
          {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
        LIMIT 2000
    """
    isolated_query = """
        MATCH (n)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
          AND NOT (n)--()
        RETURN
          {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          null AS r, null AS m
        LIMIT 500
    """
    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: graph.query(connected_query)),
            timeout=300.0
        )
        try:
            isolated = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: graph.query(isolated_query)),
                timeout=10.0
            )
            results = results + isolated
        except Exception:
            pass
        if results and _GRAPHVIS_CACHE_ENABLED:
            _graphvis_cache["data"] = results
            _graphvis_cache["ts"] = time.monotonic()
        return {"results": results}
    except asyncio.TimeoutError:
        logger.warning("/graphvis timed out — clearing cache and returning empty graph")
        # Clear cache on timeout to force fresh query on next attempt
        invalidate_graphvis_cache()
        return JSONResponse(status_code=504, content={
            "status": "error", "error_code": "GRAPH_QUERY_TIMEOUT", "results": [],
            "message": "Graph query timed out. Try a more specific ontology type filter.",
        })
    except Exception as e:
        logger.warning(f"/graphvis error: {type(e).__name__}: {str(e)}")
        # Clear cache on any error to prevent serving stale data
        invalidate_graphvis_cache()
        return JSONResponse(status_code=503, content={
            "status": "error", "error_code": "GRAPH_SERVICE_UNAVAILABLE", "results": [],
            "message": "Neo4j database temporarily unavailable.",
        })


def _empty_graph_service_response(message: str, *, status_code: int = 503) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "unavailable",
            "message": message,
            "nodes": [],
            "relationships": [],
            "counts": {"nodes": 0, "relationships": 0},
        },
    )


@app.get("/api/v1/graph/view")
async def get_graph_view(limit: int = 750, scope: str = "all"):
    """Return a visualization-ready graph payload using the official Neo4j driver."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    try:
        return GraphViewService.get_graph_overview(limit=limit, scope=scope)
    except RuntimeError as exc:
        raise _graph_service_unavailable("/api/v1/graph/view", exc)


@app.get("/api/v1/code-audit")
async def get_code_audit(refresh: bool = Query(default=False)):
    """Return the repository dependency graph, optionally rebuilding it first."""
    try:
        from tools.code_graph_audit import OUTPUT, audit

        if refresh or not OUTPUT.exists():
            report = await run_in_threadpool(audit)
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        else:
            report = json.loads(OUTPUT.read_text(encoding="utf-8"))
        report["generated_at"] = FileSystemPath(OUTPUT).stat().st_mtime
        return report
    except Exception as exc:
        logger.exception("Code audit generation failed")
        raise HTTPException(status_code=500, detail="Code audit generation failed") from exc


@app.get("/api/v1/graph/view/architecture/{prefix}")
async def get_architecture_process_view(prefix: str = "archimate", limit: int = 750):
    """Return connected architecture/process model graph view, including ArchiMate imports."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    try:
        return GraphViewService.get_architecture_process_view(prefix=prefix, limit=limit)
    except Exception as exc:
        logger.warning("/api/v1/graph/view/architecture/%s unavailable: %s", prefix, exc)
        return {
            "status": "unavailable",
            "message": str(exc),
            "nodes": [],
            "relationships": [],
            "counts": {"nodes": 0, "relationships": 0},
            "view": {"type": "architecture-process", "prefix": prefix},
        }


@app.get("/api/v1/graph/view/ontology/{prefix}")
async def get_virtual_ontology_view(prefix: str, limit: int = 750):
    """Return a generated ontology-centric graph view without mutating base data."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    try:
        return GraphViewService.get_virtual_ontology_view(prefix=prefix, limit=limit)
    except RuntimeError as exc:
        raise _graph_service_unavailable(f"/api/v1/graph/view/ontology/{prefix}", exc)


@app.get("/api/v1/graph/contextual-subgraph")
async def get_contextual_subgraph(
    search: str = "",
    ontology_prefix: str = "",
    import_id: str = "",
    limit: int = 400,
    search_mode: str = "best",
    expand_neighbors: bool = False,
):
    """Return a contextual subgraph for GraphRAG-style inspection."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    try:
        return await run_in_threadpool(
            GraphViewService.get_contextual_subgraph,
            search=search,
            ontology_prefix=ontology_prefix,
            import_id=import_id,
            limit=limit,
            expand_neighbors=expand_neighbors,
            search_mode=search_mode,
        )
    except RuntimeError as exc:
        raise _graph_service_unavailable("/api/v1/graph/contextual-subgraph", exc)


def _requirement_source_bucket(source_value: str, labels: list[str] | None = None) -> str:
    text = str(source_value or "").lower()
    label_text = " ".join(labels or []).lower()
    combined = f"{text} {label_text}"
    if "reqif" in combined:
        return "ReqIF"
    if "plmxml" in combined:
        return "PLMXML"
    if "xmi" in combined or "sysml" in combined or "mbse" in combined or "mdxml" in combined:
        return "MBSE"
    if "oslc" in combined:
        return "OSLC"
    if "alm" in combined or "teamcenter" in combined or "polarion" in combined or "doors" in combined:
        return "ALM"
    if "document" in combined or "unstructured" in combined or "pdf" in combined or "doc" in combined or "html" in combined:
        return "Unstructured"
    return "Graph"


@app.get("/api/v1/requirements")
async def get_normalized_requirements(
    source: str = "all",
    search: str = "",
    limit: int = Query(default=500, ge=1, le=5000),
):
    """Return normalized requirement-like records from the live context graph.

    This endpoint intentionally stays source-neutral: PLMXML, ReqIF, MBSE/XMI,
    OSLC, ALM, and unstructured ingestion can all project requirement-like nodes
    into the same table and GraphRAG context without forcing the UI to know each
    parser's internal schema.
    """
    try:
        from backend.core.graph import query_with_timeout
    except Exception:
        from core.graph import query_with_timeout

    source_norm = str(source or "all").strip().lower()
    search_norm = _normalize_search_term(search)
    cypher = """
    MATCH (n)
    WITH n, labels(n) AS node_labels, properties(n) AS p
    WITH n, node_labels, p,
         toLower(coalesce(
           toString(p['source_format']),
           toString(p['file_format']),
           toString(p['source_system']),
           toString(p['source']),
           toString(p['ontology_prefix']),
           ''
         )) AS source_hint,
         coalesce(
           toString(p['requirement_id']),
           toString(p['requirement_ref']),
           toString(p['identifier']),
           toString(p['code']),
           toString(p['id']),
           toString(p['uid']),
           elementId(n)
         ) AS requirement_id,
         coalesce(
           toString(p['title']),
           toString(p['name']),
           toString(p['label']),
           toString(p['requirement_id']),
           toString(p['id']),
           elementId(n)
         ) AS title,
         coalesce(
           toString(p['description']),
           toString(p['text']),
           toString(p['body']),
           toString(p['value']),
           toString(p['statement']),
           ''
         ) AS requirement_text,
         coalesce(
           toString(p['semantic_role']),
           toString(p['element_type']),
           toString(p['entity_type']),
           ''
         ) AS semantic_role
    WITH n, node_labels, p, source_hint, requirement_id, title, requirement_text, semantic_role,
         toLower(coalesce(toString(p['row_type']), '')) AS row_type,
         toLower(coalesce(toString(p['type_ref']), '')) AS type_ref,
         toLower(coalesce(toString(p['original_id']), '')) AS original_id,
         toLower(requirement_id + ' ' + title + ' ' + requirement_text + ' ' + semantic_role + ' ' + source_hint + ' ' + reduce(acc = '', lbl IN node_labels | acc + ' ' + lbl)) AS haystack
    WHERE
      NOT any(lbl IN node_labels WHERE lbl IN ['OntologyClass', 'OntologyProperty', 'OntologyDatatypeProperty', 'OntologyObjectProperty', 'OntologyAnnotationProperty'])
      AND NOT (toLower(requirement_id) =~ '^id[0-9]+$' AND NOT (haystack CONTAINS 'requirement' OR row_type IN ['requirement', 'requirementrelation', 'relation', 'specification']))
      AND (
        any(lbl IN node_labels WHERE lbl IN ['Requirement', 'RequirementRevision', 'RequirementRelation'])
        OR semantic_role IN ['Requirement', 'RequirementRevision', 'RequirementRelation', 'requirement', 'requirementrevision', 'requirementrelation']
        OR row_type IN ['requirement', 'requirementrelation', 'relation', 'specification']
        OR type_ref CONTAINS 'requirement'
        OR original_id STARTS WITH 'req-'
        OR toLower(requirement_id) STARTS WITH 'req-'
      )
    WITH n, node_labels, p, source_hint, requirement_id, title, requirement_text, semantic_role, haystack
    WHERE $search = '' OR haystack CONTAINS $search
    OPTIONAL MATCH (n)-[r]-(m)
    WITH n, node_labels, p, source_hint, requirement_id, title, requirement_text, semantic_role,
         collect(DISTINCT {type: type(r), other: coalesce(m.name, m.title, m.label, m.id, elementId(m))})[0..8] AS context_links,
         count(DISTINCT r) AS relationship_count
    RETURN
      elementId(n) AS element_id,
      node_labels AS labels,
      requirement_id,
      title,
      requirement_text,
      semantic_role,
      source_hint,
      coalesce(toString(p['source_file']), toString(p['filename']), toString(p['source_path']), '') AS source_file,
      coalesce(toString(p['ontology_prefix']), toString(p['prefix']), '') AS ontology_prefix,
      coalesce(toString(p['ontology_class']), toString(p['class_name']), toString(p['element_type']), '') AS ontology_class,
      coalesce(toString(p['status']), toString(p['lifecycle_status']), '') AS status,
      coalesce(toString(p['owner']), toString(p['author']), '') AS owner,
      relationship_count,
      context_links
    ORDER BY requirement_id, title
    LIMIT toInteger($limit)
    """
    try:
        rows = query_with_timeout(cypher, {"search": search_norm, "limit": limit}, timeout=60) or []
    except Exception as exc:
        raise _graph_service_unavailable("/api/v1/requirements", exc)

    requirements_by_key: dict[str, dict] = {}
    for row in rows:
        source_bucket = _requirement_source_bucket(row.get("source_hint"), row.get("labels") or [])
        if source_norm not in {"", "all"} and source_bucket.lower() != source_norm:
            continue
        requirement_id = row.get("requirement_id") or row.get("element_id")
        item = {
            "id": requirement_id,
            "requirement_id": requirement_id,
            "title": row.get("title") or requirement_id or row.get("element_id"),
            "text": row.get("requirement_text") or "",
            "source": source_bucket,
            "source_hint": row.get("source_hint") or "",
            "source_file": row.get("source_file") or "",
            "ontology_prefix": row.get("ontology_prefix") or "",
            "ontology_class": row.get("ontology_class") or "",
            "semantic_role": row.get("semantic_role") or "",
            "status": row.get("status") or "",
            "owner": row.get("owner") or "",
            "labels": row.get("labels") or [],
            "element_id": row.get("element_id"),
            "relationship_count": int(row.get("relationship_count") or 0),
            "context_links": [link for link in (row.get("context_links") or []) if link.get("type") and link.get("other")],
        }
        dedupe_key = f"{source_bucket.lower()}::{str(requirement_id or item['title']).lower()}"
        existing = requirements_by_key.get(dedupe_key)
        if not existing:
            requirements_by_key[dedupe_key] = item
            continue

        merged_labels = list(dict.fromkeys((existing.get("labels") or []) + (item.get("labels") or [])))
        merged_links = list({
            (str(link.get("type")), str(link.get("other"))): link
            for link in ((existing.get("context_links") or []) + (item.get("context_links") or []))
            if link.get("type") and link.get("other")
        }.values())[:12]
        prefer_item = (
            "Requirement" in (item.get("labels") or [])
            and "Requirement" not in (existing.get("labels") or [])
        )
        base = item if prefer_item else existing
        base["labels"] = merged_labels
        base["context_links"] = merged_links
        base["relationship_count"] = max(int(existing.get("relationship_count") or 0), int(item.get("relationship_count") or 0), len(merged_links))
        if not base.get("text"):
            base["text"] = item.get("text") or existing.get("text") or ""
        requirements_by_key[dedupe_key] = base

    requirements = list(requirements_by_key.values())
    source_counts: dict[str, int] = {}
    for item in requirements:
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1

    return {
        "status": "success",
        "requirements": requirements,
        "count": len(requirements),
        "source_counts": source_counts,
        "sources": ["ReqIF", "PLMXML", "MBSE", "OSLC", "ALM", "Unstructured", "Graph"],
        "search": search,
        "source": source,
    }


@app.get("/graphvis/by-ontology/{prefix}")
async def get_graph_by_ontology(prefix: str):
    """Get graph filtered by ontology prefix - shows OntologyClass and Instance nodes."""
    import asyncio
    import re
    from pathlib import Path

    # Validate prefix: only allow alphanumeric and underscore/hyphen to prevent injection
    if not re.match(r"^[a-zA-Z0-9_-]{1,50}$", prefix):
        return {"results": [], "prefix": prefix, "error": "Invalid prefix format"}

    prefix_safe = prefix.lower()

    # Return both connected edges and isolated nodes so the UI doesn't look blank
    # when an ontology has sparse relationships.
    connected_query = """
    MATCH (n)-[r]->(m)
    WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
      AND (
        n.prefix = $prefix OR n.ontology_prefix = $prefix OR
        m.prefix = $prefix OR m.ontology_prefix = $prefix
      )
    RETURN
      {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
      {elementId: elementId(r), type: type(r), properties: properties(r),
        start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
      {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
    LIMIT 2000
    """

    isolated_query = """
    MATCH (n)
    WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
      AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
      AND NOT (n)--()
    RETURN
      {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
      null AS r, null AS m
    LIMIT 500
    """

    # Fallback: include nodes even if they have relationships only to excluded chunk nodes.
    # This keeps the visualization from appearing blank for schema-only ontologies.
    nodes_query = """
    MATCH (n)
    WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
      AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
    RETURN
      {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
      null AS r, null AS m
    LIMIT 500
    """

    def _bootstrap_if_missing(prefix_token: str) -> bool:
        """Best-effort: load a known sample XMI for sysml/ap239 into Neo4j as schema nodes.

        Returns True when the prefix now has at least one node.
        """
        try:
            # If any nodes exist already, do nothing.
            existing = graph.query(
                """
                MATCH (n)
                WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                RETURN count(n) AS c
                """,
                params={"prefix": prefix_token},
            )
            if (existing or [{}])[0].get("c", 0) > 0:
                return True

            if prefix_token not in {"sysml", "ap239"}:
                return False

            # Pick a sample XMI from the repo.
            workspace_root = Path(__file__).resolve().parents[1]

            sample_path: Path | None = None
            ontology_name = prefix_token.upper()
            description = "Bootstrapped from workspace sample file"

            if prefix_token == "sysml":
                candidates = list((workspace_root / "backend" / "uploads").glob("**/SugarPlantMBSE.xmi"))
                if candidates:
                    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    sample_path = candidates[0]
                    ontology_name = "Sugar Plant MBSE (SysML)"

            if prefix_token == "ap239" and sample_path is None:
                ap239_candidates = [
                    workspace_root
                    / "data"
                    / "domain_models"
                    / "product_life_cycle_support"
                    / "Domain_model_4439_XMI"
                    / "STEPlib"
                    / "Application_protocols"
                    / "AP239"
                    / "AP239.xmi",
                    workspace_root
                    / "data"
                    / "domain_models"
                    / "product_life_cycle_support"
                    / "Domain_model_4439_XMI"
                    / "STEPlib"
                    / "Application_protocols"
                    / "AP239"
                    / "Domain_model"
                    / "Domain_model.xmi",
                ]
                for p in ap239_candidates:
                    if p.exists():
                        sample_path = p
                        ontology_name = "AP239"
                        break

            if sample_path is None or not sample_path.exists():
                return False

            from Services.ontology_upload_manager import OntologyUploadManager

            file_content = sample_path.read_bytes()
            save_result = OntologyUploadManager.save_ontology_file(
                file_content=file_content,
                filename=sample_path.name,
                ontology_name=ontology_name,
                prefix=prefix_token,
                file_type="xmi",
                generation_type="as_is",
                description=description,
                schema_type="schema",
            )
            if save_result.get("status") != "success":
                return False

            ontology_id = save_result.get("ontology_id")
            push_result = OntologyUploadManager.push_to_neo4j(ontology_id, graph, schema_type="schema")
            if push_result.get("status") != "success":
                return False

            # Confirm nodes now exist.
            after = graph.query(
                """
                MATCH (n)
                WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                RETURN count(n) AS c
                """,
                params={"prefix": prefix_token},
            )
            return (after or [{}])[0].get("c", 0) > 0
        except Exception:
            return False

    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: graph.query(connected_query, params={"prefix": prefix_safe})),
            timeout=300.0,
        )

        try:
            isolated = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: graph.query(isolated_query, params={"prefix": prefix_safe})),
                timeout=10.0,
            )
            results = (results or []) + (isolated or [])
        except Exception:
            pass

        # If we still have no rows, return a sample of nodes for this prefix.
        if not results:
            try:
                nodes_only = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: graph.query(nodes_query, params={"prefix": prefix_safe})),
                    timeout=10.0,
                )
                results = nodes_only or []
            except Exception:
                pass

        # If still empty for sysml/ap239, attempt a one-time bootstrap from bundled sample files.
        if not results and prefix_safe in {"sysml", "ap239"}:
            try:
                bootstrapped = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: _bootstrap_if_missing(prefix_safe)),
                    timeout=300.0,
                )
                if bootstrapped:
                    nodes_only = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: graph.query(nodes_query, params={"prefix": prefix_safe})),
                        timeout=10.0,
                    )
                    results = nodes_only or []
            except Exception:
                pass

        return {"results": results, "prefix": prefix_safe, "count": len(results)}
    except Exception as e:
        logger.warning(f"/graphvis/by-ontology error: {type(e).__name__}: {str(e)}")
        return {"results": [], "prefix": prefix_safe, "error": str(e)}


ONTOLOGY_VISUALIZATION_CYPHER = """
MATCH (n)-[r]->(m)
WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
  AND (
    n.prefix = $prefix OR n.ontology_prefix = $prefix OR
    m.prefix = $prefix OR m.ontology_prefix = $prefix
  )
RETURN
  {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
  {elementId: elementId(r), type: type(r), properties: properties(r),
    start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
  {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
LIMIT 2000
"""


async def ontology_debug_payload(ontology_id: str):
    """Return ontology generation, Neo4j load, and visualization diagnostics."""
    try:
        from Services.ontology_upload_manager import OntologyUploadManager
    except Exception:
        from backend.Services.ontology_upload_manager import OntologyUploadManager

    meta_result = OntologyUploadManager.get_ontology(ontology_id)
    metadata = meta_result.get("metadata") if meta_result.get("status") == "success" else {}
    prefix = (metadata or {}).get("prefix") or ontology_id
    owl_file_path = (metadata or {}).get("owl_file_path", "")

    counts_q = """
    MATCH (n)
    WHERE n.prefix = $prefix OR n.ontology_prefix = $prefix OR n.source_ontology = $ontology_id
    WITH collect(n) AS nodes
    UNWIND nodes AS n
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE m.prefix = $prefix OR m.ontology_prefix = $prefix OR m.source_ontology = $ontology_id
    RETURN
      size(nodes) AS node_count,
      count(DISTINCT r) AS relationship_count,
      sum(CASE WHEN n:OntologyClass THEN 1 ELSE 0 END) AS class_count,
      sum(CASE WHEN n:ObjectProperty THEN 1 ELSE 0 END) AS object_property_count,
      sum(CASE WHEN n:DatatypeProperty THEN 1 ELSE 0 END) AS datatype_property_count,
      sum(CASE WHEN type(r) = 'SUBCLASS_OF' THEN 1 ELSE 0 END) AS subclass_relationship_count
    """
    sample_nodes_q = """
    MATCH (n)
    WHERE n.prefix = $prefix OR n.ontology_prefix = $prefix OR n.source_ontology = $ontology_id
    RETURN elementId(n) AS elementId, labels(n) AS labels, properties(n) AS properties
    LIMIT 10
    """
    sample_rels_q = """
    MATCH (n)-[r]->(m)
    WHERE (n.prefix = $prefix OR n.ontology_prefix = $prefix OR n.source_ontology = $ontology_id)
      AND (m.prefix = $prefix OR m.ontology_prefix = $prefix OR m.source_ontology = $ontology_id)
    RETURN elementId(r) AS elementId, type(r) AS type,
           elementId(startNode(r)) AS start, elementId(endNode(r)) AS end,
           properties(r) AS properties
    LIMIT 10
    """

    try:
        counts = (graph.query(counts_q, params={"prefix": prefix, "ontology_id": ontology_id}) or [{}])[0]
        sample_nodes = graph.query(sample_nodes_q, params={"prefix": prefix, "ontology_id": ontology_id}) or []
        sample_relationships = graph.query(sample_rels_q, params={"prefix": prefix, "ontology_id": ontology_id}) or []
    except Exception as exc:
        counts = {"error": str(exc)}
        sample_nodes = []
        sample_relationships = []

    return {
        "ontology_id": ontology_id,
        "ontology_metadata": metadata,
        "owl_file_path": owl_file_path,
        "parsed_class_count": metadata.get("parsed_class_count", 0) if metadata else 0,
        "parsed_property_count": (
            (metadata.get("parsed_object_property_count", 0) if metadata else 0)
            + (metadata.get("parsed_datatype_property_count", 0) if metadata else 0)
        ),
        "parsed_relationship_count": (
            (metadata.get("parsed_subclass_relationship_count", 0) if metadata else 0)
            + (metadata.get("parsed_domain_relationship_count", 0) if metadata else 0)
            + (metadata.get("parsed_range_relationship_count", 0) if metadata else 0)
        ),
        "neo4j_node_count": counts.get("node_count", 0),
        "neo4j_relationship_count": counts.get("relationship_count", 0),
        "neo4j_counts": counts,
        "sample_nodes": sample_nodes,
        "sample_relationships": sample_relationships,
        "cypher_query_used_by_visualization": ONTOLOGY_VISUALIZATION_CYPHER,
    }


@app.get("/api/ontology/{ontology_id}/debug")
@app.get("/api/v1/ontology/{ontology_id}/debug")
async def debug_ontology(ontology_id: str):
    return await ontology_debug_payload(ontology_id)


@app.get("/api/v1/ontology/{ontology_id}/taxonomy")
async def get_uploaded_ontology_taxonomy(ontology_id: str):
    """Return extracted taxonomy terms and hierarchy links for an uploaded ontology."""
    try:
        from backend.Services.ontology_taxonomy_service import OntologyTaxonomyService

        return OntologyTaxonomyService.get_taxonomy(ontology_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Ontology taxonomy degraded for %s: %s", ontology_id, e)
        return {
            "status": "degraded",
            "ontology_id": ontology_id,
            "prefix": ontology_id,
            "source_filename": "",
            "extraction_source": "error",
            "nodes": [],
            "edges": [],
            "reasoning_summary": {},
            "summary": {"terms": 0, "taxonomy_links": 0, "triple_count": 0},
            "diagnostics": [{"severity": "error", "message": str(e)}],
        }


@app.get("/api/v1/ontology/{ontology_id}/reason")
async def get_uploaded_ontology_reasoning(ontology_id: str):
    """Return cached Owlready2-backed classes, properties, individuals, and diagnostics."""
    try:
        from backend.Services.ontology_taxonomy_service import OntologyTaxonomyService

        return OntologyTaxonomyService.get_reasoning(ontology_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Ontology reasoning degraded for %s: %s", ontology_id, e)
        return {
            "status": "degraded",
            "engine": "owlready2",
            "available": False,
            "ontology_id": ontology_id,
            "prefix": ontology_id,
            "classes": [],
            "object_properties": [],
            "datatype_properties": [],
            "annotation_properties": [],
            "individuals": [],
            "subclass_edges": [],
            "diagnostics": [{"severity": "error", "message": str(e)}],
            "summary": {},
        }


@app.post("/api/v1/ontology/{ontology_id}/inference/preview")
async def preview_uploaded_ontology_inference(ontology_id: str, body: dict | None = None):
    """Preview selectable ontology inferences without mutating Neo4j."""
    try:
        from backend.Services.ontology_reasoning_service import OntologyReasoningService

        return OntologyReasoningService.preview_inferences(ontology_id, body or {})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        safe_error("/api/v1/ontology/{ontology_id}/inference/preview", e)
        raise HTTPException(status_code=500, detail="Ontology service failed. Please try again later.") from e


@app.get("/api/v1/ontology/{ontology_id}/data-dictionary")
def get_registered_ontology_data_dictionary(ontology_id: str):
    """Return a generic ontology data dictionary for any registered ontology id or prefix."""
    try:
        from backend.Services.ontology_reasoning_service import OntologyReasoningService
    except ImportError:
        from Services.ontology_reasoning_service import OntologyReasoningService
    try:
        reasoning = OntologyReasoningService.get_reasoning(ontology_id)

        def entry(row, kind):
            label = str(row.get("label") or row.get("name") or row.get("term_id") or row.get("iri") or "").strip()
            if not label:
                return None
            return label, {
                "label": label,
                "iri": row.get("iri") or row.get("uri") or row.get("term_id") or label,
                "definition": row.get("definition") or row.get("comment") or "",
                "kind": kind,
                "domain": row.get("domain") or [],
                "range": row.get("range") or [],
                "source": "owlready2_reasoning",
            }

        entities = {}
        properties = {}
        relationships = {}
        for row in reasoning.get("classes") or []:
            item = entry(row, "Class")
            if item:
                entities[item[0]] = item[1]
        for row in reasoning.get("datatype_properties") or []:
            item = entry(row, "DatatypeProperty")
            if item:
                properties[item[0]] = item[1]
        for row in reasoning.get("object_properties") or []:
            item = entry(row, "ObjectProperty")
            if item:
                relationships[item[0]] = {**item[1], "type": "objectProperty", "connections": []}
        for row in reasoning.get("annotation_properties") or []:
            item = entry(row, "AnnotationProperty")
            if item:
                properties.setdefault(item[0], item[1])

        return {
            "status": "success",
            "ontology_id": reasoning.get("ontology_id") or ontology_id,
            "prefix": reasoning.get("prefix") or ontology_id,
            "total_terms": len(entities) + len(properties) + len(relationships),
            "data": {
                "entities": entities,
                "properties": properties,
                "relationships": relationships,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        safe_error("/api/v1/ontology/{ontology_id}/data-dictionary", e)
        raise HTTPException(status_code=500, detail="Ontology service failed. Please try again later.") from e


@app.get("/api/v1/ontology/{ontology_id}/mappings/{mapping_type}")
def get_registered_ontology_mapping_edges(ontology_id: str, mapping_type: str):
    """Return mapping edges for a registered ontology; empty is valid for OWL-only ontologies."""
    try:
        from backend.Services.ontology_reasoning_service import OntologyReasoningService
        resolved = OntologyReasoningService.resolve_ontology_id(ontology_id) or ontology_id
        return {
            "status": "success",
            "ontology_id": resolved,
            "mapping_type": mapping_type,
            "mappings": {},
            "mapping_edges": [],
            "message": "No curated mapping edges are stored for this ontology yet. Use Semantic Bridge to create mappings.",
        }
    except Exception as e:
        safe_error("/api/v1/ontology/{ontology_id}/mappings/{mapping_type}", e)
        raise HTTPException(status_code=500, detail="Ontology service failed. Please try again later.") from e


@app.get("/ontology/registered")
async def list_ontologies_registered():
    """Alias for /ontologies/list — used by frontend OntologyContext"""
    return await list_ontologies()


@app.get("/ontologies/list")
async def list_ontologies():
    """List registered ontology prefixes with configured Neo4j runtime counts."""
    try:
        try:
            from Services.ontology_upload_manager import OntologyUploadManager
        except Exception:
            from backend.Services.ontology_upload_manager import OntologyUploadManager

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: OntologyUploadManager.list_ontologies_with_neo4j_counts(graph)),
            timeout=10.0
        )
        result["total"] = result.get("count", 0)
        return result
    except Exception as e:
        logger.warning(f"/ontologies/list error: {type(e).__name__}: {str(e)}")
        return {
            "ontologies": [],
            "status": "error",
            "error": str(e)
        }


# ────────────────────────────────────────────────────────────────────────────
# LAYER SEPARATION ENDPOINTS: Schema vs Instance Graph Visualization
# ────────────────────────────────────────────────────────────────────────────

@app.get("/schema-graph")
async def get_schema_graph():
    """
    Returns the SCHEMA LAYER (ontology graph):
    - OntologyClass, Class, ObjectProperty, DatatypeProperty nodes
    - Structured for hierarchical visualization
    - Color: Blue (#4A90E2)
    """
    schema_query = """
        MATCH (n)
        WHERE n:OntologyClass OR n:Class OR n:ObjectProperty OR n:DatatypeProperty 
           OR n.ontology_id IS NOT NULL OR n.prefix IS NOT NULL
        OPTIONAL MATCH (n)-[r]->(m)
        WHERE m:OntologyClass OR m:Class OR m:ObjectProperty OR m:DatatypeProperty 
           OR m.ontology_id IS NOT NULL OR m.prefix IS NOT NULL
        RETURN
          {
            elementId: elementId(n), 
            labels: labels(n), 
            properties: properties(n),
            layerType: 'schema',
            color: '#4A90E2'
          } AS n,
          CASE WHEN r IS NOT NULL THEN
            {
              elementId: elementId(r), 
              type: type(r), 
              properties: properties(r),
              start: elementId(startNode(r)), 
              end: elementId(endNode(r))
            }
          ELSE NULL END AS r,
          CASE WHEN m IS NOT NULL THEN
            {
              elementId: elementId(m), 
              labels: labels(m), 
              properties: properties(m),
              layerType: 'schema',
              color: '#4A90E2'
            }
          ELSE NULL END AS m
        LIMIT 1000
    """
    
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        
        # Query ontology/schema nodes
        results = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: graph.query(schema_query)),
            timeout=300.0
        )
        
        return {"results": results or [], "layerType": "schema"}
    except asyncio.TimeoutError:
        logger.warning("/schema-graph timed out")
        return JSONResponse(status_code=504, content={
            "status": "error", "error_code": "GRAPH_QUERY_TIMEOUT", "results": [],
            "message": "Schema graph query timed out",
        })
    except Exception as e:
        logger.warning(f"/schema-graph error: {type(e).__name__}: {str(e)}")
        return JSONResponse(status_code=503, content={
            "status": "error", "error_code": "GRAPH_SERVICE_UNAVAILABLE", "results": [],
            "message": "Failed to fetch schema graph",
        })


def fetch_instances_and_rels(prefix, class_ids=None):
    """Module-level helper: fetch instance nodes related to an ontology prefix or connected to class_ids.
    Returns a list of rows in the same shape as other endpoints (n, r, m).
    """
    try:
        inst_nodes = []
        inst_rels = []

        # Instances connected to known classes
        if class_ids:
            cls_ids = class_ids[:500]
            q = """
                MATCH (inst)-[r]-(cl)
                WHERE elementId(cl) IN $class_ids
                  AND NOT ('OntologyClass' IN labels(inst) OR 'Class' IN labels(inst))
                RETURN {elementId: elementId(inst), labels: labels(inst), properties: properties(inst)} AS n,
                       {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
                       {elementId: elementId(cl), labels: labels(cl), properties: properties(cl)} AS m
                LIMIT 1000
            """
            inst_rels = graph.query(q, params={"class_ids": cls_ids}) or []

        # Instances that explicitly carry the prefix/id/namespace
        prop_q = """
            MATCH (n)
            WHERE coalesce(n.ontology_prefix, '') = $prefix
               OR coalesce(n.ontology_id, '') = $prefix
               OR toLower(coalesce(n.source_ontology, '')) CONTAINS toLower($prefix)
               OR toLower(coalesce(n.namespace, '')) CONTAINS toLower($prefix)
            RETURN {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
                   null AS r, null AS m
            LIMIT 1000
        """
        inst_nodes = graph.query(prop_q, params={"prefix": prefix}) or []

        # If we have instance nodes, fetch relationships among the combined ids for richer graph
        all_ids = []
        all_ids += [r['n']['elementId'] for r in inst_nodes if r.get('n')]
        all_ids += [r['n']['elementId'] for r in inst_rels if r.get('n')]
        all_ids = list(dict.fromkeys(all_ids))[:500]

        rels = []
        if all_ids:
            rels_q = """
                MATCH (a)-[r]-(b)
                WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN {elementId: elementId(a), labels: labels(a), properties: properties(a)} AS n,
                       {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
                       {elementId: elementId(b), labels: labels(b), properties: properties(b)} AS m
                LIMIT 2000
            """
            rels = graph.query(rels_q, params={"ids": all_ids}) or []

        combined = []
        combined.extend(inst_nodes)
        combined.extend(inst_rels)
        combined.extend(rels)
        return combined
    except Exception as e:
        logger.error('Instance fetch error: %s', e, exc_info=True)
        return []


@app.get("/instance-graph")
async def get_instance_graph():
    """
    Returns the INSTANCE LAYER (contextual graph):
    - Real entities and relationships (excludes schema/ontology nodes)
    - Includes events, transactions, processes
    - Includes time, provenance, and contextual metadata
    - Color: Green for instances (#27AE60), Yellow for contextual (#F39C12)
    """
    instance_query = """
        MATCH (n)
        WHERE NOT (
            n:OntologyClass OR n:Class OR n:ObjectProperty OR n:DatatypeProperty
            OR n:DatasheetChunk OR n:GraphChunk
        )
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE NOT (
            m:OntologyClass OR m:Class OR m:ObjectProperty OR m:DatatypeProperty
            OR m:DatasheetChunk OR m:GraphChunk
        )
        RETURN
          {
            elementId: elementId(n),
            labels: labels(n),
            properties: properties(n),
            layerType: 'instance',
            color: '#27AE60'
          } AS n,
          CASE WHEN r IS NOT NULL THEN
            {
              elementId: elementId(r),
              type: type(r),
              properties: properties(r),
              start: elementId(startNode(r)),
              end: elementId(endNode(r))
            }
          ELSE NULL END AS r,
          CASE WHEN m IS NOT NULL THEN
            {
              elementId: elementId(m),
              labels: labels(m),
              properties: properties(m),
              layerType: 'instance',
              color: '#27AE60'
            }
          ELSE NULL END AS m
        LIMIT 1000
    """

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: graph.query(instance_query)),
            timeout=300.0,
        )
        return {"results": results or [], "layerType": "instance"}
    except asyncio.TimeoutError:
        logger.warning("/instance-graph timed out")
        return JSONResponse(status_code=504, content={
            "status": "error", "error_code": "GRAPH_QUERY_TIMEOUT", "results": [],
            "message": "Instance graph query timed out",
        })
    except Exception as e:
        logger.warning(f"/instance-graph error: {type(e).__name__}: {str(e)}")
        return JSONResponse(status_code=503, content={
            "status": "error", "error_code": "GRAPH_SERVICE_UNAVAILABLE", "results": [],
            "message": "Failed to fetch instance graph",
        })


@app.post("/graphfilter")
def filter_graph_nodes(request: TextSearchRequest):
    """Search graph nodes by text and return local relationships in graphvis shape.

    Search is intentionally instance/business-object first. Ontology schema terms are
    retained as fallback matches, but they should not hide data-bearing nodes for user
    searches such as REQ-* or part names.
    """
    input_val = _normalize_search_term(request.search)
    ontology_prefix = (request.ontology_prefix or "").strip()
    if not input_val:
        return {"results": []}

    wildcard_prefix_search = "*" in str(request.search or "")
    query = """
        CALL {
          MATCH (n)
          WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
            AND (
              toLower(elementId(n)) CONTAINS toLower($input)
              OR any(lbl IN labels(n) WHERE toLower(lbl) CONTAINS toLower($input))
              OR any(field IN $search_fields WHERE
                CASE
                  WHEN $wildcard_prefix_search THEN toLower(toString(coalesce(n[field], ''))) STARTS WITH toLower($input)
                  ELSE toLower(toString(coalesce(n[field], ''))) CONTAINS toLower($input)
                END
              )
            )
            AND (
              $ontology_prefix = ''
              OR n.prefix = $ontology_prefix
              OR n.ontology_prefix = $ontology_prefix
              OR EXISTS {
                MATCH (n)-[typed_rel]->(cls)
                WHERE type(typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (cls.prefix = $ontology_prefix OR cls.ontology_prefix = $ontology_prefix)
              }
            )
          RETURN n
          LIMIT 120
        UNION
          MATCH (a)-[matched_rel]-(b)
          WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk)
            AND (
              toLower(type(matched_rel)) CONTAINS toLower($input)
              OR any(field IN $relationship_search_fields WHERE
                toLower(toString(coalesce(matched_rel[field], ''))) CONTAINS toLower($input)
              )
            )
            AND (
              $ontology_prefix = ''
              OR a.prefix = $ontology_prefix
              OR a.ontology_prefix = $ontology_prefix
              OR b.prefix = $ontology_prefix
              OR b.ontology_prefix = $ontology_prefix
              OR EXISTS {
                MATCH (a)-[a_typed_rel]->(a_cls)
                WHERE type(a_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (a_cls.prefix = $ontology_prefix OR a_cls.ontology_prefix = $ontology_prefix)
              }
              OR EXISTS {
                MATCH (b)-[b_typed_rel]->(b_cls)
                WHERE type(b_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (b_cls.prefix = $ontology_prefix OR b_cls.ontology_prefix = $ontology_prefix)
              }
            )
          RETURN a AS n
          LIMIT 80
        UNION
          MATCH (a)-[matched_rel]-(b)
          WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk)
            AND (
              toLower(type(matched_rel)) CONTAINS toLower($input)
              OR any(field IN $relationship_search_fields WHERE
                toLower(toString(coalesce(matched_rel[field], ''))) CONTAINS toLower($input)
              )
            )
            AND (
              $ontology_prefix = ''
              OR a.prefix = $ontology_prefix
              OR a.ontology_prefix = $ontology_prefix
              OR b.prefix = $ontology_prefix
              OR b.ontology_prefix = $ontology_prefix
              OR EXISTS {
                MATCH (a)-[a_typed_rel]->(a_cls)
                WHERE type(a_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (a_cls.prefix = $ontology_prefix OR a_cls.ontology_prefix = $ontology_prefix)
              }
              OR EXISTS {
                MATCH (b)-[b_typed_rel]->(b_cls)
                WHERE type(b_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (b_cls.prefix = $ontology_prefix OR b_cls.ontology_prefix = $ontology_prefix)
              }
            )
          RETURN b AS n
          LIMIT 80
        }
        WITH DISTINCT n,
          toLower(toString(coalesce(
            n['name'], n['title'], n['code'], n['label'],
            n['identifier'], n['requirement_id'], n['part_number'], n['catalogue_id'], n['item_id'], n['uid'], n['id'], ''
          ))) AS displayText
        WITH n, displayText,
          CASE
            WHEN any(lbl IN labels(n) WHERE lbl IN ['OntologyClass','Class','ObjectProperty','DatatypeProperty','OntologyProperty']) THEN 900
            WHEN any(lbl IN labels(n) WHERE lbl IN ['DatasheetChunk','GraphChunk']) THEN 950
            WHEN any(lbl IN labels(n) WHERE lbl IN ['AttributeContext','MetadataWrapper','RelationshipCarrier','GeneralRelation']) THEN 850
            WHEN any(lbl IN labels(n) WHERE lbl IN ['Part','Requirement','Function','LogicalElement','PhysicalElement','Process','Product','Document']) THEN 0
            WHEN any(lbl IN labels(n) WHERE lbl IN ['Individual','ProductInstance']) AND NOT displayText STARTS WITH 'id' THEN 20
            WHEN any(lbl IN labels(n) WHERE lbl IN ['Individual','ProductInstance']) THEN 250
            ELSE 100
          END AS schemaPenalty,
          CASE
            WHEN displayText = toLower($input) THEN 0
            WHEN any(lbl IN labels(n) WHERE toLower(lbl) = toLower($input)) THEN 5
            WHEN displayText STARTS WITH toLower($input) THEN 10
            WHEN displayText STARTS WITH 'id' THEN 120
            WHEN any(lbl IN labels(n) WHERE toLower(lbl) CONTAINS toLower($input)) THEN 80
            ELSE 50
          END AS matchRank
        ORDER BY schemaPenalty ASC, matchRank ASC, displayText ASC, elementId(n) ASC
        WITH collect({node: n, schemaPenalty: schemaPenalty, matchRank: matchRank})[..90] AS rankedMatches
        WITH rankedMatches, [item IN rankedMatches | item.node] AS matchedNodes
        UNWIND range(0, size(rankedMatches) - 1) AS matchedIndex
        WITH rankedMatches[matchedIndex].node AS n, matchedIndex, matchedNodes
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE r IS NULL
           OR m IN matchedNodes
           OR toLower(type(r)) CONTAINS toLower($input)
        WITH n, r, m, matchedIndex
        ORDER BY matchedIndex ASC
        RETURN
          {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          CASE WHEN r IS NOT NULL THEN {
            elementId: elementId(r),
            type: type(r),
            properties: properties(r),
            start: elementId(startNode(r)),
            end: elementId(endNode(r))
          } ELSE null END AS r,
          CASE WHEN m IS NOT NULL THEN {
            elementId: elementId(m), labels: labels(m), properties: properties(m)
          } ELSE null END AS m
    """
    try:
        results = graph.query(query, params={
            "input": input_val,
            "ontology_prefix": ontology_prefix,
            "search_fields": GRAPH_SEARCH_PROPERTY_KEYS,
            "relationship_search_fields": GRAPH_SEARCH_RELATIONSHIP_PROPERTY_KEYS,
            "wildcard_prefix_search": wildcard_prefix_search,
        })
        return {"results": results}
    except Exception as e:
        safe_error("/graphfilter", e)


class ComparativeSearchRequest(BaseModel):
    nodeType: str = ""
    name: str = ""
    version: str = ""
    limit: int = 12


def _comparative_query_text(node_type: str, name: str, version: str) -> str:
    parts = []
    if name:
        parts.append(name)
    if version:
        parts.append(f"revision {version}")
    if node_type:
        parts.append(f"type {node_type}")
    return " | ".join(parts).strip()


def _text_match_strength(value, term: str) -> float:
    if not term:
        return 0.0
    text = str(value or "").strip().lower()
    wanted = term.strip().lower()
    if not text or not wanted:
        return 0.0
    if text == wanted:
        return 1.0
    if text.startswith(wanted):
        return 0.75
    if wanted in text:
        return 0.45
    return 0.0


def _comparative_rank_boost(node: dict, node_type: str, name: str, version: str) -> float:
    props = node.get("properties") or {}
    labels = [str(label or "").lower() for label in (node.get("labels") or [])]
    boost = 0.0

    if name:
        boost += max(
            _text_match_strength(props.get("name"), name),
            _text_match_strength(props.get("title"), name),
            _text_match_strength(props.get("label"), name),
            _text_match_strength(props.get("code"), name),
            _text_match_strength(props.get("id"), name),
        ) * 0.35

    if node_type:
        label_score = max((_text_match_strength(label, node_type) for label in labels), default=0.0)
        boost += max(
            label_score,
            _text_match_strength(props.get("type"), node_type),
            _text_match_strength(props.get("node_type"), node_type),
            _text_match_strength(props.get("entity_type"), node_type),
        ) * 0.2

    if version:
        boost += max(
            _text_match_strength(props.get("version"), version),
            _text_match_strength(props.get("Version"), version),
            _text_match_strength(props.get("revision"), version),
            _text_match_strength(props.get("external_version"), version),
        ) * 0.15

    return boost


def _comparative_similarity_results(node_type: str, name: str, version: str, limit: int):
    query_text = _comparative_query_text(node_type, name, version)
    if not query_text:
        return []

    try:
        try:
            from .core.llm import embeddings, EMBEDDER_AVAILABLE
        except Exception:
            from core.llm import embeddings, EMBEDDER_AVAILABLE

        if not EMBEDDER_AVAILABLE:
            return []

        vector_index_name = os.getenv("NEO4J_GRAPH_VECTOR_INDEX", "graph_embedding")
        candidate_limit = max(min(limit * 4, 60), limit)
        query_embedding = embeddings.embed_query(query_text)

        rows = graph.query(
            """
            CALL db.index.vector.queryNodes($index_name, $candidate_limit, $embedding)
            YIELD node, score
            MATCH (node)-[:EMBEDDED_FROM]->(src)
            WHERE NOT (src:DatasheetChunk OR src:GraphChunk)
            WITH src, max(score) AS similarity_score
            RETURN
              elementId(src) AS elementId,
              labels(src) AS labels,
              properties(src) AS properties,
              similarity_score
            LIMIT $candidate_limit
            """,
            params={
                "index_name": vector_index_name,
                "candidate_limit": candidate_limit,
                "embedding": query_embedding,
            },
        ) or []
    except Exception as exc:
        logger.info("Comparative similarity search unavailable, falling back to keyword search: %s", exc)
        return []

    ranked = []
    for row in rows:
        properties = dict(row.get("properties") or {})
        raw_similarity = float(row.get("similarity_score") or 0.0)
        node = {
            "elementId": row.get("elementId"),
            "labels": row.get("labels") or [],
            "properties": {
                **properties,
                "similarity_score": round(raw_similarity * 100, 1),
            },
        }
        rank_score = raw_similarity + _comparative_rank_boost(node, node_type, name, version)
        ranked.append((rank_score, node))

    ranked.sort(key=lambda item: item[0], reverse=True)

    deduped = []
    seen = set()
    for _score, node in ranked:
        node_id = node.get("elementId")
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        deduped.append({"n": node, "r": None, "m": None})
        if len(deduped) >= limit:
            break

    return deduped


def _comparative_keyword_results(node_type: str, name: str, version: str, limit: int):
    query = """
        MATCH (n)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
          AND (
            $name = ''
            OR toLower(coalesce(n.name, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.label, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.title, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.FileName, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.id, '')) CONTAINS toLower($name)
          )
          AND (
            $node_type = ''
            OR any(lbl IN labels(n) WHERE toLower(lbl) CONTAINS toLower($node_type))
            OR toLower(coalesce(n.type, '')) CONTAINS toLower($node_type)
            OR toLower(coalesce(n.node_type, '')) CONTAINS toLower($node_type)
            OR toLower(coalesce(n.entity_type, '')) CONTAINS toLower($node_type)
          )
          AND (
            $version = ''
            OR toLower(coalesce(n.version, '')) CONTAINS toLower($version)
            OR toLower(coalesce(n.Version, '')) CONTAINS toLower($version)
            OR toLower(coalesce(n.revision, '')) CONTAINS toLower($version)
            OR toLower(coalesce(n.external_version, '')) CONTAINS toLower($version)
          )
        RETURN
          {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          null AS r,
          null AS m
        LIMIT $limit
    """
    return graph.query(
        query,
        params={"node_type": node_type, "name": name, "version": version, "limit": limit},
    )


@app.post("/comparative-search")
def comparative_search(request: ComparativeSearchRequest):
    """Search nodes for comparison using semantic similarity with keyword fallback."""
    node_type = (request.nodeType or "").strip()
    name = (request.name or "").strip()
    version = (request.version or "").strip()
    limit = max(1, min(int(request.limit or 12), 25))

    if not name and not node_type and not version:
        return {"results": []}

    try:
        results = _comparative_similarity_results(node_type, name, version, limit)
        if not results:
            results = _comparative_keyword_results(node_type, name, version, limit)
        return {"results": results}
    except Exception as e:
        safe_error("/comparative-search", e)


class MultiNameSearchRequest(BaseModel):
    names: list[str] | None = None
    search: str | list[str] | None = None


@app.post("/graphfilter-multi")
def filter_graph_nodes_multi(request: MultiNameSearchRequest):
    """Fetch named/search result nodes and any relationships between them.
    Accepts the legacy {names: [...]} payload and tolerant {search: ...} payloads for external callers."""
    raw_terms: list[str] = []
    if request.names:
        raw_terms.extend(str(name) for name in request.names)
    if isinstance(request.search, list):
        raw_terms.extend(str(name) for name in request.search)
    elif isinstance(request.search, str):
        raw_terms.extend(part.strip() for part in re.split(r"[,;\n]+", request.search) if part.strip())

    # Cap at 50 names to avoid overloading Neo4j
    names = [_normalize_search_term(n) for n in raw_terms if n and str(n).strip()][:50]
    names = [n for n in names if n]
    if not names:
        return {"results": []}

    wildcard_prefix_search = any("*" in str(term or "") for term in raw_terms)
    query = """
UNWIND $names AS searchName
MATCH (n)
WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
  AND (
    toLower(elementId(n)) CONTAINS toLower(searchName)
    OR any(lbl IN labels(n) WHERE toLower(lbl) CONTAINS toLower(searchName))
    OR any(field IN $search_fields WHERE
      CASE
        WHEN $wildcard_prefix_search THEN toLower(toString(coalesce(n[field], ''))) STARTS WITH toLower(searchName)
        ELSE toLower(toString(coalesce(n[field], ''))) CONTAINS toLower(searchName)
      END
    )
  )
WITH collect(DISTINCT n)[..250] AS matchedNodes
UNWIND matchedNodes AS n
OPTIONAL MATCH (n)-[r]-(m)
WHERE m IN matchedNodes
RETURN
  {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
  CASE WHEN r IS NOT NULL THEN {
    elementId: elementId(r), type: type(r), properties: properties(r),
    start: elementId(startNode(r)), end: elementId(endNode(r))
  } ELSE null END AS r,
  CASE WHEN m IS NOT NULL THEN {
    elementId: elementId(m), labels: labels(m), properties: properties(m)
  } ELSE null END AS m
"""
    try:
        results = graph.query(query, params={
            "names": names,
            "search_fields": GRAPH_SEARCH_PROPERTY_KEYS,
            "wildcard_prefix_search": wildcard_prefix_search,
        })
        return {"results": results}
    except Exception as e:
        safe_error("/graphfilter-multi", e)


@app.get("/graphtraverse/{node_id}")
def traverse_node(
    node_id: str = Path(..., description="Neo4j internal node ID"),
    depth: int = 1,
):
    try:
        try:
            from backend.Services.graph_view_service import GraphViewService
        except Exception:
            from Services.graph_view_service import GraphViewService

        return GraphViewService.get_traversal_slice(node_id=node_id, limit=120, depth=depth)
    except Exception as e:
        safe_error("/graphtraverse", e)


@app.get("/ap242/rotor-shaft-pmi")
def get_rotor_shaft_pmi_shape():
    """Return the STEP Rotor Shaft PMI shape instances linked to their AP242
    ontology classes and connected PLMXML data through the ontology bridge.

    The query walks:
      1. STEP Rotor Shaft Individual instances (shape, dimension, tolerance,
         datum, annotation, PMI) -> INSTANCE_OF -> AP242 OntologyClass
      2. Those same AP242 classes <- SUBCLASS_OF chain into core AP242 ontology
      3. PLMXML ontology classes that share the AP242 alignment namespace
      4. PLMXML Individual instances that are INSTANCE_OF PLMXML classes
    """
    query = """
    // ── 1. STEP Rotor Shaft PMI / Shape individuals ──────────────────────
    MATCH (step:Individual)-[r1:INSTANCE_OF]->(cls)
    WHERE step.namespace CONTAINS 'Rotor_Shaft'
      AND (step.name CONTAINS 'SHAPE'
        OR step.name CONTAINS 'DIMENSION'
        OR step.name CONTAINS 'TOLERANCE'
        OR step.name CONTAINS 'DATUM'
        OR step.name CONTAINS 'ANNOTATION'
        OR step.name CONTAINS 'PMI'
        OR step.name CONTAINS 'PRODUCT_DEFINITION'
        OR step.name CONTAINS 'TESSELLATED')

    WITH step, r1, cls

    // ── 2. Optional: climb the class hierarchy via SUBCLASS_OF ───────────
    OPTIONAL MATCH (cls)-[r2:SUBCLASS_OF]->(parent)

    WITH step, r1, cls, r2, parent

    // ── 3. Optional: find PLMXML individuals sharing the same ontology class
    //       or linked through the alignment namespace ──────────────────────
    OPTIONAL MATCH (plm:Individual)-[r3:INSTANCE_OF]->(plmCls)
    WHERE plm.namespace CONTAINS 'plmxml'

    WITH step, r1, cls, r2, parent, plm, r3, plmCls
    LIMIT 500

    // ── 4. Collect all distinct nodes & relationships ─────────────────────
    WITH collect(DISTINCT {
           elementId: elementId(step),
           labels: labels(step),
           properties: properties(step)
         }) AS stepNodes,
         collect(DISTINCT {
           elementId: elementId(cls),
           labels: labels(cls),
           properties: properties(cls)
         }) AS clsNodes,
         collect(DISTINCT CASE WHEN parent IS NOT NULL THEN {
           elementId: elementId(parent),
           labels: labels(parent),
           properties: properties(parent)
         } END) AS parentNodes,
         collect(DISTINCT CASE WHEN plm IS NOT NULL THEN {
           elementId: elementId(plm),
           labels: labels(plm),
           properties: properties(plm)
         } END) AS plmNodes,
         collect(DISTINCT CASE WHEN plmCls IS NOT NULL THEN {
           elementId: elementId(plmCls),
           labels: labels(plmCls),
           properties: properties(plmCls)
         } END) AS plmClsNodes,
         collect(DISTINCT {
           elementId: elementId(r1),
           type: type(r1),
           properties: properties(r1),
           start: elementId(startNode(r1)),
           end: elementId(endNode(r1))
         }) AS r1Links,
         collect(DISTINCT CASE WHEN r2 IS NOT NULL THEN {
           elementId: elementId(r2),
           type: type(r2),
           properties: properties(r2),
           start: elementId(startNode(r2)),
           end: elementId(endNode(r2))
         } END) AS r2Links,
         collect(DISTINCT CASE WHEN r3 IS NOT NULL THEN {
           elementId: elementId(r3),
           type: type(r3),
           properties: properties(r3),
           start: elementId(startNode(r3)),
           end: elementId(endNode(r3))
         } END) AS r3Links

    // Flatten everything into a single results list
    WITH stepNodes + clsNodes +
         [x IN parentNodes WHERE x IS NOT NULL] +
         [x IN plmNodes WHERE x IS NOT NULL] +
         [x IN plmClsNodes WHERE x IS NOT NULL] AS allNodes,
         r1Links +
         [x IN r2Links WHERE x IS NOT NULL] +
         [x IN r3Links WHERE x IS NOT NULL] AS allLinks

    UNWIND allNodes AS n
    WITH DISTINCT n, allLinks
    RETURN n, null AS r, null AS m

    UNION

    // Second part: return links in the n/r/m format the frontend expects
    MATCH (step:Individual)-[r1:INSTANCE_OF]->(cls)
    WHERE step.namespace CONTAINS 'Rotor_Shaft'
      AND (step.name CONTAINS 'SHAPE'
        OR step.name CONTAINS 'DIMENSION'
        OR step.name CONTAINS 'TOLERANCE'
        OR step.name CONTAINS 'DATUM'
        OR step.name CONTAINS 'ANNOTATION'
        OR step.name CONTAINS 'PMI'
        OR step.name CONTAINS 'PRODUCT_DEFINITION'
        OR step.name CONTAINS 'TESSELLATED')
    RETURN
      {elementId: elementId(step), labels: labels(step), properties: properties(step)} AS n,
      {elementId: elementId(r1), type: type(r1), properties: properties(r1),
       start: elementId(startNode(r1)), end: elementId(endNode(r1))} AS r,
      {elementId: elementId(cls), labels: labels(cls), properties: properties(cls)} AS m
    LIMIT 300
    """
    try:
        results = graph.query(query)
        return {"results": results}
    except Exception as e:
        safe_error("/ap242/rotor-shaft-pmi", e)


@app.post("/ap242/search")
def ap242_search(request: TextSearchRequest):
    """Search across the AP242 ontology graph — STEP individuals, ontology
    classes, PLMXML instances — and return a visualisable subgraph of
    matching nodes with their 1-hop relationships."""
    query = """
    WITH toLower($input) AS keyword

    // Find any node whose properties contain the keyword
    MATCH (n)
    WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
    UNWIND keys(n) AS prop
    WITH n, prop, n[prop] AS val, keyword
    WHERE val IS NOT NULL AND toLower(toString(val)) CONTAINS keyword

    WITH DISTINCT n
          LIMIT 50

    // Get 1-hop neighbourhood
    OPTIONAL MATCH (n)-[r]-(m)

    RETURN
      {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
      CASE WHEN r IS NOT NULL THEN
        {elementId: elementId(r), type: type(r), properties: properties(r),
         start: elementId(startNode(r)), end: elementId(endNode(r))}
      ELSE NULL END AS r,
      CASE WHEN m IS NOT NULL THEN
        {elementId: elementId(m), labels: labels(m), properties: properties(m)}
      ELSE NULL END AS m
    LIMIT 500
    """
    try:
        input_val = request.search.strip()
        results = graph.query(query, params={"input": input_val})
        return {"results": results}
    except Exception as e:
        safe_error("/ap242/search", e)


# ── Ontology viewer endpoints ─────────────────────────────────────────────
# NOTE: Specific routes (/ontology/step/parts, /ontology/step/{part_name})
#       MUST come before the generic /ontology/{ontology_type} route.

@app.get("/ontology/step/parts")
def get_step_parts():
    """Return the list of distinct STEP part names available for the secondary filter."""
    query = """
        MATCH (n:Individual)
        WHERE n.namespace CONTAINS 'step-ap242'
        WITH n.namespace AS ns
        WITH DISTINCT ns
        // Extract part name from namespace URL
        // e.g. http://IAE-depo.com/step-ap242/000684_B_1-Rotor_Shaft_Machined# -> 000684_B_1-Rotor_Shaft_Machined
        WITH ns, split(ns, '/') AS parts
        WITH parts[size(parts)-1] AS raw_name
        WITH replace(raw_name, '#', '') AS part_name
        WHERE part_name <> ''
        RETURN DISTINCT part_name
        ORDER BY part_name
    """
    try:
        results = graph.query(query)
        parts = [r["part_name"] for r in results]
        return {"parts": parts}
    except Exception as e:
        safe_error("/ontology/step/parts", e)


@app.get("/ontology/step/{part_name}")
def get_step_part_graph(part_name: str = Path(..., description="Part name filter for STEP ontology")):
    """Return the STEP subgraph filtered to a specific part.
    Returns nodes with relationships if available, otherwise nodes only."""
    # First try to find connected data (relationships)
    rel_query = """
        MATCH (n)-[r]-(m)
        WHERE (n.namespace CONTAINS $part_filter OR m.namespace CONTAINS $part_filter)
        RETURN
          {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          {elementId: elementId(r), type: type(r), properties: properties(r),
           start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
          {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
        LIMIT 500
    """
    # Fallback: return nodes only (for disconnected step-ap242 nodes)
    node_query = """
        MATCH (n)
        WHERE n.namespace CONTAINS $part_filter
        RETURN
          {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          null AS r, null AS m
        LIMIT 300
    """
    try:
        results = graph.query(rel_query, params={"part_filter": part_name.strip()})
        if not results:
            results = graph.query(node_query, params={"part_filter": part_name.strip()})
        return {"results": results}
    except Exception as e:
        safe_error("/ontology/step/{part_name}", e)


@app.get("/ontology/options")
def get_ontology_options():
        """Return registry-driven ontology/data-view dropdown options."""
        options = [{"value": "ALL", "label": "All Ontologies", "source": "system"}]
        try:
                try:
                        from Services.ontology_upload_manager import OntologyUploadManager
                except Exception:
                        from backend.Services.ontology_upload_manager import OntologyUploadManager

                registry = OntologyUploadManager.list_ontologies_with_neo4j_counts(graph)
                for row in registry.get("ontologies", []):
                        prefix = row.get("prefix")
                        if not prefix:
                                continue
                        name = row.get("ontology_name") or row.get("name") or prefix.upper()
                        node_count = int(row.get("node_count") or 0)
                        rel_count = int(row.get("relationship_count") or 0)
                        options.append({
                                "value": prefix,
                                "label": name,
                                "prefix": prefix,
                                "ontology_id": row.get("ontology_id"),
                                "source": row.get("source", "registered"),
                                "status": row.get("availability") or row.get("status"),
                                "node_count": node_count,
                                "relationship_count": rel_count,
                                "disabled": node_count == 0,
                        })

                # Add STEP and MBSE system views only when corresponding data exists.
                step_count_query = """
                MATCH (n)
                WHERE n.namespace CONTAINS 'step-ap242'
                   OR n.source_format = 'step'
                   OR n.file_format = 'step'
                RETURN count(n) AS cnt
                """
                mbse_count_query = """
                MATCH (n)
                WHERE n.source_format = 'xmi' OR n.ontology_id = 'mbse_domain_ontology'
                RETURN count(n) AS cnt
                """
                step_results = OntologyUploadManager._query_configured_neo4j(step_count_query, graph=graph)
                step_count = (step_results[0].get("cnt", 0) if step_results else 0)
                if step_count > 0:
                        options.append({
                                "value": "step",
                                "label": "CAD STEP Instances",
                                "source": "system",
                                "status": "available",
                                "node_count": step_count,
                                "relationship_count": 0,
                        })

                mbse_results = OntologyUploadManager._query_configured_neo4j(mbse_count_query, graph=graph)
                mbse_count = (mbse_results[0].get("cnt", 0) if mbse_results else 0)
                if mbse_count > 0:
                        options.append({
                                "value": "mbse",
                                "label": "MBSE Domain Ontology",
                                "source": "system",
                                "status": "available",
                                "node_count": mbse_count,
                                "relationship_count": 0,
                        })
                        options.append({
                                "value": "mbse_instances",
                                "label": "MBSE Data",
                                "source": "system",
                                "status": "available",
                                "node_count": mbse_count,
                                "relationship_count": 0,
                        })

                return {
                        "options": options,
                        "count": len(options),
                        "step_node_count": step_count,
                        "mbse_node_count": mbse_count,
                }
        except Exception as e:
                safe_error("/ontology/options", e)


@app.get("/ontology/mbse-instances")
def get_mbse_instance_graph():
        """Return MBSE instance-only graph (imported from XMI)."""
        query = """
                MATCH (n)
                WHERE n.source_format = 'xmi'
                    AND NOT n:OntologyMetadata
                OPTIONAL MATCH (n)-[r]-(m)
                WHERE (m.source_format = 'xmi' AND NOT m:OntologyMetadata) OR m IS NULL
                RETURN
                    {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
                    CASE
                        WHEN r IS NOT NULL THEN {
                            elementId: elementId(r), type: type(r), properties: properties(r),
                            start: elementId(startNode(r)), end: elementId(endNode(r))
                        }
                        ELSE NULL
                    END AS r,
                    CASE
                        WHEN m IS NOT NULL THEN {
                            elementId: elementId(m), labels: labels(m), properties: properties(m)
                        }
                        ELSE NULL
                    END AS m
                LIMIT 2000
        """
        try:
                results = graph.query(query)
                return {"results": results}
        except Exception as e:
                safe_error("/ontology/mbse-instances", e)


@app.get("/ontology/{ontology_type}")
async def get_ontology_graph(
    ontology_type: str = Path(..., description="ap242, plmxml, step, or mbse"),
    include_instances: bool = Query(False, alias="includeInstances", description="Include instance-level nodes related to the ontology")
):
    """Return the subgraph for a specific ontology.
    - ap242:  AP242 ontology classes + step-ontology schema + taxonomy
    - plmxml: PLMXML ontology classes + taxonomy
    - step:   STEP file individual nodes (returned as node inventory)
    - mbse:   MBSE domain ontology classes inferred from imported XMI data
    """
    queries = {
        "ap242": """
            MATCH (n:OntologyClass {prefix: 'ap242'})
            OPTIONAL MATCH (n)-[r]->(m:OntologyClass {prefix: 'ap242'})
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              CASE WHEN r IS NOT NULL THEN
                {elementId: elementId(r), type: type(r), properties: properties(r),
                 start: elementId(startNode(r)), end: elementId(endNode(r))}
              ELSE NULL END AS r,
              CASE WHEN m IS NOT NULL THEN
                {elementId: elementId(m), labels: labels(m), properties: properties(m)}
              ELSE NULL END AS m
            LIMIT 500
        """,
        "plmxml": """
            MATCH (n)
            WHERE n.ontology_prefix = 'plmxml'
               OR n.source_ontology CONTAINS 'PLMXMLSchema'
               OR n.source_ontology CONTAINS 'plmxml.org'
            OPTIONAL MATCH (n)-[r]->(m)
            WHERE m.ontology_prefix = 'plmxml'
               OR m.source_ontology CONTAINS 'PLMXMLSchema'
               OR m.source_ontology CONTAINS 'plmxml.org'
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              CASE WHEN r IS NOT NULL THEN
                {elementId: elementId(r), type: type(r), properties: properties(r),
                 start: elementId(startNode(r)), end: elementId(endNode(r))}
              ELSE NULL END AS r,
              CASE WHEN m IS NOT NULL THEN
                {elementId: elementId(m), labels: labels(m), properties: properties(m)}
              ELSE NULL END AS m
            LIMIT 500
        """,
        "step": """
            MATCH (n)
            WHERE n.namespace CONTAINS 'step-ap242'
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              null AS r, null AS m
            LIMIT 300
        """,
                "mbse": """
                        MATCH (a)-[r]->(b)
                        WHERE a.source_format = 'xmi' AND b.source_format = 'xmi'
                        WITH DISTINCT
                            labels(a)[0] AS src_type,
                            type(r) AS rel_type,
                            labels(b)[0] AS tgt_type
                        RETURN
                            {
                                elementId: 'mbse_class_' + src_type,
                                labels: ['OntologyClass'],
                                properties: {
                                    name: src_type,
                                    namespace: 'http://depo.example/mbse/domain#',
                                    source_format: 'xmi',
                                    ontology_id: 'mbse_domain_ontology'
                                }
                            } AS n,
                            {
                                elementId: 'mbse_rel_' + src_type + '_' + rel_type + '_' + tgt_type,
                                type: rel_type,
                                properties: {
                                    ontology_id: 'mbse_domain_ontology'
                                },
                                start: 'mbse_class_' + src_type,
                                end: 'mbse_class_' + tgt_type
                            } AS r,
                            {
                                elementId: 'mbse_class_' + tgt_type,
                                labels: ['OntologyClass'],
                                properties: {
                                    name: tgt_type,
                                    namespace: 'http://depo.example/mbse/domain#',
                                    source_format: 'xmi',
                                    ontology_id: 'mbse_domain_ontology'
                                }
                            } AS m
                        LIMIT 1000
                """,
    }
    key = ontology_type.lower().strip()

    # Helper: fetch instances related to a set of class ids OR matching the prefix
    def _fetch_instances_and_rels(prefix, class_ids=None):
        try:
            inst_nodes = []
            inst_rels = []

            # Instances connected to known classes
            if class_ids:
                # limit class ids to 500 to avoid huge IN lists
                cls_ids = class_ids[:500]
                q = """
                    MATCH (inst)-[r]-(cl)
                    WHERE elementId(cl) IN $class_ids
                      AND NOT ('OntologyClass' IN labels(inst) OR 'Class' IN labels(inst))
                    RETURN {elementId: elementId(inst), labels: labels(inst), properties: properties(inst)} AS n,
                           {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
                           {elementId: elementId(cl), labels: labels(cl), properties: properties(cl)} AS m
                    LIMIT 1000
                """
                inst_rels = graph.query(q, params={"class_ids": cls_ids}) or []

            # Instances that explicitly carry the prefix/id/namespace
            prop_q = """
                MATCH (n)
                WHERE coalesce(n.ontology_prefix, '') = $prefix
                   OR coalesce(n.ontology_id, '') = $prefix
                   OR toLower(coalesce(n.source_ontology, '')) CONTAINS toLower($prefix)
                   OR toLower(coalesce(n.namespace, '')) CONTAINS toLower($prefix)
                RETURN {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
                       null AS r, null AS m
                LIMIT 1000
            """
            inst_nodes = graph.query(prop_q, params={"prefix": prefix}) or []

            # If we have instance nodes, fetch relationships among the combined ids for richer graph
            all_ids = []
            all_ids += [r['n']['elementId'] for r in inst_nodes if r.get('n')]
            all_ids += [r['n']['elementId'] for r in inst_rels if r.get('n')]
            # dedupe and cap
            all_ids = list(dict.fromkeys(all_ids))[:500]

            rels = []
            if all_ids:
                rels_q = """
                    MATCH (a)-[r]-(b)
                    WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                    RETURN {elementId: elementId(a), labels: labels(a), properties: properties(a)} AS n,
                           {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
                           {elementId: elementId(b), labels: labels(b), properties: properties(b)} AS m
                    LIMIT 2000
                """
                rels = graph.query(rels_q, params={"ids": all_ids}) or []

            # Combine instance-only nodes (inst_nodes) and rel rows
            combined = []
            # inst_nodes are rows with n and null r/m; convert to same shape
            combined.extend(inst_nodes)
            combined.extend(inst_rels)
            combined.extend(rels)
            return combined
        except Exception as e:
            logger.error('Instance fetch error: %s', e, exc_info=True)
            return []

    # If we have a known, specialized query, use it first
    if key in queries:
        try:
            results = graph.query(queries[key])
            if include_instances:
                # collect class ids from schema results and fetch instances
                class_ids = [r['n']['elementId'] for r in results if r.get('n')]
                inst_rows = fetch_instances_and_rels(ontology_type, class_ids=class_ids)
                # merge and normalize by elementId for simple response
                combined = (results or []) + (inst_rows or [])
                normalized = normalize_ontology_prefix(combined)
                return {"results": normalized}
            normalized = normalize_ontology_prefix(results)
            return {"results": normalized}
        except Exception as e:
            safe_error("/ontology/{ontology_type}", e)

    # Generic heuristics for arbitrary ontology names / prefixes
    # Attempt multiple, increasingly-broad strategies so customers with
    # different naming conventions still get useful results.
    try:
        # Strategy 1: OntologyClass nodes with matching prefix property (fast, schema-level)
        schema_query = """
            MATCH (n:OntologyClass)
            WHERE coalesce(n.prefix, '') = $prefix
            RETURN {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
                   null AS r, null AS m
            LIMIT 500
        """
        schema_results = graph.query(schema_query, params={"prefix": ontology_type})
        if schema_results:
            if include_instances:
                class_ids = [r['n']['elementId'] for r in schema_results if r.get('n')]
                inst_rows = fetch_instances_and_rels(ontology_type, class_ids=class_ids)
                combined = (schema_results or []) + (inst_rows or [])
                normalized = normalize_ontology_prefix(combined)
                return {"results": normalized}
            normalized = normalize_ontology_prefix(schema_results)
            return {"results": normalized}

        # Strategy 2: Instance/individual nodes where an ontology identifying property matches
        # (common properties: ontology_prefix, ontology_id, source_ontology, namespace)
        instance_query = """
            MATCH (n)
            WHERE coalesce(n.ontology_prefix, '') = $prefix
               OR coalesce(n.ontology_id, '') = $prefix
               OR (coalesce(n.source_ontology, '') CONTAINS $prefix)
               OR (coalesce(n.namespace, '') CONTAINS $prefix)
            RETURN {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
                   null AS r, null AS m
            LIMIT 1000
        """
        instance_results = graph.query(instance_query, params={"prefix": ontology_type})
        if instance_results:
            if include_instances:
                # instance_results already contains instance rows; enrich with rels via helper
                inst_rows = fetch_instances_and_rels(ontology_type, class_ids=None)
                combined = (instance_results or []) + (inst_rows or [])
                normalized = normalize_ontology_prefix(combined)
                return {"results": normalized}
            # Try to also return any relationships between those nodes for richer graphs
            node_ids = [r['n']['elementId'] for r in instance_results if r.get('n')]
            if node_ids:
                # Build rels between matched nodes (bounded by list size)
                rels_query = """
                    MATCH (a)-[r]-(b)
                    WHERE elementId(a) IN $ids AND elementId(b) IN $ids
                    RETURN {elementId: elementId(a), labels: labels(a), properties: properties(a)} AS n,
                           {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
                           {elementId: elementId(b), labels: labels(b), properties: properties(b)} AS m
                    LIMIT 2000
                """
                rels = graph.query(rels_query, params={"ids": node_ids})
                if rels:
                    normalized = normalize_ontology_prefix(rels)
                    return {"results": normalized}
            normalized = normalize_ontology_prefix(instance_results)
            return {"results": normalized}

        # Strategy 3: Full-text-ish fallback — search common identifying fields for substring match
        fuzzy_query = """
            MATCH (n)-[r]-(m)
            WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($prefix)
               OR toLower(coalesce(n.label, '')) CONTAINS toLower($prefix)
               OR toLower(coalesce(n.original_type, '')) CONTAINS toLower($prefix)
               OR toLower(coalesce(n.source_ontology, '')) CONTAINS toLower($prefix)
            RETURN {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
                   CASE WHEN r IS NOT NULL THEN {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} ELSE NULL END AS r,
                   CASE WHEN m IS NOT NULL THEN {elementId: elementId(m), labels: labels(m), properties: properties(m)} ELSE NULL END AS m
            LIMIT 1000
        """
        fuzzy_results = graph.query(fuzzy_query, params={"prefix": ontology_type})
        if fuzzy_results:
            normalized = normalize_ontology_prefix(fuzzy_results)
            return {"results": normalized}

        # Nothing found — return empty results so frontend can fall back to initial data
        return {"results": []}
    except Exception as e:
        safe_error("/ontology/{ontology_type}", e)


@app.get("/ontology/{ontology_type}/instances")
async def get_ontology_instances(
    ontology_type: str = Path(..., description="ontology prefix or type"),
    limit: int = Query(1000, description="Max rows to return"),
    include_rels: bool = Query(True, description="Whether to include relationships among matched instances")
):
    """Return instance-level nodes related to the given ontology prefix.
    This endpoint focuses on instance discovery and relationship enrichment, separate from schema responses.
    """
    try:
        # collect class ids for the prefix (if any) to broaden instance matching
        class_q = """
            MATCH (c:OntologyClass)
            WHERE coalesce(c.prefix, '') = $prefix
            RETURN {elementId: elementId(c), labels: labels(c), properties: properties(c)} AS n
            LIMIT 500
        """
        classes = graph.query(class_q, params={"prefix": ontology_type}) or []
        class_ids = [r['n']['elementId'] for r in classes if r.get('n')]

        # Run the potentially expensive instance fetch in a thread to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, lambda: fetch_instances_and_rels(ontology_type, class_ids=class_ids))

        # Optionally filter out relationships if include_rels is False (keep only node rows)
        if not include_rels:
            nodes_only = [r for r in rows if r.get('n') and not r.get('r')]
            rows = nodes_only

        # apply limit
        if isinstance(limit, int) and limit > 0:
            rows = rows[:limit]

        return {"results": rows}
    except Exception as e:
        safe_error("/ontology/{ontology_type}/instances", e)


@app.post("/embeddings/build")
def build_graph_embeddings(force: bool = False):
    """Trigger the context-aware graph embedding pipeline.
    Pass ?force=true to rebuild all chunks even if they already exist."""
    from Services.graph_embeddings import run_graph_embeddings
    try:
        run_graph_embeddings(force_rebuild=force)
        return {"status": "ok", "message": "Graph embeddings built successfully"}
    except Exception as e:
        safe_error("/embeddings/build", e)



@app.post("/reports")
@app.post("/api/v1/reports")
def get_reports(body: dict):
    """Compatibility report endpoint for customer deployments and external clients."""
    try:
        report_type = str((body or {}).get("type") or (body or {}).get("report_type") or "overview").strip().lower()
        page = max(1, int((body or {}).get("page") or 1))
        page_size = max(1, min(int((body or {}).get("page_size") or (body or {}).get("pageSize") or 25), 500))
        include_documents = bool((body or {}).get("include_documents") or (body or {}).get("includeDocuments"))
        skip = (page - 1) * page_size

        if report_type in {"ontology", "ontologies", "governance"}:
            try:
                from Services.ontology_upload_manager import OntologyUploadManager
            except Exception:
                from backend.Services.ontology_upload_manager import OntologyUploadManager
            registry = OntologyUploadManager.list_ontologies_with_neo4j_counts(graph)
            rows = registry.get("ontologies", []) if isinstance(registry, dict) else []
            return {
                "status": "success",
                "type": report_type,
                "page": page,
                "page_size": page_size,
                "total": len(rows),
                "results": rows[skip:skip + page_size],
            }

        if report_type in {"relationship", "relationships", "traceability", "lineage"}:
            rows = graph.query(
                """
                MATCH (a)-[r]->(b)
                WITH a, r, b,
                     coalesce(a.name, a.label, a.id, '') AS from_name,
                     coalesce(b.name, b.label, b.id, '') AS to_name
                WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk)
                  AND from_name <> '' AND to_name <> ''
                  AND NOT toLower(from_name) STARTS WITH 'id'
                  AND NOT toLower(to_name) STARTS WITH 'id'
                  AND ($include_documents OR coalesce(a.element_type, '') <> 'Document')
                  AND ($include_documents OR coalesce(b.element_type, '') <> 'Document')
                  AND ($include_documents OR coalesce(a.document_type, '') <> 'DataSet')
                  AND ($include_documents OR coalesce(b.document_type, '') <> 'DataSet')
                  AND NOT any(lbl IN labels(a) WHERE lbl IN ['GeneralRelation', 'RelationshipCarrier', 'AttributeContext', 'MetadataWrapper'])
                  AND NOT any(lbl IN labels(b) WHERE lbl IN ['GeneralRelation', 'RelationshipCarrier', 'AttributeContext', 'MetadataWrapper'])
                RETURN type(r) AS relationship_type,
                       from_name AS from_name,
                       labels(a) AS from_labels,
                       to_name AS to_name,
                       labels(b) AS to_labels,
                       properties(r) AS relationship_properties
                ORDER BY relationship_type, from_name, to_name
                SKIP $skip LIMIT $limit
                """,
                params={"skip": skip, "limit": page_size, "include_documents": include_documents},
            ) or []
            total_rows = graph.query(
                """
                MATCH (a)-[r]->(b)
                WITH a, r, b,
                     coalesce(a.name, a.label, a.id, '') AS from_name,
                     coalesce(b.name, b.label, b.id, '') AS to_name
                WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk)
                  AND from_name <> '' AND to_name <> ''
                  AND NOT toLower(from_name) STARTS WITH 'id'
                  AND NOT toLower(to_name) STARTS WITH 'id'
                  AND NOT any(lbl IN labels(a) WHERE lbl IN ['GeneralRelation', 'RelationshipCarrier', 'AttributeContext', 'MetadataWrapper'])
                  AND NOT any(lbl IN labels(b) WHERE lbl IN ['GeneralRelation', 'RelationshipCarrier', 'AttributeContext', 'MetadataWrapper'])
                RETURN count(r) AS total
                """
            , params={"include_documents": include_documents}) or []
            total = int(total_rows[0].get("total") or 0) if total_rows else len(rows)
            return {"status": "success", "type": report_type, "page": page, "page_size": page_size, "total": total, "results": rows}

        rows = graph.query(
            """
            MATCH (n)
            WITH n, coalesce(n.name, n.label, n.id, '') AS display_name
            WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
              AND display_name <> ''
              AND NOT toLower(display_name) STARTS WITH 'id'
              AND ($include_documents OR coalesce(n.element_type, '') <> 'Document')
              AND ($include_documents OR coalesce(n.document_type, '') <> 'DataSet')
              AND NOT any(lbl IN labels(n) WHERE lbl IN ['GeneralRelation', 'RelationshipCarrier', 'AttributeContext', 'MetadataWrapper'])
            RETURN elementId(n) AS elementId,
                   labels(n) AS labels,
                   properties(n) AS properties
            ORDER BY display_name
            SKIP $skip LIMIT $limit
            """,
            params={"skip": skip, "limit": page_size, "include_documents": include_documents},
        ) or []
        total_rows = graph.query(
            """
            MATCH (n)
            WITH n, coalesce(n.name, n.label, n.id, '') AS display_name
            WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
              AND display_name <> ''
              AND NOT toLower(display_name) STARTS WITH 'id'
              AND ($include_documents OR coalesce(n.element_type, '') <> 'Document')
              AND ($include_documents OR coalesce(n.document_type, '') <> 'DataSet')
              AND NOT any(lbl IN labels(n) WHERE lbl IN ['GeneralRelation', 'RelationshipCarrier', 'AttributeContext', 'MetadataWrapper'])
            RETURN count(n) AS total
            """,
            params={"include_documents": include_documents},
        ) or []
        total = int(total_rows[0].get("total") or 0) if total_rows else len(rows)
        normalized = []
        for row in rows:
            props = dict(row.get("properties") or {})
            normalized.append({
                "elementId": row.get("elementId"),
                "type": ", ".join(row.get("labels") or []),
                **props,
                "name": props.get("name") or props.get("label") or props.get("id") or row.get("elementId"),
            })
        return {"status": "success", "type": report_type, "page": page, "page_size": page_size, "total": total, "results": normalized}
    except Exception as e:
        safe_error("/reports", e)


@app.get("/api/v1/reports/xsd-relational")
def get_xsd_relational_report(ontology_id: str = Query(..., min_length=1, max_length=200)):
    """Return a read-only relational projection of a registered XSD."""
    try:
        try:
            from Services.ontology_upload_manager import OntologyUploadManager
            from Services.xsd_relational_report import build_xsd_relational_report
        except ImportError:
            from backend.Services.ontology_upload_manager import OntologyUploadManager
            from backend.Services.xsd_relational_report import build_xsd_relational_report
        result = OntologyUploadManager.get_ontology(ontology_id)
        if result.get("status") != "success":
            raise HTTPException(status_code=404, detail=result.get("error") or "Ontology not found")
        metadata = result.get("metadata") or {}
        file_path = _Path(metadata.get("file_path") or "")
        if file_path.suffix.lower() != ".xsd" or not file_path.exists():
            raise HTTPException(status_code=422, detail="The selected ontology does not have an accessible XSD source file")
        return {"ontology_id": ontology_id, "prefix": metadata.get("prefix") or "", **build_xsd_relational_report(file_path)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"XSD relational report could not be generated: {exc}")

# ======================== RECOMMENDATION ENDPOINTS ========================

try:
    from .Services.change_impact_recommender import ChangeImpactRecommender
    from .Services.similar_parts_recommender import SimilarPartsRecommender
    from .Services.manufacturing_process_recommender import ManufacturingProcessRecommender
except ImportError:
    from Services.change_impact_recommender import ChangeImpactRecommender
    from Services.similar_parts_recommender import SimilarPartsRecommender
    from Services.manufacturing_process_recommender import ManufacturingProcessRecommender

_change_impact = ChangeImpactRecommender(graph)
_similar_parts = SimilarPartsRecommender(graph)
_mfg_process = ManufacturingProcessRecommender(graph)


@app.post("/recommendations/change-impact")
def recommend_change_impact(body: dict):
    """Analyse change impact given a change entity name or a part name."""
    change_name = body.get("change_name", "")
    part_name = body.get("part_name", "")
    scope = body.get("scope") or {}
    node_id = body.get("node_id") or body.get("element_id") or scope.get("node_id") or scope.get("element_id") or ""
    if node_id and isinstance(scope, dict):
        scope = {**scope, "node_id": node_id}
    if not change_name and not part_name:
        raise HTTPException(status_code=400, detail="Provide 'change_name' or 'part_name'")
    try:
        return _change_impact.analyse(change_name=change_name, part_name=part_name, scope=scope)
    except Exception as e:
        safe_error("/recommendations/change-impact", e)


@app.post("/recommendations/similar-parts")
def recommend_similar_parts(body: dict):
    """Find similar parts given a part name."""
    part_name = body.get("part_name", "")
    top_n = body.get("top_n", 10)
    scope = body.get("scope") or {}
    node_id = body.get("node_id") or body.get("element_id") or scope.get("node_id") or scope.get("element_id") or ""
    if node_id and isinstance(scope, dict):
        scope = {**scope, "node_id": node_id}
    if not part_name:
        raise HTTPException(status_code=400, detail="Provide 'part_name'")
    try:
        return _similar_parts.recommend(part_name, top_n=int(top_n), scope=scope, node_id=node_id)
    except Exception as e:
        safe_error("/recommendations/similar-parts", e)


@app.post("/recommendations/manufacturing")
def recommend_manufacturing(body: dict):
    """Recommend manufacturing processes for a part."""
    part_name = body.get("part_name", "")
    scope = body.get("scope") or {}
    node_id = body.get("node_id") or body.get("element_id") or scope.get("node_id") or scope.get("element_id") or ""
    if node_id and isinstance(scope, dict):
        scope = {**scope, "node_id": node_id}
    if not part_name:
        raise HTTPException(status_code=400, detail="Provide 'part_name'")
    try:
        return _mfg_process.recommend(part_name, scope=scope, node_id=node_id)
    except Exception as e:
        safe_error("/recommendations/manufacturing", e)


@app.get("/recommendations/health")
def recommendations_health():
    """Service health check with key Neo4j counts."""
    try:
        from Services.ontology_upload_manager import OntologyUploadManager
        try:
            registered = OntologyUploadManager.list_ontologies_with_neo4j_counts(graph)
        except Exception:
            registered = OntologyUploadManager.list_ontologies()

        counts = graph.query("""
            MATCH (p:Individual)-[:INSTANCE_OF]->(c:OntologyClass)
            WHERE c.name IS NOT NULL
            RETURN c.name AS class_name, count(p) AS cnt
            ORDER BY cnt DESC
            LIMIT 20
        """)
        model_counts = graph.query("""
            OPTIONAL MATCH (i:Individual)
            WITH count(i) AS individual_count
            OPTIONAL MATCH (raw)
            WHERE NOT raw:OntologyClass
              AND NOT raw:ObjectProperty
              AND NOT raw:DatatypeProperty
            WITH individual_count, count(raw) AS raw_graph_count
            OPTIONAL MATCH (biz)
            WHERE NOT biz:OntologyClass
              AND NOT biz:ObjectProperty
              AND NOT biz:DatatypeProperty
              AND coalesce(biz.name, biz.title, biz.code, biz.part_number, biz.requirement_id, '') <> ''
              AND NOT toLower(coalesce(biz.name, '')) STARTS WITH 'id'
            WITH individual_count, raw_graph_count, count(biz) AS business_object_count
            OPTIONAL MATCH (proc)
            WHERE NOT proc:OntologyClass
              AND NOT proc:ObjectProperty
              AND NOT proc:DatatypeProperty
              AND NOT proc:GeneralRelation
              AND NOT proc:ProductInstance
              AND NOT proc:ProductView
              AND NOT proc:UserData
              AND NOT proc:Transform
              AND NOT proc:AttributeContext
              AND coalesce(proc.name, proc.title, proc.code, '') <> ''
              AND NOT toLower(coalesce(proc.name, '')) STARTS WITH 'id'
              AND (
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'process' OR
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'operation' OR
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'activity' OR
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'service' OR
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'validate' OR
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'monitor' OR
                toLower(coalesce(proc.name, proc.title, proc.code, '')) CONTAINS 'prepare'
              )
            RETURN individual_count,
                   raw_graph_count,
                   business_object_count,
                   count(proc) AS process_context_count
        """)
        model_count_row = model_counts[0] if model_counts else {}
        individual_count = int(model_count_row.get("individual_count") or 0)
        raw_graph_count = int(model_count_row.get("raw_graph_count") or 0)
        business_object_count = int(model_count_row.get("business_object_count") or 0)
        process_context_count = int(model_count_row.get("process_context_count") or 0)
        has_business_graph = individual_count > 0 or business_object_count > 0
        service_readiness = {
            "change-impact": {
                "ready": has_business_graph,
                "message": "Change impact can traverse the current business graph." if has_business_graph else "Load business objects or normalized instances first.",
            },
            "similar-parts": {
                "ready": has_business_graph,
                "message": "Similar-part recommendations can compare the current business graph." if has_business_graph else "Load business objects or normalized instances first.",
            },
            "manufacturing": {
                "ready": has_business_graph and process_context_count > 0,
                "message": (
                    "Manufacturing guidance can use process-like business context from the current graph."
                    if has_business_graph and process_context_count > 0
                    else "Manufacturing guidance needs process-like business objects or operational traceability in the loaded graph."
                ),
            },
        }
        return {
            "status": "ok",
            "services": ["change-impact", "similar-parts", "manufacturing"],
            "neo4j_counts": {r["class_name"]: r["cnt"] for r in counts},
            "readiness": {
                "scenario_ready": has_business_graph,
                "individual_count": individual_count,
                "raw_graph_count": raw_graph_count,
                "business_object_count": business_object_count,
                "process_context_count": process_context_count,
                "service_readiness": service_readiness,
                "required_model": "Individual nodes linked to OntologyClass with business names",
                "message": (
                    "Recommendation scenarios are ready on normalized instances."
                    if individual_count > 0
                    else (
                        "Recommendation scenarios can run on current business objects, but the graph is not fully normalized into ontology-linked instances yet."
                        if business_object_count > 0
                        else "Recommendation scenarios need normalized instance data before they can return business results."
                    )
                ),
            },
            "ontology_scopes": (registered.get("ontologies", []) if isinstance(registered, dict) else []),
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


# ======================== ONTOLOGY MAPPER ENDPOINTS ========================

try:
    from .Services.ontology_mapper_service import OntologyMapperService
except ImportError:
    from Services.ontology_mapper_service import OntologyMapperService

LEGACY_ONTOLOGY_MAPPER_NOTICE = {
    "deprecated": True,
    "mode": "legacy_seed_profile",
    "replacement_workflow": "instance.link",
    "replacement_endpoint": "/api/v1/workflows/execute",
    "message": "Legacy seed profiles are compatibility templates. Use Semantic Bridge instance.link for instance-to-ontology alignment.",
}


@app.get("/ontology-mapper/options")
def get_mapping_options():
    """Get available ontology mapping options."""
    try:
        return {
            **LEGACY_ONTOLOGY_MAPPER_NOTICE,
            "options": OntologyMapperService.get_mapping_options(),
            "mapping_types": OntologyMapperService.MAPPING_TYPES,
        }
    except Exception as e:
        safe_error("/ontology-mapper/options", e)


@app.get("/ontology-mapper/{mapping_type}/mappings")
def get_ontology_mappings(mapping_type: str = Path(..., description="plmxml, step, or windchill")):
    """Get all entity mappings for a specific mapping type (e.g., PLMXML→AP242)."""
    try:
        mappings = OntologyMapperService.get_mappings(mapping_type)
        if not mappings:
            raise HTTPException(status_code=404, detail=f"No mappings found for type: {mapping_type}")
        return {
            **LEGACY_ONTOLOGY_MAPPER_NOTICE,
            "mapping_type": mapping_type,
            "total": len(mappings),
            "mappings": mappings,
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/ontology-mapper/{mapping_type}/mappings", e)


@app.get("/ontology-mapper/{mapping_type}/data-dictionary")
def get_data_dictionary(mapping_type: str = Path(..., description="plmxml, step, or windchill")):
    """Get the data dictionary (terms and definitions) for a mapping type."""
    try:
        terms = OntologyMapperService.get_data_dictionary(mapping_type)
        if not terms:
            raise HTTPException(status_code=404, detail=f"No data dictionary found for type: {mapping_type}")
        return {
            **LEGACY_ONTOLOGY_MAPPER_NOTICE,
            "mapping_type": mapping_type,
            "total_terms": len(terms),
            "terms": terms,
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/ontology-mapper/{mapping_type}/data-dictionary", e)


@app.get("/ontology-mapper/{mapping_type}/vocabulary")
def get_vocabulary_mappings(mapping_type: str = Path(..., description="plmxml, step, or windchill")):
    """Get vocabulary mappings (relationship types) for a mapping type."""
    try:
        vocabulary = OntologyMapperService.generate_vocabulary_mappings(mapping_type)
        if not vocabulary:
            raise HTTPException(status_code=404, detail=f"No vocabulary found for type: {mapping_type}")
        return {
            **LEGACY_ONTOLOGY_MAPPER_NOTICE,
            "mapping_type": mapping_type,
            "total_mappings": len(vocabulary),
            "mappings": vocabulary,
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/ontology-mapper/{mapping_type}/vocabulary", e)


@app.get("/ontology-mapper/{mapping_type}/stats")
def get_mapping_stats(mapping_type: str = Path(..., description="plmxml, step, or windchill")):
    """Get statistics about a mapping type."""
    try:
        stats = OntologyMapperService.get_mapping_stats(mapping_type)
        return {**LEGACY_ONTOLOGY_MAPPER_NOTICE, **stats}
    except Exception as e:
        safe_error("/ontology-mapper/{mapping_type}/stats", e)


@app.get("/graph-metrics")
def get_graph_metrics():
    """Return enterprise dashboard metrics: volume and ontology KPIs."""
    try:
        total_nodes = graph.query("MATCH (n) WHERE NOT (n:DatasheetChunk OR n:GraphChunk) RETURN count(n) AS c")[0]["c"]
        total_rels = graph.query(
            "MATCH (a)-[r]->(b) "
            "WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk) "
            "RETURN count(r) AS c"
        )[0]["c"]

        label_rows = graph.query(
            "MATCH (n) WHERE NOT (n:DatasheetChunk OR n:GraphChunk) "
            "UNWIND labels(n) AS lbl RETURN lbl, count(*) AS cnt ORDER BY cnt DESC LIMIT 30"
        )
        rel_rows = graph.query(
            "MATCH (a)-[r]->(b) "
            "WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk) "
            "RETURN type(r) AS rel_type, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"
        )

        # Ontology-level counts via OntologyMetadata source_tag grouping
        ont_rows = graph.query(
            "MATCH (n) WHERE n.source_tag IS NOT NULL AND NOT (n:DatasheetChunk OR n:GraphChunk) "
            "RETURN n.source_tag AS ontology, count(n) AS node_count"
        )

        ontology_kpis_row = graph.query(
            """
            MATCH (n)
            WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
            RETURN
              sum(CASE WHEN n:OntologyClass OR n:Class THEN 1 ELSE 0 END) AS classes,
              sum(CASE WHEN n:ObjectProperty THEN 1 ELSE 0 END) AS object_properties,
              sum(CASE WHEN n:DatatypeProperty THEN 1 ELSE 0 END) AS datatype_properties,
              sum(CASE WHEN n:Restriction THEN 1 ELSE 0 END) AS restrictions,
              sum(CASE WHEN n:ResourceShape THEN 1 ELSE 0 END) AS shacl_shapes,
              sum(CASE WHEN n:Entity OR n:Individual THEN 1 ELSE 0 END) AS individuals
            """
        )
        ontology_kpis = ontology_kpis_row[0] if ontology_kpis_row else {
            "classes": 0,
            "object_properties": 0,
            "datatype_properties": 0,
            "restrictions": 0,
            "shacl_shapes": 0,
            "individuals": 0,
        }

        # Proxy for ontology richness akin to Protege dashboard-style summaries.
        ontology_kpis["axiom_proxy_count"] = int(total_rels)
        ontology_kpis["class_to_property_ratio"] = round(
            (int(ontology_kpis.get("classes") or 0) / max(1, int(ontology_kpis.get("object_properties") or 0) + int(ontology_kpis.get("datatype_properties") or 0))),
            3,
        )

        return {
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "node_labels": [{"label": r["lbl"], "count": r["cnt"]} for r in label_rows],
            "relationship_types": [{"type": r["rel_type"], "count": r["cnt"]} for r in rel_rows],
            "ontology_breakdown": [{"ontology": r["ontology"], "node_count": r["node_count"]} for r in ont_rows],
            "ontology_kpis": ontology_kpis,
        }
    except Exception as e:
        logger.warning("graph-metrics error: %s", e)
        return JSONResponse(status_code=503, content={
            "status": "error",
            "error_code": "GRAPH_METRICS_UNAVAILABLE",
            "detail": "Graph metrics are temporarily unavailable.",
            "total_nodes": 0,
            "total_relationships": 0,
            "node_labels": [],
            "relationship_types": [],
            "ontology_breakdown": [],
            "ontology_kpis": {},
        })


@app.get("/ontologies/available")
def get_available_ontologies():
    """Get available ontologies from Neo4j and registered upload storage."""
    try:
        try:
            from Services.ontology_upload_manager import OntologyUploadManager
        except Exception:
            from backend.Services.ontology_upload_manager import OntologyUploadManager

        registry = OntologyUploadManager.list_ontologies_with_neo4j_counts(graph)
        ontologies = []
        for row in registry.get("ontologies", []):
            ontologies.append({
                'id': row.get('ontology_id') or row.get('prefix'),
                'name': row.get('ontology_name') or row.get('name') or row.get('prefix'),
                'type': row.get('generation_type') or row.get('file_type') or 'ontology',
                'fileType': row.get('file_type'),
                'viewMode': None,
                'ttlFile': row.get('owl_file_path') or row.get('stored_filename') or row.get('original_filename'),
                'usageCount': 0,
                'lastUsed': row.get('uploaded_at'),
                'source': row.get('source') or 'registered',
                'prefix': row.get('prefix'),
                'status': row.get('availability') or row.get('status'),
                'node_count': row.get('node_count', 0),
                'relationship_count': row.get('relationship_count', 0),
                'ontology_id': row.get('ontology_id') or row.get('prefix'),
            })

        return {
            'ontologies': ontologies,
            'count': len(ontologies),
            'dynamicCount': len([o for o in ontologies if o.get('source') == 'neo4j']),
            'registeredCount': len([o for o in ontologies if o.get('source') == 'registered']),
        }
    except Exception as e:
        logger.warning(f"/ontologies/available fallback after error: {type(e).__name__}: {e}", exc_info=True)
        return {
            'ontologies': [],
            'count': 0,
            'dynamicCount': 0,
            'registeredCount': 0,
            'error': str(e),
        }


# ======================== DATA IMPORT PIPELINE ENDPOINTS ========================

from fastapi import UploadFile, File, Form
from pathlib import Path as _Path
try:
    from .Services.data_import_service import DataImportService
    from .Services.ollama_service import get_ollama_service
except ImportError:
    from Services.data_import_service import DataImportService
    from Services.ollama_service import get_ollama_service

# Directory containing ontology .ttl files served by the frontend
ONTOLOGY_DIR = _Path(__file__).resolve().parent.parent / "frontend" / "public" / "Ontology"
MAX_IMPORT_UPLOAD_BYTES = int(os.getenv("MAX_IMPORT_UPLOAD_BYTES", str(500 * 1024 * 1024)))


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload incrementally and reject it before unbounded buffering."""
    if max_bytes <= 0:
        raise RuntimeError("MAX_IMPORT_UPLOAD_BYTES must be positive")
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds the configured size limit")
        chunks.append(chunk)
    return b"".join(chunks)


class OllamaQueryRequest(BaseModel):
    query: str

# Known filename-to-ID mappings for consistent resolution
_KNOWN_ONTOLOGY_IDS = {
    'plmxml_ap242_product_alignment.ttl': ('plmxml_ap242', 'PLMXML \u2192 AP242 Product Alignment'),
    'step_to_ap242_mapping.ttl': ('step_ap242', 'STEP \u2192 AP242 Mapping'),
    'step_ap242_mbd3d_alignment.ttl': ('step_ap242_mbd3d', 'STEP \u2192 AP242-MBD3D Alignment'),
    'windchill_ap242_product_alignment.ttl': ('windchill_ap242', 'Windchill \u2192 AP242 Product Alignment'),
}

_STATIC_ONTOLOGY_MAPPINGS = [
    {
        "id": "plmxml_ap242",
        "name": "PLMXML \u2192 AP242 Product Alignment",
        "file": "plmxml_ap242_product_alignment.ttl",
        "applies_to": ["plmxml", "xml"],
        "required_for": [],
    },
    {
        "id": "step_ap242_mbd3d",
        "name": "STEP \u2192 AP242-MBD3D Alignment",
        "file": "step_ap242_mbd3d_alignment.ttl",
        "applies_to": ["step"],
        "required_for": ["step"],
    },
    {
        "id": "step_ap242",
        "name": "STEP \u2192 AP242 Mapping (legacy)",
        "file": "step_to_ap242_mapping.ttl",
        "applies_to": ["step"],
        "required_for": [],
    },
    {
        "id": "windchill_ap242",
        "name": "Windchill \u2192 AP242 Product Alignment",
        "file": "windchill_ap242_product_alignment.ttl",
        "applies_to": ["json", "xml", "csv", "excel"],
        "required_for": [],
    },
]


@app.get("/ontology-mappings")
async def get_ontology_mappings(file_type: str = ""):
    """List ontology mapping options sourced only from Neo4j OntologyMetadata."""
    normalized_file_type = (file_type or "").strip().lower()

    # Neo4j is the source of truth for dashboard/dropdown state.
    try:
        from core.graph import graph

        cypher = """
        MATCH (om:OntologyMetadata)
        RETURN om.id AS id,
               om.name AS name,
               om.type AS type,
               om.ttl_file AS ttl_file,
               om.generation_type AS generation_type
        ORDER BY om.usage_count DESC, om.last_used DESC
        """
        rows = await asyncio.to_thread(graph.query, cypher)
        rows = rows or []
    except Exception as e:
        logger.warning(f"/ontology-mappings Neo4j query failed: {e}")
        rows = []

    applies_by_type = {
        "plmxml": ["plmxml", "xml"],
        "step": ["step"],
        "xmi": ["xmi", "xml"],
        "xsd": ["xsd", "xml"],
        "json": ["json"],
        "xml": ["xml"],
        "csv": ["csv"],
        "excel": ["excel"],
        "owl": ["ontology", "owl", "rdf", "xml"],
        "rdf": ["ontology", "rdf", "xml"],
        "ttl": ["ontology", "ttl", "rdf", "xml"],
    }

    mappings = []
    for row in rows:
        ont_id = (row.get("id") or "").strip()
        if not ont_id:
            continue

        ont_type = (row.get("type") or "").strip().lower()
        mappings.append({
            "id": ont_id,
            "name": row.get("name") or ont_id,
            "file": row.get("ttl_file") or "",
            "applies_to": applies_by_type.get(
                ont_type,
                ["csv", "excel", "json", "xml", "plmxml", "step", "xmi", "xsd", "ontology"],
            ),
            "required_for": [],
        })

    mappings = sorted(mappings, key=lambda x: x.get("name", ""))

    filtered = mappings
    if normalized_file_type:
        filtered = [
            m for m in mappings
            if normalized_file_type in m.get('applies_to', [])
        ]

    required = [
        m['id'] for m in filtered
        if normalized_file_type and normalized_file_type in m.get('required_for', [])
    ]

    return {
        "mappings": filtered,
        "file_type": normalized_file_type or None,
        "required_mappings": required,
    }


@app.post("/api/v1/import/upload")
@app.post("/api/import/upload")
@app.post("/data-import/upload")
async def upload_file(
    file: UploadFile = File(...),
    ontology_id: str = Form(""),
    ontology_mapping: str = Form(""),
    metadata_exclusion_tags: str = Form(""),
):
    """Upload a file to the import pipeline with selected ontology.
    
    Parameters:
    - file: Data file (CSV, XLS, JSON, etc.)
    - ontology_id: ID of registered ontology (optional, overrides ontology_mapping)
    - ontology_mapping: Legacy ontology name/prefix (used if ontology_id not provided)
    - metadata_exclusion_tags: Optional comma-separated PLMXML tags to suppress as metadata-only nodes
    
    Returns IMMEDIATELY with task_id (within 5 seconds) and processes file in background.
    Use /data-import/status/{task_id} to check processing progress.
    """
    try:
        # Read filename and content
        filename = file.filename or "unknown"
        content = await _read_upload_with_limit(file, MAX_IMPORT_UPLOAD_BYTES)
        if not content:
            raise HTTPException(status_code=400, detail="File is empty")

        # Prefer the unified import service which persists task snapshots so status
        # and commit operations work across workers/processes.
        from backend.Services.unified_data_import import FileFormatDetector, UnifiedDataImportService
        from backend.Services.ontology_upload_manager import OntologyUploadManager

        # Resolve ontology prefix from ontology_id (if provided)
        resolved_ontology_mapping = ontology_mapping
        parse_options = {}
        if metadata_exclusion_tags.strip():
            parse_options["metadata_exclusion_tags"] = [
                tag.strip() for tag in metadata_exclusion_tags.split(",") if tag.strip()
            ]
        if ontology_id:
            try:
                OntologyUploadManager.initialize()
                meta = OntologyUploadManager.load_metadata(ontology_id)
                if meta and meta.get('prefix'):
                    resolved_ontology_mapping = meta['prefix']
            except Exception as e:
                logger.warning(f"Could not resolve ontology_id '{ontology_id}': {e}. Using ontology_mapping instead.")
        
        # Start import via unified service (schedules parsing in background and persists snapshot)
        task_id = await UnifiedDataImportService.start_import(
            content,
            filename,
            resolved_ontology_mapping,
            parse_options=parse_options,
        )

        return {
            "task_id": task_id,
            "filename": filename,
            "file_type": FileFormatDetector.detect(filename).value,
            "ontology_id": ontology_id,
            "ontology_mapping": resolved_ontology_mapping,
            "metadata_exclusion_tags": parse_options.get("metadata_exclusion_tags", []),
            "message": f"File '{filename}' uploaded. Processing started in background. Check status with task_id: {task_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload endpoint error: {e}", exc_info=True)
        safe_error("/data-import/upload", e)


@app.get("/api/v1/import/status/{task_id}")
@app.get("/api/import/status/{task_id}")
@app.get("/data-import/status/{task_id}")
def get_import_status(task_id: str):
    """Get the status of an import task."""
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService
        from backend.Services.data_import_service import import_tasks

        # Prefer the unified service status (reads persisted snapshots and avoids
        # in-memory disparities between modules). If not available, fall back to
        # the legacy DataImportService store and attempt disk restore there.
        unified_status = UnifiedDataImportService.get_status(task_id)
        if unified_status:
            return unified_status

        # Fallback: try to restore into legacy import_tasks and return its view
        if task_id in import_tasks:
            return DataImportService.get_task_status(task_id)
        else:
            task = UnifiedDataImportService._restore_task(task_id)
            if task:
                try:
                    import_tasks[task_id] = task
                except Exception:
                    pass
                return DataImportService.get_task_status(task_id)

        return {
            'status': 'not_found',
            'error': f'Task {task_id} not found in memory or disk',
        }
    except Exception as e:
        safe_error("/data-import/status/{task_id}", e)


@app.post("/api/v1/import/cancel/{task_id}")
@app.post("/api/import/cancel/{task_id}")
@app.post("/data-import/cancel/{task_id}")
def cancel_import(task_id: str):
    """Cancel a processing import task."""
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService

        status = UnifiedDataImportService.get_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        UnifiedDataImportService.cancel_import(task_id)
        updated = UnifiedDataImportService.get_status(task_id) or status
        return {
            "task_id": task_id,
            "status": updated.get("status"),
            "message": "Import task cancelled" if updated.get("status") == "cancelled" else "Task is not in a cancellable state",
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/import/cancel/{task_id}", e)


@app.get("/api/v1/import/formats")
def get_import_formats():
    """Return supported import file extensions."""
    try:
        from backend.Services.unified_data_import import FileFormatDetector

        return {
            "supported_formats": FileFormatDetector.get_supported_formats(),
            "formats": FileFormatDetector.get_supported_formats(),
        }
    except Exception as e:
        safe_error("/api/v1/import/formats", e)


@app.get("/api/v1/import/owl/{task_id}")
def get_import_owl(task_id: str):
    """Return generated OWL/Turtle content for an import task when available."""
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService

        status = UnifiedDataImportService.get_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        owl_ttl = status.get("owl_ttl")
        if not owl_ttl:
            raise HTTPException(status_code=404, detail=f"No OWL content available for task: {task_id}")

        return {
            "task_id": task_id,
            "format": "text/turtle",
            "owl_ttl": owl_ttl,
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/import/owl/{task_id}", e)



@app.get("/api/v1/import/owl/{task_id}/export")
def export_import_owl(task_id: str, format: str = Query("ttl", pattern="^(ttl|rdf|owl|jsonld)$")):
    """Download generated ontology content as TTL, RDF/XML, OWL/XML, or JSON-LD."""
    try:
        from rdflib import Graph as RDFGraph
        from backend.Services.unified_data_import import UnifiedDataImportService

        status = UnifiedDataImportService.get_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        owl_ttl = status.get("owl_ttl")
        if not owl_ttl:
            raise HTTPException(status_code=404, detail=f"No OWL content available for task: {task_id}")

        export_format = (format or "ttl").lower()
        filename_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(status.get("filename") or f"ontology_{task_id}"))
        filename_base = re.sub(r"\.(ttl|rdf|owl|jsonld|json)$", "", filename_base, flags=re.IGNORECASE)
        export_map = {
            "ttl": {"rdflib": "turtle", "media": "text/turtle", "ext": "ttl"},
            "rdf": {"rdflib": "xml", "media": "application/rdf+xml", "ext": "rdf"},
            "owl": {"rdflib": "pretty-xml", "media": "application/rdf+xml", "ext": "owl"},
            "jsonld": {"rdflib": "json-ld", "media": "application/ld+json", "ext": "jsonld"},
        }
        spec = export_map[export_format]

        if export_format == "ttl":
            content = owl_ttl
        else:
            graph = RDFGraph()
            try:
                graph.parse(data=owl_ttl, format="turtle")
                content = graph.serialize(format=spec["rdflib"])
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Generated Turtle could not be serialized as {export_format}: {exc}")

        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        headers = {"Content-Disposition": f'attachment; filename="{filename_base}.{spec["ext"]}"'}
        return Response(content=body, media_type=f'{spec["media"]}; charset=utf-8', headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/import/owl/{task_id}/export", e)


@app.get("/api/v1/ontology/{ontology_id}/export")
def export_registered_ontology(ontology_id: str, format: str = Query("ttl", pattern="^(ttl|rdf|owl|jsonld)$")):
    """Download a registered/generated ontology as TTL, RDF/XML, OWL/XML, or JSON-LD."""
    try:
        from rdflib import Graph as RDFGraph
        from backend.Services.ontology_upload_manager import OntologyUploadManager

        meta_result = OntologyUploadManager.get_ontology(ontology_id)
        if meta_result.get("status") != "success":
            raise HTTPException(status_code=404, detail=f"Ontology not found: {ontology_id}")
        meta = meta_result.get("metadata") or {}
        export_format = (format or "ttl").lower()
        artifacts = meta.get("ontology_export_artifacts") or []
        direct = next((item for item in artifacts if str(item.get("format") or "").lower() == export_format), None)
        if direct:
            direct_path = _Path(str(direct.get("path") or ""))
            if direct_path.exists():
                filename_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(meta.get("ontology_name") or meta.get("prefix") or ontology_id))
                ext = "ttl" if export_format == "ttl" else export_format
                return FileResponse(path=str(direct_path), filename=f"{filename_base}.{ext}")

        source_path = _Path(str(meta.get("owl_file_path") or meta.get("file_path") or ""))
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Ontology semantic file is missing for: {ontology_id}")

        export_map = {
            "ttl": {"rdflib": "turtle", "media": "text/turtle", "ext": "ttl"},
            "rdf": {"rdflib": "xml", "media": "application/rdf+xml", "ext": "rdf"},
            "owl": {"rdflib": "pretty-xml", "media": "application/rdf+xml", "ext": "owl"},
            "jsonld": {"rdflib": "json-ld", "media": "application/ld+json", "ext": "jsonld"},
        }
        spec = export_map[export_format]
        graph_obj = RDFGraph()
        parse_formats = ["turtle", "xml", "n3"] if source_path.suffix.lower() == ".ttl" else ["xml", "turtle", "n3"]
        last_error = None
        for parse_format in parse_formats:
            try:
                graph_obj.parse(str(source_path), format=parse_format)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error:
            raise HTTPException(status_code=422, detail=f"Ontology could not be parsed for export: {last_error}")
        content = graph_obj.serialize(format=spec["rdflib"])
        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        filename_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(meta.get("ontology_name") or meta.get("prefix") or ontology_id))
        headers = {"Content-Disposition": f'attachment; filename="{filename_base}.{spec["ext"]}"'}
        return Response(content=body, media_type=f'{spec["media"]}; charset=utf-8', headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/ontology/{ontology_id}/export", e)


@app.get("/api/v1/import/artifacts/{task_id}")
def get_import_artifacts(task_id: str):
    """Return retained workflow artifacts for an import task."""
    try:
        from backend.Services.workflow_artifact_service import WorkflowArtifactService

        manifest = WorkflowArtifactService.get_manifest(task_id)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"No artifacts found for task: {task_id}")
        return manifest
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/import/artifacts/{task_id}", e)


@app.get("/api/v1/workflows/options")
def get_workflow_options():
    """Return executable semantic workflow IDs."""
    from backend.Services.workflow_registry import get_workflow_options as list_workflow_options

    return {"workflows": list_workflow_options()}


@app.post("/api/v1/workflows/execute")
def execute_workflow(request: WorkflowExecuteRequest):
    """Execute an artifact-first semantic workflow."""
    try:
        from backend.Services.semantic_workflow_service import SemanticWorkflowService

        return SemanticWorkflowService.execute(request.workflow_id, request.payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        safe_error("/api/v1/workflows/execute", e)


@app.get("/api/v1/workflows/artifacts/{task_id}/{artifact_path:path}")
def get_workflow_artifact_file(task_id: str, artifact_path: str):
    """Return one retained workflow artifact file by manifest path."""
    try:
        from backend.Services.workflow_artifact_service import WorkflowArtifactService

        artifact_file = WorkflowArtifactService.resolve_artifact_path(task_id, artifact_path)
        if not artifact_file:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_path}")
        return FileResponse(path=str(artifact_file), filename=artifact_file.name)
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/workflows/artifacts/{task_id}/{artifact_path}", e)


@app.get("/api/v1/import/tasks")
@app.get("/api/import/tasks")
@app.get("/data-import/tasks")
def list_import_tasks():
    """List all import tasks."""
    try:
        # Unified imports are persisted on disk and must remain selectable in
        # Semantic Bridge after a backend restart. Keep legacy tasks visible
        # too, while deduplicating task IDs shared by both stores.
        from backend.Services.unified_data_import import UnifiedDataImportService

        tasks_by_id = {
            str(task.get('task_id')): task
            for task in DataImportService.list_tasks()
            if task.get('task_id')
        }
        for task in UnifiedDataImportService.list_tasks():
            if task.get('task_id'):
                tasks_by_id[str(task['task_id'])] = task
        tasks = sorted(
            tasks_by_id.values(),
            key=lambda task: str(task.get('started_at') or ''),
            reverse=True,
        )
        return {
            "total_tasks": len(tasks),
            "tasks": tasks,
        }
    except Exception as e:
        safe_error("/data-import/tasks", e)


@app.get("/api/v1/import/ollama/health")
def ollama_health():
    """Check local Ollama availability for conversational endpoints."""
    try:
        service = get_ollama_service()
        healthy = service.health_check()
        models = service.list_models() if healthy else []
        return {
            "healthy": healthy,
            "base_url": service.base_url,
            "model": service.model,
            "available_models": models,
        }
    except Exception as e:
        safe_error("/api/v1/import/ollama/health", e)


@app.post("/api/v1/import/ollama/query")
def ollama_query(payload: OllamaQueryRequest):
    """Query Ollama for a conversational answer."""
    try:
        question = (payload.query or "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="Query is required")

        service = get_ollama_service()
        if not service.health_check():
            raise HTTPException(status_code=503, detail="Ollama is not available")

        response = service.answer_question(question)
        return response
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/import/ollama/query", e)


@app.get("/api/v1/import/preview/{task_id}")
@app.get("/api/import/preview/{task_id}")
@app.get("/data-import/preview/{task_id}")
def get_import_preview(task_id: str):
    """Get a preview of the import data for a task."""
    try:
        from backend.Services.unified_data_import import UnifiedDataImportService
        from backend.Services.data_import_service import import_tasks

        unified_preview = UnifiedDataImportService.get_preview(task_id)
        if unified_preview:
            unified_status = UnifiedDataImportService.get_status(task_id) or {}
            return {
                "task_id": task_id,
                "filename": unified_status.get("filename", ""),
                "file_type": unified_status.get("file_type", ""),
                "status": unified_status.get("status", ""),
                **unified_preview,
            }
        
        status = import_tasks.get(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        
        # Return summary preview
        result_data = status.get("result") or {}
        parsed_data = (result_data.get("parsed_data") or {})
        return {
            "task_id": task_id,
            "filename": status.get("filename", ""),
            "file_type": status.get("file_type", ""),
            "node_count": len(parsed_data.get("nodes", [])),
            "relationship_count": len(parsed_data.get("relationships", [])),
            "sample_nodes": parsed_data.get("nodes", [])[:5],  # First 5 nodes
            "status": status.get("status", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview failed for {task_id}: {e}", exc_info=True)
        safe_error("/api/v1/import/preview/{task_id}", e)


@app.get("/api/v1/import/pre-commit/{task_id}")
@app.get("/api/import/pre-commit/{task_id}")
@app.get("/data-import/pre-commit/{task_id}")
def pre_commit_check(task_id: str):
    """Pre-commit validation: check task readiness before commit."""
    try:
        from backend.Services.data_import_service import import_tasks
        from backend.Services.unified_data_import import UnifiedDataImportService

        # Prefer unified task state; it is the source used by STEP/STPX imports.
        status = UnifiedDataImportService.get_status(task_id)
        if not status:
            status = import_tasks.get(task_id)
        if not status:
            task = UnifiedDataImportService._restore_task(task_id)
            if task:
                import_tasks[task_id] = task
                status = UnifiedDataImportService.get_status(task_id) or import_tasks.get(task_id)
            else:
                return {
                    "ready": False,
                    "reason": f"Task not found: {task_id}",
                    "checks": {
                        "neo4j": {"ok": True},
                        "task": {"ok": False, "status": "NOT_FOUND", "rows": 0}
                    }
                }
        
        task_status = status.get("status", "")
        # Task is ready if it has completed processing or is ready for commit
        task_ok = task_status in ("completed", "ready_for_commit", "processing")
        
        preview = UnifiedDataImportService.get_preview(task_id) or {}
        result_data = status.get("result") or {}
        parsed_data = result_data.get("parsed_data", {})
        stats = status.get("stats") or {}
        node_count = (
            preview.get("row_count")
            or stats.get("row_count")
            or stats.get("entities_found")
            or len(parsed_data.get("nodes", []))
            or 0
        )
        
        neo4j_ok = False
        neo4j_message = "Unchecked"
        try:
            result = graph.query("RETURN 1 AS ok")
            neo4j_ok = bool(result)
            neo4j_message = "Connected" if neo4j_ok else "No response"
        except Exception as neo4j_exc:
            neo4j_message = str(neo4j_exc)

        ready = task_ok and neo4j_ok
        reason = ""
        if not task_ok:
            reason = f"Task not ready (status: {task_status})"
        elif not neo4j_ok:
            reason = f"Neo4j is not reachable: {neo4j_message}"
        
        return {
            "ready": ready,
            "reason": reason,
            "checks": {
                "neo4j": {"ok": neo4j_ok, "message": neo4j_message},
                "task": {
                    "ok": task_ok,
                    "status": task_status,
                    "rows": node_count
                }
            }
        }
    except Exception as e:
        logger.error(f"Pre-commit check failed for {task_id}: {e}", exc_info=True)
        return {
            "ready": False,
            "reason": f"Pre-commit check error: {str(e)}",
            "checks": {
                "neo4j": {"ok": False, "message": "Pre-commit check failed before Neo4j validation"},
                "task": {"ok": False, "status": "ERROR", "rows": 0}
            }
        }


@app.post("/api/v1/import/commit/{task_id}")
@app.post("/api/import/commit/{task_id}")
@app.post("/data-import/commit/{task_id}")
async def commit_import(task_id: str):
    """Commit import data to Neo4j."""
    try:
        # Prefer unified import flow which uses `parsed_rows` and handles OWL
        # generation and commit atomically. Falls back to legacy per-node
        # commit logic only if unified service isn't available.
        try:
            from backend.Services.unified_data_import import UnifiedDataImportService
        except Exception:
            UnifiedDataImportService = None

        # If unified service available, use its commit path which understands
        # the `parsed_rows` shape written by the parser.
        if UnifiedDataImportService is not None:
            try:
                result = await UnifiedDataImportService.commit_import(task_id)
                invalidate_graphvis_cache()
                try:
                    OSLCTRSService.publish_event(
                        OSLCTRSService.import_resource_uri(task_id),
                        "Modification",
                        title=f"Import committed for {task_id}",
                        metadata={"task_id": task_id, "path": "unified_commit", "result_summary": str(result)[:500]},
                    )
                except Exception as exc:
                    logger.warning("OSLC TRS publish skipped for import commit %s: %s", task_id, exc)
                return {"success": True, "task_id": task_id, "message": "Committed via unified service", "result": result}
            except ValueError as ve:
                # Task not found or not ready
                raise HTTPException(status_code=404, detail=str(ve))
            except Exception as ue:
                logger.error(f"Unified commit failed for {task_id}: {ue}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Unified commit failed: {ue}")

        # Legacy fallback: attempt to restore into legacy import_tasks and use
        # the older commit path (nodes/relationships shaped under result.parsed_data)
        try:
            from backend.Services.data_import_service import import_tasks
        except Exception:
            import_tasks = {}

        task = import_tasks.get(task_id)
        if not task:
            # Try restoring snapshot (works across workers)
            try:
                task = UnifiedDataImportService._restore_task(task_id) if UnifiedDataImportService else None
            except Exception:
                task = None
            if task:
                import_tasks[task_id] = task
            else:
                raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        # Legacy expects a `result` dict containing parsed_data.nodes/relationships
        result = task.get("result") or {}
        parsed_data = (result.get("parsed_data") or {})
        nodes = parsed_data.get("nodes", [])
        relationships = parsed_data.get("relationships", [])

        if not nodes and not relationships:
            raise HTTPException(status_code=400, detail="No data to commit")

        # Push to Neo4j using legacy graph API
        try:
            committed_count = 0
            for node in nodes:
                props = node.get("properties", {})
                node_id = props.get("id", "")
                if node_id:
                    label = _safe_cypher_identifier(node.get("label", "Element"), default="Element")
                    cypher = f"MERGE (n:`{label}` {{id: $id, import_id: $import_id}}) SET n += $props"
                    scoped_props = {**props, "import_id": task_id}
                    graph.query(
                        cypher,
                        {"id": node_id, "import_id": task_id, "props": scoped_props},
                        timeout=300,
                    )
                    committed_count += 1
            for rel in relationships:
                from_id = rel.get("from_props", {}).get("id", "")
                to_id = rel.get("to_props", {}).get("id", "")
                rel_type = _safe_cypher_identifier(rel.get("type", "RELATES_TO"), default="RELATES_TO")
                if from_id and to_id:
                    cypher = (
                        f"MATCH (a {{id: $from_id, import_id: $import_id}}) "
                        f"MATCH (b {{id: $to_id, import_id: $import_id}}) "
                        f"MERGE (a)-[:`{rel_type}`]->(b)"
                    )
                    graph.query(
                        cypher,
                        {"from_id": from_id, "to_id": to_id, "import_id": task_id},
                        timeout=300,
                    )
                    committed_count += 1

            task["status"] = "committed"
            task["committed_count"] = committed_count
            task["completed_at"] = time.time()
            invalidate_graphvis_cache()
            try:
                OSLCTRSService.publish_event(
                    OSLCTRSService.import_resource_uri(task_id),
                    "Modification",
                    title=f"Import committed for {task_id}",
                    metadata={"task_id": task_id, "path": "legacy_commit", "committed_count": committed_count},
                )
            except Exception as exc:
                logger.warning("OSLC TRS publish skipped for import commit %s: %s", task_id, exc)
            return {
                "success": True,
                "task_id": task_id,
                "message": f"Successfully committed {committed_count} items to Neo4j",
                "committed_count": committed_count,
            }
        except Exception as neo4j_err:
            logger.error(f"Failed to commit to Neo4j (legacy path): {neo4j_err}")
            task["status"] = "commit_failed"
            task["error"] = str(neo4j_err)
            raise HTTPException(status_code=500, detail=f"Failed to commit to Neo4j: {str(neo4j_err)}")
    
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/api/v1/import/commit/{task_id}", e)


# ============================================================================
# Webhook Handlers with Signature Validation
# ============================================================================
try:
    from .Services.webhook_validator import WebhookValidator, WEBHOOK_SECRETS
except ImportError:
    from Services.webhook_validator import WebhookValidator, WEBHOOK_SECRETS

# Configure webhook secrets from environment variables
# Set as: NEO4J_WEBHOOK_SECRET="your_secret_key" in .env
def init_webhook_secrets():
    """Initialize webhook secrets from environment variables"""
    neo4j_secret = os.getenv("NEO4J_WEBHOOK_SECRET", None)
    if neo4j_secret:
        WEBHOOK_SECRETS["neo4j_events"] = neo4j_secret
        logger.info("Neo4j webhook secret configured")

init_webhook_secrets()

@app.post("/api/v1/webhooks/neo4j")
@app.post("/api/webhooks/neo4j")  # Backward compatibility
async def handle_neo4j_webhook(request: Request):
    """
    Handle webhooks from Neo4j event stream
    
    Header requirements:
        X-Webhook-Signature: sha256=<computed_hmac>
        X-Webhook-Timestamp: <unix_timestamp>
    
    Environment variable required:
        NEO4J_WEBHOOK_SECRET="your_secret"
    """
    try:
        if "neo4j_events" not in WEBHOOK_SECRETS:
            logger.warning("Neo4j webhook endpoint called but secret not configured")
            raise HTTPException(500, "Webhook not configured")
        
        # Read request body
        body = await request.body()
        
        # Get headers
        signature_header = request.headers.get("X-Webhook-Signature", "")
        timestamp_header = request.headers.get("X-Webhook-Timestamp", "")
        
        # Validate webhook
        validator = WebhookValidator("neo4j_events", WEBHOOK_SECRETS["neo4j_events"])
        is_valid, data, error = validator.validate_and_parse_json(
            body,
            signature_header,
            timestamp_header
        )
        
        if not is_valid:
            logger.warning(f"Webhook validation failed: {error}")
            raise HTTPException(401, f"Webhook validation failed: {error}")
        
        # Process webhook data
        logger.info(f"Processing Neo4j webhook: {data.get('event_type', 'unknown')}")
        
        # Example: Handle different event types
        event_type = data.get("event_type", "")
        if event_type == "node_created":
            logger.info(f"Node created: {data.get('node_id')}")
        elif event_type == "relationship_created":
            logger.info(f"Relationship created: {data.get('relationship_id')}")
        
        return {
            "status": "success",
            "message": "Webhook processed",
            "event_type": event_type
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(500, "Error processing webhook")



# ======================== ONTOLOGY MODELING WORKBENCH ENDPOINTS ========================


def _agentic_modeling_service():
    try:
        from backend.Services import agentic_modeling_service
    except Exception:
        from Services import agentic_modeling_service
    return agentic_modeling_service

def _modeling_service():
    try:
        from backend.Services import modeling_service
    except Exception:
        from Services import modeling_service
    return modeling_service


@app.get("/api/v1/modeling/metamodel")
async def modeling_metamodel():
    return _modeling_service().metamodel()


@app.post("/api/v1/modeling/indexes")
async def modeling_indexes():
    return _modeling_service().ensure_indexes()


@app.get("/api/v1/modeling/graph")
async def modeling_graph(project: str = "Digital Engineering Model", search: str = "", limit: int = Query(default=500, ge=1, le=2000)):
    return _modeling_service().list_graph(project=project, search=search, limit=limit)


@app.get("/api/v1/modeling/tree")
async def modeling_tree(project: str = "Digital Engineering Model"):
    return _modeling_service().tree(project=project)


@app.get("/api/v1/modeling/search")
async def modeling_search(q: str, project: str = "Digital Engineering Model", limit: int = Query(default=50, ge=1, le=200)):
    return _modeling_service().search(query=q, project=project, limit=limit)


@app.get("/api/v1/modeling/context/{element_id}")
async def modeling_context(element_id: str, depth: int = Query(default=1, ge=1, le=2), limit: int = Query(default=300, ge=1, le=1000)):
    return _modeling_service().context(element_id=element_id, depth=depth, limit=limit)


@app.post("/api/v1/modeling/nodes")
async def modeling_create_node(payload: Dict[str, Any]):
    return _modeling_service().create_node(payload)


@app.put("/api/v1/modeling/nodes/{element_id}")
async def modeling_update_node(element_id: str, payload: Dict[str, Any]):
    return _modeling_service().update_node(element_id, payload)


@app.delete("/api/v1/modeling/nodes/{element_id}")
async def modeling_delete_node(element_id: str):
    return _modeling_service().delete_node(element_id)


@app.post("/api/v1/modeling/links")
async def modeling_create_link(payload: Dict[str, Any]):
    return _modeling_service().create_link(payload)


@app.put("/api/v1/modeling/links/{element_id}")
async def modeling_update_link(element_id: str, payload: Dict[str, Any]):
    return _modeling_service().update_link(element_id, payload)


@app.delete("/api/v1/modeling/links/{element_id}")
async def modeling_delete_link(element_id: str):
    return _modeling_service().delete_link(element_id)


@app.get("/api/v1/modeling/validation")
async def modeling_validation(project: str = "Digital Engineering Model"):
    return _modeling_service().validate(project=project)



@app.post("/api/v1/modeling/agent/proposals")
async def modeling_agent_create_proposal(payload: Dict[str, Any]):
    try:
        return _agentic_modeling_service().create_proposal(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/modeling/agent/proposals")
async def modeling_agent_list_proposals(project: str = "Digital Engineering Model", limit: int = Query(default=50, ge=1, le=200)):
    return _agentic_modeling_service().list_proposals(project=project, limit=limit)


@app.post("/api/v1/modeling/agent/proposals/{proposal_id}/approve")
async def modeling_agent_approve_proposal(proposal_id: str, payload: Dict[str, Any] | None = None):
    payload = payload or {}
    result = _agentic_modeling_service().approve_proposal(proposal_id, approved_by=payload.get("approved_by") or "user", comment=payload.get("comment") or "")
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Agent proposal not found")
    if result.get("error") == "invalid_state":
        raise HTTPException(status_code=409, detail=f"Agent proposal is already {result.get('current_status') or 'finalized'}")
    return result


@app.post("/api/v1/modeling/agent/proposals/{proposal_id}/reject")
async def modeling_agent_reject_proposal(proposal_id: str, payload: Dict[str, Any] | None = None):
    payload = payload or {}
    result = _agentic_modeling_service().reject_proposal(proposal_id, rejected_by=payload.get("rejected_by") or "user", comment=payload.get("comment") or "")
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Agent proposal not found")
    if result.get("error") == "invalid_state":
        raise HTTPException(status_code=409, detail=f"Agent proposal is already {result.get('current_status') or 'finalized'}")
    return result
@app.post("/api/v1/modeling/seed")
async def modeling_seed(payload: Dict[str, Any] | None = None):
    payload = payload or {}
    return _modeling_service().seed_sample(project=payload.get("project") or "Digital Engineering Model")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
