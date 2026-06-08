import os
import sys
import asyncio
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Request, APIRouter, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
import logging as _logging
from logging.handlers import RotatingFileHandler
import json
import re

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

# Ensure Neo4j vector + keyword indexes exist BEFORE any module tries to
# connect to them (e.g. chains/vector.py imported via agent.chat).
ensure_indexes_standalone = None
try:
    from .Services.graph_embeddings import ensure_indexes_standalone
except Exception:
    try:
        from Services.graph_embeddings import ensure_indexes_standalone
    except Exception as _exc:
        logger.warning("Index pre-creation skipped: %s", _exc)

try:
    if ensure_indexes_standalone is not None:
        ensure_indexes_standalone()
except Exception as _exc:
    logger.warning("Index pre-creation skipped: %s", _exc)

try:
    from .agent.chat import generate_response, generate_response_stream #generate_response_with_cypher
except Exception as _exc:
    try:
        from agent.chat import generate_response, generate_response_stream #generate_response_with_cypher
    except Exception as _full_exc:
        logger.warning("Agent chat module not available: %s", _exc)
        logger.info("Using fallback chat implementation with Ollama")
        
        # Fallback: Simple Ollama-based chat without the complex agent
        from Services.ollama_service import get_ollama_service
        
        async def _fallback_generate_response(session_id: str, message: str) -> str:
            """Fallback chat implementation using Ollama directly"""
            try:
                service = get_ollama_service()
                response = service.query(message)
                return response or "I couldn't generate a response. Please try again."
            except Exception as e:
                logger.error(f"Fallback chat error: {type(e).__name__}: {e}", exc_info=True)
                return "I encountered an error processing your request. Please try again later."
        
        async def _fallback_generate_response_stream(session_id: str, message: str):
            """Fallback streaming chat implementation using Ollama directly"""
            try:
                service = get_ollama_service()
                response = service.query(message)
                if response:
                    # Stream the response in chunks
                    chunk_size = 6
                    for i in range(0, len(response), chunk_size):
                        yield f"data: {json.dumps({'token': response[i:i + chunk_size]})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                logger.error(f"Fallback stream error: {type(e).__name__}: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': 'Error processing your request'})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
        
        generate_response = _fallback_generate_response
        generate_response_stream = _fallback_generate_response_stream

try:
    from .core.graph import graph, get_graph_schema, cleanup_graph_connection
    # from .models.schema import ChatRequest, ChatResponse, ResetRequest, TextSearchRequest, ChatWithCypherResponse
    # from .agent.memory import reset_memory
    from .models.schema import ChatRequest, ChatResponse, TextSearchRequest
    from .data_ingestion import router as ingestion_router
    from .Services.unified_import_router import router as unified_import_router, ontology_router as ontology_upload_router
    from .routes.ontology_routes import router as ontology_router
    from .routes.threedxml_routes import router as threedxml_router
    from .routes.admin_routes import router as admin_router
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
    from backend.routes.threedxml_routes import router as threedxml_router
    from backend.routes.admin_routes import router as admin_router

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup complete — yield to allow request handling
    try:
        yield
    finally:
        logger.info("Application shutting down...")
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

# ✅ SECURE: Load allowed origins from environment with fallback
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

# Add CORS middleware with secure configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Restricted to specific origins from .env
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Only allow safe HTTP methods
    allow_headers=["Content-Type", "Authorization", "Cache-Control"],  # Cache-Control needed for no-cache requests
)

# 🔒 SECURITY: Rate limiting to prevent brute force attacks
from collections import defaultdict
from time import time as unix_time

request_counts = defaultdict(list)  # Track requests per IP: {ip: [timestamp, timestamp, ...]}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 100  # max requests per window

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
        current_time = unix_time()
        
        # Clean old requests (older than window)
        request_counts[client_ip] = [
            t for t in request_counts[client_ip]
            if current_time - t < RATE_LIMIT_WINDOW
        ]
        
        # Check rate limit
        if len(request_counts[client_ip]) >= RATE_LIMIT_MAX:
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
        
        # Record request
        request_counts[client_ip].append(current_time)
        
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
        client_ip = scope.get("client", ("unknown", 0))[0]
        
        current_time = unix_time()
        
        # Clean expired sessions
        expired_sessions = [
            sid for sid, sess in session_store.items()
            if current_time - sess.get('last_accessed_at', current_time) > SESSION_TIMEOUT
        ]
        for sid in expired_sessions:
            del session_store[sid]
            if sid in session_ips:
                del session_ips[sid]
        
        # Check session validity
        if session_id and session_id in session_store:
            session = session_store[session_id]
            
            # Check for IP change (session fixation detection)
            if client_ip not in session_ips[session_id]:
                # IP changed - rotate session
                logger.warning(f"Session IP mismatch detected. Rotating session. Old IP: {session_ips[session_id]}, New IP: {client_ip}")
                old_session_id = session_id
                session_id = str(uuid4())
                session_store[session_id] = session
                session_ips[session_id] = [client_ip]
                del session_store[old_session_id]
                del session_ips[old_session_id]
            
            # Update last accessed time
            session['last_accessed_at'] = current_time
        else:
            # Create new session
            session_id = str(uuid4())
            session_store[session_id] = {
                'created_at': current_time,
                'last_accessed_at': current_time,
                'data': {}
            }
            session_ips[session_id] = [client_ip]
        
        # Pass session ID to app via scope
        scope['session_id'] = session_id
        
        await self.app(scope, receive, send)

app.add_middleware(SessionSecurityMiddleware)

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
                    (b"content-security-policy", b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:"),
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
    - Graph operations: 2 minutes (120s)
    - All others: 1 minute (60s)
    """
    
    def __init__(self, app):
        self.app = app
        # Endpoint-specific timeout mappings
        self.endpoint_timeouts = {
            '/api/v1/import': 300,  # 5 minutes for import operations
            '/api/import': 300,      # Legacy route
            '/api/v1/ontology/upload': 300,  # 5 minutes for ontology uploads
            '/api/ontology/upload': 300,     # Legacy route
            '/chat': 300,            # 5 minutes for chat responses
            '/chat-stream': 300,     # 5 minutes for streaming responses
            '/graphvis': 120,        # 2 minutes for graph visualization
            '/graphfilter': 120,     # 2 minutes for filtering
        }
        self.default_timeout = 60  # 1 minute default
    
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

# 🔒 SECURITY: Neo4j query timeout configuration
NEO4J_QUERY_TIMEOUT = int(os.getenv("NEO4J_QUERY_TIMEOUT", "30"))  # 30 seconds default
NEO4J_DRIVER_TIMEOUT = 60  # Connection timeout

# Chat/session timing controls
# Extended timeouts for Ollama model inference and streaming responses
CHAT_REQUEST_TIMEOUT_SECONDS = int(os.getenv("CHAT_REQUEST_TIMEOUT_SECONDS", "180"))  # 3 min
CHAT_STREAM_TIMEOUT_SECONDS = int(os.getenv("CHAT_STREAM_TIMEOUT_SECONDS", "300"))  # 5 min
SESSION_LOCK_TIMEOUT_SECONDS = int(os.getenv("SESSION_LOCK_TIMEOUT_SECONDS", "15"))  # Allow slower systems
SESSION_LOCK_TTL_SECONDS = int(os.getenv("SESSION_LOCK_TTL_SECONDS", "1800"))

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
    try:
        await asyncio.wait_for(lock.acquire(), timeout=SESSION_LOCK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=429,
            detail="Another request is in progress for this session. Please retry shortly.",
        ) from exc

    try:
        yield
    finally:
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


async def _stream_with_timeout(session_id: str, message: str):
    stream_iter = None
    try:
        async with _session_lock(session_id):
            stream_iter = generate_response_stream(session_id, message)
            deadline = time.monotonic() + CHAT_STREAM_TIMEOUT_SECONDS
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                try:
                    event = await asyncio.wait_for(stream_iter.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    break
                yield event
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
from functools import wraps

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", None)  # Optional: Require API key for sensitive endpoints

def require_api_key(func):
    """
    Decorator to require API key for sensitive endpoints
    Pass key via X-API-Key header: X-API-Key: your-secret-key
    """
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if ADMIN_API_KEY:
            api_key = request.headers.get("X-API-Key")
            if api_key != ADMIN_API_KEY:
                logger.warning(f"Unauthorized API access attempt from {request.client.host}")
                raise HTTPException(status_code=401, detail="Invalid or missing API key")
        
        return await func(request, *args, **kwargs)
    
    return wrapper

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
            "status": "error"
        }
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
app.include_router(threedxml_router, prefix="/api/v1", tags=["v1-3dxml"])
app.include_router(admin_router, prefix="/api/v1", tags=["v1-admin"])

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
        # Return empty schema gracefully instead of 500 error
        return {
            "node_labels": {},
            "rel_types": {},
            "display_names": {},
            "message": "Neo4j database temporarily unavailable. Schema will load when database is connected."
        }


# @app.post("/chat")
# def chat(prompt):
#     try:
#       completion = secure_models.complete(prompt)
#       return {"results": completion.text}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if generate_response is None:
        raise HTTPException(status_code=503, detail="Chat service is unavailable. Please check backend configuration.")

    try:
        async with _session_lock(request.session_id):
            result = await _run_with_timeout(
                generate_response,
                CHAT_REQUEST_TIMEOUT_SECONDS,
                request.session_id,
                request.message,
            )
        return ChatResponse(session_id=request.session_id, response=result)
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning("Chat request timed out for session %s", request.session_id)
        raise HTTPException(status_code=504, detail="Chat request timed out. Please retry with a narrower question.")
    except Exception as e:
        logger.error(f"Chat endpoint error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process chat request. Please try again later.")


@app.post("/chat-stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint — returns Server-Sent Events (text/event-stream).
    Each event is a JSON object:
      {"token": "..."}   — next text chunk
      {"status": "..."}  — tool-call status label
      {"done": true}     — stream finished
      {"error": "..."}   — error message
    """
    if generate_response_stream is None:
        raise HTTPException(status_code=503, detail="Chat stream service is unavailable. Please check backend configuration.")

    return StreamingResponse(
        _stream_with_timeout(request.session_id, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/chat/sample-queries")
async def get_sample_queries():
    """Return dynamically generated sample queries based on actual Neo4j data.

    Picks representative entities from each domain:
      - ProvidedPart  → motor component queries
      - GeneralOperation / HeaderOperation → assembly process queries
      - MbseNode Class → SysML MBSE queries
      - UseCase → use-case queries
    Falls back to hardcoded domain-specific defaults when the graph is empty.
    """
    try:
        from chains.cypher import query_cypher

        def _fetch(cypher):
            try:
                return [r.get("name") for r in query_cypher(cypher) if r.get("name")]
            except Exception:
                return []

        parts       = _fetch("MATCH (n:ProvidedPart) RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 5")
        operations  = _fetch("MATCH (n:GeneralOperation) RETURN DISTINCT n.name AS name ORDER BY n.name LIMIT 3")
        assemblies  = _fetch("MATCH (n:ManufacturingAssembly) RETURN DISTINCT n.name AS name LIMIT 2")
        mbse_cls    = _fetch("MATCH (n:Class:MbseNode) WHERE n.name IS NOT NULL AND size(n.name) > 3 RETURN n.name AS name ORDER BY n.name LIMIT 3")
        use_cases   = _fetch("MATCH (n:UseCase:MbseNode) WHERE n.name IS NOT NULL AND size(n.name) > 3 RETURN n.name AS name LIMIT 2")
        packages    = _fetch("MATCH (n:Package:MbseNode) WHERE n.name IS NOT NULL AND NOT n.name STARTS WITH 'Basic' RETURN n.name AS name LIMIT 2")

        data_available = any([parts, operations, assemblies, mbse_cls, use_cases])

        if data_available:
            part1  = parts[0]       if parts       else "ROTOR SHAFT"
            part2  = parts[1]       if len(parts) > 1 else "LAMINATED ROTOR CORE"
            part3  = parts[2]       if len(parts) > 2 else "THREE PHASE WINDINGS"
            asm1   = assemblies[0]  if assemblies  else "5 HP MOTOR ASSEMBLY"
            op1    = operations[0]  if operations  else "#170_Operation-FDA Unit Electric A"
            cls1   = mbse_cls[0]    if mbse_cls    else "Variable Speed Drive"
            cls2   = mbse_cls[1]    if len(mbse_cls) > 1 else "Sugar Production Plant"
            uc1    = use_cases[0]   if use_cases   else "Energy efficiency for juice purification"
            pkg1   = packages[0]    if packages    else "2 Functional Analysis"

            sample_queries = [
                # Motor / XPDMXML domain
                f'What are all the parts in the "{asm1}" and in what sequence are they assembled?',
                f'Show the complete assembly operation sequence for "{asm1}"',
                f'Recommend manufacturing processes for "{part1}"',
                f'Find parts similar to "{part2}" that could be substituted',
                f'What operations does "{part3}" go through during assembly?',
                f'Analyse change impact if "{part1}" is modified',
                # SysML / MBSE domain
                f'What are the SysML requirements related to "{cls1}"?',
                f'Show all use cases and actors in the "{pkg1}" package',
                f'Trace the MBSE requirements for use case "{uc1}"',
                f'Which SysML blocks are associated with "{cls2}"?',
                # Cross-domain
                f'Analyse change impact if "{part1}" is modified',
                f'What ontology classes does "{asm1}" instantiate?',
            ]
        else:
            # Hardcoded domain-specific fallbacks
            sample_queries = [
                'What are all the parts in the 5 HP MOTOR ASSEMBLY and in what sequence are they assembled?',
                'Show the complete assembly operation sequence for 5 HP MOTOR ASSEMBLY',
                'Recommend manufacturing processes for ROTOR SHAFT',
                'Find parts similar to LAMINATED ROTOR CORE that could be substituted',
                'What SysML requirements relate to the Variable Speed Drive?',
                'Show all use cases and actors in the Sugar Production Plant MBSE model',
                'Analyse change impact if ROTOR SHAFT is modified',
                'Analyse change impact if THREE PHASE WINDINGS is modified',
            ]

        all_entities = parts + operations + assemblies + mbse_cls + use_cases
        return JSONResponse({
            "queries": sample_queries,
            "data_available": data_available,
            "entity_count": len(all_entities),
            "sample_entities": all_entities[:8],
        })

    except Exception as e:
        logger.error(f"Sample queries error: {e}", exc_info=True)
        return JSONResponse({
            "queries": [
                'What are all the parts in the 5 HP MOTOR ASSEMBLY and in what sequence are they assembled?',
                'Show the complete assembly operation sequence for 5 HP MOTOR ASSEMBLY',
                'Recommend manufacturing processes for ROTOR SHAFT',
                'Find parts similar to LAMINATED ROTOR CORE that could be substituted',
                'What SysML requirements relate to the Variable Speed Drive?',
                'Show all use cases and actors in the Sugar Production Plant MBSE model',
                'Analyse change impact if ROTOR SHAFT is modified',
                'Analyse change impact if THREE PHASE WINDINGS is modified',
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

_graphvis_cache: dict = {"data": None, "ts": 0.0}
_GRAPHVIS_CACHE_TTL = 60  # 60 seconds — short enough that deleting Neo4j clears within a minute

def invalidate_graphvis_cache():
    """Clear graph cache when Neo4j connection fails"""
    global _graphvis_cache
    _graphvis_cache["data"] = None
    _graphvis_cache["ts"] = 0.0
    logger.info("Graph cache invalidated due to connection error")

@app.get("/health/neo4j")
async def check_neo4j_health():
    """Health check endpoint to verify Neo4j connectivity"""
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: graph.query("MATCH (n) RETURN count(n) as cnt LIMIT 1")),
            timeout=5.0
        )
        is_connected = result and len(result) > 0
        return {
            "status": "healthy" if is_connected else "degraded",
            "neo4j_connected": is_connected,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.warning(f"Neo4j health check failed: {type(e).__name__}: {str(e)}")
        # Invalidate cache on health check failure
        invalidate_graphvis_cache()
        return {
            "status": "unhealthy",
            "neo4j_connected": False,
            "error": str(e),
            "timestamp": time.time()
        }

@app.get("/graphvis")
async def get_entire_graph():
    import asyncio, time
    now = time.monotonic()
    if _graphvis_cache["data"] is not None and (now - _graphvis_cache["ts"]) < _GRAPHVIS_CACHE_TTL:
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
            timeout=25.0
        )
        try:
            isolated = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: graph.query(isolated_query)),
                timeout=10.0
            )
            results = results + isolated
        except Exception:
            pass
        if results:
            _graphvis_cache["data"] = results
            _graphvis_cache["ts"] = time.monotonic()
        return {"results": results}
    except asyncio.TimeoutError:
        logger.warning("/graphvis timed out — clearing cache and returning empty graph")
        # Clear cache on timeout to force fresh query on next attempt
        invalidate_graphvis_cache()
        return {"results": [], "message": "Graph query timed out. Try a more specific ontology type filter."}
    except Exception as e:
        logger.warning(f"/graphvis error: {type(e).__name__}: {str(e)}")
        # Clear cache on any error to prevent serving stale data
        invalidate_graphvis_cache()
        return {"results": [], "message": "Neo4j database temporarily unavailable. Graph will display when database is connected."}


@app.get("/api/v1/graph/view")
async def get_graph_view(limit: int = 1000):
    """Return a visualization-ready graph payload using the official Neo4j driver."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    return GraphViewService.get_graph_overview(limit=limit)


@app.get("/api/v1/graph/view/ontology/{prefix}")
async def get_virtual_ontology_view(prefix: str, limit: int = 1000):
    """Return a generated ontology-centric graph view without mutating base data."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    return GraphViewService.get_virtual_ontology_view(prefix=prefix, limit=limit)


@app.get("/api/v1/graph/contextual-subgraph")
async def get_contextual_subgraph(search: str = "", ontology_prefix: str = "", import_id: str = "", limit: int = 400):
    """Return a contextual subgraph for GraphRAG-style inspection."""
    try:
        from backend.Services.graph_view_service import GraphViewService
    except Exception:
        from Services.graph_view_service import GraphViewService

    return GraphViewService.get_contextual_subgraph(
        search=search,
        ontology_prefix=ontology_prefix,
        import_id=import_id,
        limit=limit,
    )


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
            workspace_root = Path(__file__).resolve().parents[2]

            sample_path: Path | None = None
            ontology_name = prefix_token.upper()
            description = "Bootstrapped from workspace sample file"

            if prefix_token == "sysml":
                candidates = list((workspace_root / "Depo_onto" / "backend" / "uploads").glob("**/SugarPlantMBSE.xmi"))
                if candidates:
                    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    sample_path = candidates[0]
                    ontology_name = "Sugar Plant MBSE (SysML)"

            if prefix_token == "ap239" and sample_path is None:
                ap239_candidates = [
                    workspace_root
                    / "Depo_onto"
                    / "data"
                    / "domain_models"
                    / "product_life_cycle_support"
                    / "Domain_model_4439_XMI"
                    / "STEPlib"
                    / "Application_protocols"
                    / "AP239"
                    / "AP239.xmi",
                    workspace_root
                    / "Depo_onto"
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
            timeout=25.0,
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
                    timeout=60.0,
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
        safe_error("/api/v1/ontology/{ontology_id}/taxonomy", e)


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
            timeout=20.0
        )
        
        return {"results": results or [], "layerType": "schema"}
    except asyncio.TimeoutError:
        logger.warning("/schema-graph timed out")
        return {"results": [], "message": "Schema graph query timed out"}
    except Exception as e:
        logger.warning(f"/schema-graph error: {type(e).__name__}: {str(e)}")
        return {"results": [], "message": "Failed to fetch schema graph"}


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
            timeout=20.0,
        )
        return {"results": results or [], "layerType": "instance"}
    except asyncio.TimeoutError:
        logger.warning("/instance-graph timed out")
        return {"results": [], "message": "Instance graph query timed out"}
    except Exception as e:
        logger.warning(f"/instance-graph error: {type(e).__name__}: {str(e)}")
        return {"results": [], "message": "Failed to fetch instance graph"}


@app.post("/graphfilter")
def filter_graph_nodes(request: TextSearchRequest):
    """Search graph nodes by text and return local relationships in graphvis shape."""
    input_val = (request.search or "").strip()
    if not input_val:
        return {"results": []}

    query = """
        MATCH (n)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
          AND (
            toLower(coalesce(n.name, '')) CONTAINS toLower($input)
            OR toLower(coalesce(n.label, '')) CONTAINS toLower($input)
            OR toLower(coalesce(n.FileName, '')) CONTAINS toLower($input)
            OR toLower(coalesce(n.id, '')) CONTAINS toLower($input)
            OR any(lbl IN labels(n) WHERE toLower(lbl) CONTAINS toLower($input))
          )
        WITH collect(DISTINCT n)[..100] AS matchedNodes
        UNWIND matchedNodes AS n
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IN matchedNodes
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
        results = graph.query(query, params={"input": input_val})
        return {"results": results}
    except Exception as e:
        safe_error("/graphfilter", e)


class ComparativeSearchRequest(BaseModel):
    nodeType: str = ""
    name: str = ""
    version: str = ""


@app.post("/comparative-search")
def comparative_search(request: ComparativeSearchRequest):
    """Search a node by type/name/version for the graph comparison UI."""
    node_type = (request.nodeType or "").strip()
    name = (request.name or "").strip()
    version = (request.version or "").strip()

    if not name and not node_type and not version:
        return {"results": []}

    query = """
        MATCH (n)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
          AND (
            $name = ''
            OR toLower(coalesce(n.name, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.label, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.FileName, '')) CONTAINS toLower($name)
            OR toLower(coalesce(n.id, '')) CONTAINS toLower($name)
          )
          AND (
            $node_type = ''
            OR any(lbl IN labels(n) WHERE toLower(lbl) CONTAINS toLower($node_type))
            OR toLower(coalesce(n.type, '')) CONTAINS toLower($node_type)
            OR toLower(coalesce(n.node_type, '')) CONTAINS toLower($node_type)
          )
          AND (
            $version = ''
            OR toLower(coalesce(n.version, '')) CONTAINS toLower($version)
            OR toLower(coalesce(n.Version, '')) CONTAINS toLower($version)
            OR toLower(coalesce(n.revision, '')) CONTAINS toLower($version)
          )
        WITH collect(DISTINCT n)[..100] AS matchedNodes
        UNWIND matchedNodes AS n
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IN matchedNodes
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
        results = graph.query(
            query,
            params={"node_type": node_type, "name": name, "version": version},
        )
        return {"results": results}
    except Exception as e:
        safe_error("/comparative-search", e)


class MultiNameSearchRequest(BaseModel):
    names: list[str]


@app.post("/graphfilter-multi")
def filter_graph_nodes_multi(request: MultiNameSearchRequest):
    """Fetch a set of named nodes and any relationships between them.
    Used by the 'View in Graph' feature to load recommendation result nodes."""
    # Cap at 100 names to avoid overloading Neo4j
    names = [n.strip() for n in request.names if n and n.strip()][:100]
    if not names:
        return {"results": []}

    query = """
UNWIND $names AS searchName
MATCH (n)
WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
  AND toLower(n.name) CONTAINS toLower(searchName)
WITH collect(DISTINCT n) AS matchedNodes
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
        results = graph.query(query, params={"names": names})
        return {"results": results}
    except Exception as e:
        safe_error("/graphfilter-multi", e)


@app.get("/graphtraverse/{node_id}")
def traverse_node(node_id: str = Path(..., description="Neo4j internal node ID")):
    try:
        query = """ 
            MATCH (n)
WHERE elementId(n) = $node_id

OPTIONAL MATCH (n)-[r1]-(m1)
WITH n, collect(DISTINCT {r: r1, m: m1})[..50] AS level1

UNWIND level1 AS l1
WITH n, level1, l1.m AS l1_node
OPTIONAL MATCH (l1_node)-[r2]-(m2)
WHERE elementId(m2) <> elementId(n)
WITH n, level1, collect(DISTINCT {r: r2, m: m2})[..30] AS level2

UNWIND level2 AS l2
WITH n, level1, level2, l2.m AS l2_node
OPTIONAL MATCH (l2_node)-[r3]-(m3)
WHERE elementId(m3) <> elementId(n)
WITH n, level1, level2, collect(DISTINCT {r: r3, m: m3})[..20] AS level3

WITH n, level1 + level2 + level3 AS all_rels
UNWIND all_rels AS rel_data
WITH n, rel_data.r AS r, rel_data.m AS m
WHERE r IS NOT NULL AND m IS NOT NULL

RETURN 
{
  elementId: elementId(n),
  labels: labels(n),
  properties: properties(n)
} AS n,

{
  elementId: elementId(r),
  type: type(r),
  properties: properties(r),
  start: elementId(startNode(r)),
  end: elementId(endNode(r))
} AS r,

{
  elementId: elementId(m),
  labels: labels(m),
  properties: properties(m)
} AS m

LIMIT 500
            """

        results = graph.query(query, params={"node_id": node_id})
        return {"results": results}
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
    LIMIT 100

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


# ======================== RECOMMENDATION ENDPOINTS ========================

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
    if not change_name and not part_name:
        raise HTTPException(status_code=400, detail="Provide 'change_name' or 'part_name'")
    try:
        return _change_impact.analyse(change_name=change_name, part_name=part_name)
    except Exception as e:
        safe_error("/recommendations/change-impact", e)


@app.post("/recommendations/similar-parts")
def recommend_similar_parts(body: dict):
    """Find similar parts given a part name."""
    part_name = body.get("part_name", "")
    top_n = body.get("top_n", 10)
    if not part_name:
        raise HTTPException(status_code=400, detail="Provide 'part_name'")
    try:
        return _similar_parts.recommend(part_name, top_n=int(top_n))
    except Exception as e:
        safe_error("/recommendations/similar-parts", e)


@app.post("/recommendations/manufacturing")
def recommend_manufacturing(body: dict):
    """Recommend manufacturing processes for a part."""
    part_name = body.get("part_name", "")
    if not part_name:
        raise HTTPException(status_code=400, detail="Provide 'part_name'")
    try:
        return _mfg_process.recommend(part_name)
    except Exception as e:
        safe_error("/recommendations/manufacturing", e)


@app.get("/recommendations/health")
def recommendations_health():
    """Service health check with key Neo4j counts."""
    try:
        counts = graph.query("""
            MATCH (p:Individual)-[:INSTANCE_OF]->(c:OntologyClass)
            WHERE c.name IN ['Part', 'Requirement', 'Process', 'GeneralRelation',
                             'ProductInstance', 'Function', 'ProcessInstance']
            RETURN c.name AS class_name, count(p) AS cnt
            ORDER BY cnt DESC
        """)
        return {
            "status": "ok",
            "services": ["change-impact", "similar-parts", "manufacturing"],
            "neo4j_counts": {r["class_name"]: r["cnt"] for r in counts},
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


# ======================== ONTOLOGY MAPPER ENDPOINTS ========================

from Services.ontology_mapper_service import OntologyMapperService

@app.get("/ontology-mapper/options")
def get_mapping_options():
    """Get available ontology mapping options."""
    try:
        return {
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
        return stats
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
        return {
            "total_nodes": 0,
            "total_relationships": 0,
            "node_labels": [],
            "relationship_types": [],
            "ontology_breakdown": [],
            "ontology_kpis": {
                "classes": 0,
                "object_properties": 0,
                "datatype_properties": 0,
                "restrictions": 0,
                "shacl_shapes": 0,
                "individuals": 0,
                "axiom_proxy_count": 0,
                "class_to_property_ratio": 0,
            },
            "message": "Graph database temporarily unavailable.",
        }


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
from Services.data_import_service import DataImportService
from Services.ollama_service import get_ollama_service

# Directory containing ontology .ttl files served by the frontend
ONTOLOGY_DIR = _Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "Ontology"


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
async def upload_file(file: UploadFile = File(...), ontology_id: str = Form(""), ontology_mapping: str = Form("")):
    """Upload a file to the import pipeline with selected ontology.
    
    Parameters:
    - file: Data file (CSV, XLS, JSON, etc.)
    - ontology_id: ID of registered ontology (optional, overrides ontology_mapping)
    - ontology_mapping: Legacy ontology name/prefix (used if ontology_id not provided)
    
    Returns IMMEDIATELY with task_id (within 5 seconds) and processes file in background.
    Use /data-import/status/{task_id} to check processing progress.
    """
    try:
        # Read filename and content
        filename = file.filename or "unknown"
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="File is empty")

        # Prefer the unified import service which persists task snapshots so status
        # and commit operations work across workers/processes.
        from backend.Services.unified_data_import import FileFormatDetector, UnifiedDataImportService
        from backend.Services.ontology_upload_manager import OntologyUploadManager

        # Resolve ontology prefix from ontology_id (if provided)
        resolved_ontology_mapping = ontology_mapping
        if ontology_id:
            try:
                OntologyUploadManager.initialize()
                meta = OntologyUploadManager.load_metadata(ontology_id)
                if meta and meta.get('prefix'):
                    resolved_ontology_mapping = meta['prefix']
            except Exception as e:
                logger.warning(f"Could not resolve ontology_id '{ontology_id}': {e}. Using ontology_mapping instead.")
        
        # Start import via unified service (schedules parsing in background and persists snapshot)
        task_id = await UnifiedDataImportService.start_import(content, filename, resolved_ontology_mapping)

        return {
            "task_id": task_id,
            "filename": filename,
            "file_type": FileFormatDetector.detect(filename).value,
            "ontology_id": ontology_id,
            "ontology_mapping": resolved_ontology_mapping,
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
        tasks = DataImportService.list_tasks()
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
                    label = node.get("label", "Element")
                    cypher = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
                    graph.query(cypher, {"id": node_id, "props": props}, timeout=30)
                    committed_count += 1
            for rel in relationships:
                from_id = rel.get("from_props", {}).get("id", "")
                to_id = rel.get("to_props", {}).get("id", "")
                rel_type = rel.get("type", "RELATES_TO")
                if from_id and to_id:
                    cypher = f"MATCH (a {{id: $from_id}}) MATCH (b {{id: $to_id}}) MERGE (a)-[:{rel_type}]->(b)"
                    graph.query(cypher, {"from_id": from_id, "to_id": to_id}, timeout=30)
                    committed_count += 1

            task["status"] = "committed"
            task["committed_count"] = committed_count
            task["completed_at"] = time.time()
            invalidate_graphvis_cache()
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
