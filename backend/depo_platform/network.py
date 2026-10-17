"""Small, dependency-free networking configuration helpers."""
from __future__ import annotations

import os
import math

TIMEOUT_RANGES = {
    'AGENTIC_TOOL_TIMEOUT_SECONDS': (1, 3600),
    'AGENTIC_RUN_TIMEOUT_SECONDS': (1, 3600),
    'COMPANION_RETRIEVAL_TIMEOUT_SECONDS': (1, 120),
    'OSLC_CLIENT_TIMEOUT_SECONDS': (1, 3600),
    'SERVICE_REQUEST_TIMEOUT_SECONDS': (1, 300),
    'ENGINEERING_WORKFLOW_TIMEOUT_SECONDS': (1, 3600),
    'ENGINEERING_CONVERSION_TIMEOUT_SECONDS': (1, 900),
    'GRAPH_PUBLICATION_TIMEOUT_SECONDS': (1, 3600),
    'GRAPH_PUBLICATION_WRITE_TIMEOUT_SECONDS': (1, 3600),
    'GRAPH_PUBLICATION_ACTIVATION_TIMEOUT_SECONDS': (1, 3600),
    'MERGE_VALIDATION_TIMEOUT_SECONDS': (1, 900),
    'DEPO_READINESS_TIMEOUT_SECONDS': (1, 30),
    'ONTOLOGY_PUBLICATION_JOB_TIMEOUT_SECONDS': (1, 86400),
    'ONTOLOGY_PUBLICATION_QUEUE_TIMEOUT_SECONDS': (1, 86400),
    'BRIDGE_SOURCE_TIMEOUT_SECONDS': (1, 900),
    'DEPO_REQUEST_TIMEOUT_SECONDS': (1, 86400),
    'DEPO_CONTROL_REQUEST_TIMEOUT_SECONDS': (1, 60),
    'DEPO_PIPELINE_JOB_TIMEOUT_SECONDS': (1, 86400),
    'QIF_TASK_TIMEOUT_SECONDS': (1, 86400),
}


def validate_timeout_settings():
    """Report invalid supplied values instead of advertising clamped values as ready."""
    errors = []
    for name, (minimum, maximum) in TIMEOUT_RANGES.items():
        if name not in os.environ:
            continue
        try:
            value = float(os.environ[name])
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError()
        except (TypeError, ValueError):
            errors.append(name)
    return errors


def gateway_subscription_headers(endpoint: str) -> dict[str, str]:
    """Attach APIM credentials only to the explicitly configured gateway root."""
    from urllib.parse import urlsplit, unquote
    base = os.getenv('DEPO_API_GATEWAY_URL', '').rstrip('/')
    key = os.getenv('DEPO_APIM_SUBSCRIPTION_KEY', '').strip()
    if not base or not key:
        return {}
    try:
        target, configured = urlsplit(endpoint), urlsplit(base)
        def origin(url):
            return url.scheme.lower(), (url.hostname or '').lower(), url.port or (443 if url.scheme.lower() == 'https' else 80)
        if target.scheme not in {'http', 'https'} or target.username or target.password or origin(target) != origin(configured):
            return {}
    except ValueError:
        return {}
    # HTTP clients/proxies normalize dot segments; reject traversal before
    # attaching credentials, including encoded separators and dot segments.
    decoded = unquote(target.path)
    if '\\' in decoded or any(part in {'.', '..'} for part in decoded.split('/')):
        return {}
    if decoded != configured.path and not decoded.startswith(configured.path.rstrip('/') + '/'):
        return {}
    return {'Ocp-Apim-Subscription-Key': key}


def bounded_timeout_seconds(name: str, *, default: float, minimum: float = 1.0, maximum: float = 3600.0) -> float:
    """Read an operator timeout without allowing a malformed value to break a request."""
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value) or value <= 0:
        return default
    return max(minimum, min(maximum, value))


def graph_dispatch_timeout_seconds() -> float:
    """Allow graph RDF preparation, its write transaction, and transport overhead."""
    stage = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180, maximum=3600)
    return stage + graph_write_timeout_seconds() + graph_activation_timeout_seconds() + 30


def graph_write_timeout_seconds() -> float:
    stage = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180, maximum=3600)
    return bounded_timeout_seconds('GRAPH_PUBLICATION_WRITE_TIMEOUT_SECONDS', default=stage, maximum=3600)


def graph_activation_timeout_seconds() -> float:
    stage = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180, maximum=3600)
    return bounded_timeout_seconds('GRAPH_PUBLICATION_ACTIVATION_TIMEOUT_SECONDS', default=stage, maximum=3600)


def ontology_publication_timeout_seconds() -> float:
    """Include retained-source preparation before graph dispatch, plus overhead."""
    stage = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180, maximum=3600)
    return stage + graph_dispatch_timeout_seconds() + 30


def service_request_timeout_seconds() -> float:
    return bounded_timeout_seconds('SERVICE_REQUEST_TIMEOUT_SECONDS', default=90, maximum=300)


def engineering_workflow_timeout_seconds() -> float:
    # Conversion, policy/quality/registration/lifecycle calls, publication,
    # and transport overhead share one outer deadline.
    default = min(3600, bounded_timeout_seconds('ENGINEERING_CONVERSION_TIMEOUT_SECONDS', default=180, maximum=900)
                  + 4 * service_request_timeout_seconds() + ontology_publication_timeout_seconds() + 30)
    return bounded_timeout_seconds('ENGINEERING_WORKFLOW_TIMEOUT_SECONDS', default=default, maximum=3600)


def agent_run_timeout_seconds() -> float:
    normal = bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30)
    merge = bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
    default = min(3600, max(900, normal + 60, merge + ontology_publication_timeout_seconds() + 90,
                            engineering_workflow_timeout_seconds() + 90))
    return bounded_timeout_seconds('AGENTIC_RUN_TIMEOUT_SECONDS', default=default)


def publication_job_timeout_seconds():
    default = min(86400, max(1800, 3 * ontology_publication_timeout_seconds() + 90))
    return bounded_timeout_seconds('ONTOLOGY_PUBLICATION_JOB_TIMEOUT_SECONDS', default=default, maximum=86400)


def http_timeout(seconds):
    """Shared transport phase limits; callers still enforce their overall deadline."""
    import httpx
    return httpx.Timeout(seconds, connect=min(10, seconds), pool=min(5, seconds), write=min(60, seconds))


def timeout_configuration_warnings():
    """Short explicit outer deadlines are allowed, but their consequences are visible."""
    required = max(engineering_workflow_timeout_seconds() + 30,
                   bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
                   + ontology_publication_timeout_seconds() + 30)
    warnings = []
    if agent_run_timeout_seconds() < required:
        warnings.append({'code':'workflow_budget_shorter_than_operation', 'setting':'AGENTIC_RUN_TIMEOUT_SECONDS',
                         'configured_seconds':agent_run_timeout_seconds(), 'operation_budget_seconds':required})
    if engineering_workflow_timeout_seconds() < ontology_publication_timeout_seconds():
        warnings.append({'code':'engineering_budget_shorter_than_publication', 'setting':'ENGINEERING_WORKFLOW_TIMEOUT_SECONDS'})
    return warnings


def service_bearer_headers(token_env: str, *, service_name: str, endpoint: str = '') -> dict[str, str]:
    """Return the required credential for a private service-to-service call."""
    token = os.getenv(token_env, "").strip()
    from .authorization import require_active_token
    require_active_token(token_env)
    if not token:
        raise RuntimeError(f"{token_env} is required to call {service_name}")
    return {**gateway_subscription_headers(endpoint), **operation_headers(), "Authorization": f"Bearer {token}"}


def operation_headers():
    from .operations import current_operation
    operation = current_operation()
    return {'X-DEPO-Deadline':operation.deadline_at} if operation else {}
