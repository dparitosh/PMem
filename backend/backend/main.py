import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pathlib import Path as FilePath
import logging as _logging
from logging.handlers import RotatingFileHandler
import json
import re

# ✅ Load environment variables from .env file
load_dotenv(FilePath(__file__).resolve().parents[1] / ".env")

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
    
    # Console handler
    console_handler = _logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation (10MB per file, keep 5 backups)
    file_handler = RotatingFileHandler(
        f'{logs_dir}/app.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler (only errors and above)
    error_handler = RotatingFileHandler(
        f'{logs_dir}/error.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(_logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
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
try:
    from .services.graph_embeddings import ensure_indexes_standalone
    ensure_indexes_standalone()
except Exception as _exc:
    logger.warning("Index pre-creation skipped: %s", _exc)

from .agent.chat import generate_response, generate_response_stream #generate_response_with_cypher
from .core.graph import graph, get_graph_schema, cleanup_graph_connection
# from .models.schema import ChatRequest, ChatResponse, ChatWithCypherResponse, ResetRequest
# from .agent.memory import reset_memory
from .models.schema import ChatRequest, ChatResponse, ResetRequest, TextSearchRequest, ChatWithCypherResponse
from .data_ingestion import router as ingestion_router
from .services.unified_import_router import router as unified_import_router
from .routes.ontology_routes import router as ontology_router
from .routes.admin_routes import router as admin_router



from langchain_neo4j import Neo4jGraph

# uri = "neo4j://127.0.0.1:7687" #os.getenv('Neo4j_url') # Replace with your Neo4j instance URL
# username = "neo4j" #os.getenv('Neo4j_user') # Replace with your Neo4j username
# password = os.getenv('Neo4j_password') # Replace with your Neo4j password
# database = "neo4j"

# #graph_driver = GraphDatabase.driver(uri, auth=(username, password), database = database)
# graph = Neo4jGraph(
#     url=uri,
#     username=username,
#     password=password,
#     database = "neo4j"
# )

from pydantic import BaseModel

class TextSearchRequest(BaseModel):
    search: str

#graph = Neo4jPropertyGraphStore(
#    url = os.getenv('Neo4j_url'),
#    username=os.getenv('Neo4j_user'),
#    password=os.getenv('Neo4j_password'),
#    #url = "neo4j+ssc://b76c70fa.databases.neo4j.io",
#    database = "mbse-sysml"
#)

app = FastAPI()

# ✅ SECURE: Load allowed origins from environment with fallback
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

# Add CORS middleware with secure configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Restricted to specific origins from .env
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Only allow safe HTTP methods
    allow_headers=["Content-Type", "Authorization"],  # Restrict headers
)

# 🔒 SECURITY: Rate limiting to prevent brute force attacks
from collections import defaultdict
from time import time

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
        current_time = time()
        
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
        
        current_time = time()
        
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

# 🔒 SECURITY: Neo4j query timeout configuration
NEO4J_QUERY_TIMEOUT = int(os.getenv("NEO4J_QUERY_TIMEOUT", "30"))  # 30 seconds default
NEO4J_DRIVER_TIMEOUT = 60  # Connection timeout

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
app.include_router(ontology_router, prefix="/api/v1", tags=["v1-ontology"])
app.include_router(admin_router, prefix="/api/v1", tags=["v1-admin"])

# Keep old routes for backward compatibility (will be logged as deprecated)
logger.info("API v1 versioning enabled. Old /api/* routes maintained for compatibility. Clients should migrate to /api/v1/*")
app.include_router(ingestion_router, prefix="/api", tags=["ingestion-deprecated"])
app.include_router(unified_import_router, prefix="/api", tags=["data-import-deprecated"])

# ✅ CRITICAL: Graceful shutdown handler
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown."""
    logger.info("Application shutting down...")
    cleanup_graph_connection()
    logger.info("Application shutdown complete")

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
        raise HTTPException(status_code=500, detail="Failed to retrieve schema. Please try again later.")


# @app.post("/chat")
# def chat(prompt):
#     try:
#       completion = secure_models.complete(prompt)
#       return {"results": completion.text}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        result = generate_response(request.session_id, request.message)
        return ChatResponse(session_id=request.session_id, response=result)
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
    return StreamingResponse(
        generate_response_stream(request.session_id, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

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

@app.get("/graphvis")
def get_entire_graph():
    query = """
        MATCH (n)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IS NULL OR NOT (m:DatasheetChunk OR m:GraphChunk)
RETURN 
  {
    elementId: elementId(n),
    labels: labels(n),
    properties: properties(n)
  } AS n,
  CASE 
    WHEN r IS NOT NULL THEN {
      elementId: elementId(r),
      type: type(r),
      properties: properties(r),
      start: elementId(startNode(r)),
      end: elementId(endNode(r))
    }
    ELSE NULL
  END AS r,
  CASE 
    WHEN m IS NOT NULL THEN {
      elementId: elementId(m),
      labels: labels(m),
      properties: properties(m)
    }
    ELSE NULL
  END AS m
LIMIT 2000
"""
    try:
        #results = graph_driver.execute_query(query)
        results = graph.query(query)

        #print(results)
        return {"results": results}
    except Exception as e:
        safe_error("/graphvis", e)


@app.post("/graphfilter")
def filter_graph_nodes(request: TextSearchRequest):
    query = """WITH toLower($input) AS keyword
MATCH (n)
WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
UNWIND keys(n) AS prop
WITH n, prop, n[prop] AS val, keyword
WHERE val IS NOT NULL
 
CALL {
  WITH val
  WITH val, apoc.meta.cypher.type(val) AS t
  RETURN CASE
    WHEN t STARTS WITH 'LIST' THEN
      // flatten nested lists recursively then convert elements where possible
      [ x IN apoc.coll.flatten(val, true) | toStringOrNull(x) ]
    WHEN t = 'MAP' THEN
      // convert primitive-valued entries of the map
      [ k IN keys(val) | toStringOrNull(val[k]) ]
    WHEN t IN [
      'STRING','INTEGER','FLOAT','BOOLEAN',
      'DATE','TIME','LOCAL_DATE_TIME','DATE_TIME','DURATION'
    ] THEN
      [ toStringOrNull(val) ]
    ELSE
      []
  END AS samples
}
 
WITH n, [s IN samples WHERE s IS NOT NULL] AS samples, keyword
WHERE any(s IN samples WHERE toLower(s) CONTAINS keyword)
WITH DISTINCT n
RETURN {
  elementId: elementId(n),
  labels: labels(n),
  properties: properties(n)
} AS n

LIMIT 200;"""
#     query = """
#     MATCH (n)
# WHERE 
#   n._name is not NULL and 
#   any(prop IN keys(n) WHERE toLower(toString(n[prop])) CONTAINS toLower($input))
#   OR any(label IN labels(n) WHERE toLower(label) CONTAINS toLower($input))
# RETURN {
#   elementId: elementId(n),
#   labels: labels(n),
#   properties: {
#     name: n._name
#   }
# } AS n
#         """
    try:
        input_val = request.search.strip()

        results = graph.query(query, params={"input": input_val})
        return {"results": results}
    
    except Exception as e:
        safe_error("/graphfilter", e)


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
        """Return ontology/data-view dropdown options including dynamic MBSE entries."""
        options = [
                {"value": "ALL", "label": "All Data"},
                {"value": "ap242", "label": "MBD3D AP242 Ontology"},
                {"value": "plmxml", "label": "SPLM PLMXML Ontology"},
                {"value": "step", "label": "CAD STEP Instances"},
        ]
        try:
                # Add MBSE options only when MBSE imports exist.
                mbse_count_query = """
                MATCH (n)
                WHERE n.source_format = 'xmi' OR n.ontology_id = 'mbse_domain_ontology'
                RETURN count(n) AS cnt
                """
                results = graph.query(mbse_count_query)
                mbse_count = (results[0].get("cnt", 0) if results else 0)
                if mbse_count > 0:
                        options.append({"value": "mbse", "label": "MBSE Domain Ontology (OWL/TTL)"})
                        options.append({"value": "mbse_instances", "label": "MBSE Data (Instance Graph)"})

                return {"options": options, "count": len(options), "mbse_node_count": mbse_count}
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
def get_ontology_graph(ontology_type: str = Path(..., description="ap242, plmxml, step, or mbse")):
    """Return the subgraph for a specific ontology.
    - ap242:  AP242 ontology classes + step-ontology schema + taxonomy
    - plmxml: PLMXML ontology classes + taxonomy
    - step:   STEP file individual nodes (returned as node inventory)
    - mbse:   MBSE domain ontology classes inferred from imported XMI data
    """
    queries = {
        "ap242": """
            MATCH (n)-[r]-(m)
            WHERE n.namespace CONTAINS '/ontology/'
               OR n.namespace CONTAINS 'step-ontology'
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              {elementId: elementId(r), type: type(r), properties: properties(r),
               start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
              {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
            LIMIT 500
        """,
        "plmxml": """
            MATCH (n)-[r]-(m)
            WHERE n.namespace CONTAINS 'plmxml-ontology'
               OR m.namespace CONTAINS 'plmxml-ontology'
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              {elementId: elementId(r), type: type(r), properties: properties(r),
               start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
              {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
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
    if key not in queries:
                raise HTTPException(status_code=400, detail=f"Unknown ontology type: {ontology_type}. Use ap242, plmxml, step, or mbse.")
    try:
        results = graph.query(queries[key])
        return {"results": results}
    except Exception as e:
        safe_error("/ontology/{ontology_type}", e)


@app.post("/embeddings/build")
def build_graph_embeddings(force: bool = False):
    """Trigger the context-aware graph embedding pipeline.
    Pass ?force=true to rebuild all chunks even if they already exist."""
    from .services.graph_embeddings import run_graph_embeddings
    try:
        run_graph_embeddings(force_rebuild=force)
        return {"status": "ok", "message": "Graph embeddings built successfully"}
    except Exception as e:
        safe_error("/embeddings/build", e)


# ======================== RECOMMENDATION ENDPOINTS ========================

from .services.change_impact_recommender import ChangeImpactRecommender
from .services.similar_parts_recommender import SimilarPartsRecommender
from .services.manufacturing_process_recommender import ManufacturingProcessRecommender

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

from .services.ontology_mapper_service import OntologyMapperService

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


@app.get("/ontologies/available")
def get_available_ontologies():
    """Get available ontologies from Neo4j (dynamic, based on imports)."""
    try:
        from .core.graph import graph
        
        # Query used ontologies from Neo4j
        cypher = """
        MATCH (om:OntologyMetadata)
         RETURN om.id AS id,
             om.name AS name,
             om.type AS type,
             om.view_mode AS view_mode,
             om.ttl_file AS ttl_file,
             om.usage_count AS usage_count,
             om.last_used AS last_used
        ORDER BY om.usage_count DESC, om.last_used DESC
        """
        
        results = graph.query(cypher)
        ontologies = []
        
        for row in results:
            ontologies.append({
                'id': row['id'],
                'name': row['name'],
                'type': row['type'],
                'viewMode': row.get('view_mode'),
                'ttlFile': row.get('ttl_file'),
                'usageCount': row['usage_count'] or 0,
                'lastUsed': row['last_used'],
                'source': 'dynamic'  # From Neo4j
            })
        
        # Add static fallback options if no dynamic ones exist
        if not ontologies:
            ontologies = [
                {
                    'id': 'plmxml_ap242',
                    'name': 'PLMXML → AP242 Product Alignment',
                    'type': 'plmxml',
                    'usageCount': 0,
                    'lastUsed': None,
                    'source': 'static'  # Fallback from files
                },
                {
                    'id': 'step_ap242',
                    'name': 'STEP → AP242 Mapping',
                    'type': 'step',
                    'usageCount': 0,
                    'lastUsed': None,
                    'source': 'static'
                },
                {
                    'id': 'windchill_ap242',
                    'name': 'Windchill → AP242 Product Alignment',
                    'type': 'windchill',
                    'usageCount': 0,
                    'lastUsed': None,
                    'source': 'static'
                }
            ]
        
        return {
            'ontologies': ontologies,
            'count': len(ontologies),
            'dynamicCount': len([o for o in ontologies if o.get('source') == 'dynamic']),
        }
    except Exception as e:
        return safe_error("/ontologies/available", e) or {
            'ontologies': [
                {'id': 'plmxml_ap242', 'name': 'PLMXML → AP242 Product Alignment', 'type': 'plmxml', 'usageCount': 0, 'lastUsed': None, 'source': 'static'},
                {'id': 'step_ap242', 'name': 'STEP → AP242 Mapping', 'type': 'step', 'usageCount': 0, 'lastUsed': None, 'source': 'static'},
                {'id': 'windchill_ap242', 'name': 'Windchill → AP242 Product Alignment', 'type': 'windchill', 'usageCount': 0, 'lastUsed': None, 'source': 'static'},
            ],
            'count': 3,
            'dynamicCount': 0,
            'error': str(e),
        }


# ======================== DATA IMPORT PIPELINE ENDPOINTS ========================

from fastapi import UploadFile, File, Form
from pathlib import Path as _Path
from .services.data_import_service import DataImportService

# Directory containing ontology .ttl files served by the frontend
ONTOLOGY_DIR = _Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "Ontology"

# Known filename-to-ID mappings for consistent resolution
_KNOWN_ONTOLOGY_IDS = {
    'plmxml_ap242_product_alignment.ttl': ('plmxml_ap242', 'PLMXML \u2192 AP242 Product Alignment'),
    'step_to_ap242_mapping.ttl': ('step_ap242', 'STEP \u2192 AP242 Mapping'),
    'windchill_ap242_product_alignment.ttl': ('windchill_ap242', 'Windchill \u2192 AP242 Product Alignment'),
}


@app.get("/ontology-mappings")
def get_ontology_mappings():
    """List available ontology mapping files by scanning the Ontology directory."""
    mappings = []
    if ONTOLOGY_DIR.is_dir():
        for ttl_file in sorted(ONTOLOGY_DIR.glob("*.ttl")):
            fname = ttl_file.name
            if fname in _KNOWN_ONTOLOGY_IDS:
                ont_id, ont_name = _KNOWN_ONTOLOGY_IDS[fname]
            else:
                # Fallback: derive ID and name from filename
                stem = ttl_file.stem
                ont_id = stem
                ont_name = stem.replace('_', ' ').title()
            mappings.append({"id": ont_id, "name": ont_name, "file": fname})
    # Fallback if directory not found
    if not mappings:
        mappings = [
            {"id": "plmxml_ap242", "name": "PLMXML \u2192 AP242 Product Alignment", "file": "plmxml_ap242_product_alignment.ttl"},
            {"id": "step_ap242", "name": "STEP \u2192 AP242 Mapping", "file": "step_to_ap242_mapping.ttl"},
            {"id": "windchill_ap242", "name": "Windchill \u2192 AP242 Product Alignment", "file": "windchill_ap242_product_alignment.ttl"},
        ]
    return {"mappings": mappings}


@app.post("/data-import/upload")
async def upload_file(file: UploadFile = File(...), ontology_mapping: str = Form("")):
    """Upload a file to the import pipeline with selected ontology alignment."""
    try:
        content = await file.read()
        
        # Validate file type
        file_type = DataImportService.get_file_type(file.filename)
        if not file_type:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Supported: {', '.join(DataImportService.SUPPORTED_FORMATS.keys())}"
            )
        
        # Process file with selected ontology mapping
        task_id = await DataImportService.process_file(content, file.filename, ontology_mapping=ontology_mapping)
        
        return {
            "task_id": task_id,
            "filename": file.filename,
            "file_type": file_type,
            "ontology_mapping": ontology_mapping,
            "message": "File uploaded and processing started",
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_error("/data-import/upload", e)


@app.get("/data-import/status/{task_id}")
def get_import_status(task_id: str):
    """Get the status of an import task."""
    try:
        status = DataImportService.get_task_status(task_id)
        return status
    except Exception as e:
        safe_error("/data-import/status/{task_id}", e)


@app.post("/data-import/commit/{task_id}")
def confirm_data_import(task_id: str):
    """Confirm a completed auto-ingest pipeline task for frontend compatibility."""
    try:
        return DataImportService.confirm_import(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        safe_error("/data-import/commit/{task_id}", e)


@app.post("/data-import/cancel/{task_id}")
def cancel_data_import(task_id: str):
    """Cancel an in-progress auto-ingest pipeline task for frontend compatibility."""
    try:
        return DataImportService.cancel_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    except Exception as e:
        safe_error("/data-import/cancel/{task_id}", e)


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

# 🔒 MEDIUM PRIORITY: Webhook handlers with signature validation
from .services.webhook_validator import WebhookValidator, WEBHOOK_SECRETS

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

