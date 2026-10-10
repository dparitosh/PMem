"""Safe diagnostics for failures after SSE response headers have been sent."""

def stream_failure(exc, request_id):
    status = getattr(exc, 'status_code', None)
    category, action = (
        ('authentication_rejected', 'Reconnect in Admin and check downstream credential forwarding.') if status in (401, 403)
        else ('timed_out', 'Check service load and configured request timeouts before retrying.') if status == 504 or isinstance(exc, TimeoutError)
        else ('invalid_request', 'Review the request parameters before retrying.') if status == 422
        else ('service_unavailable', 'Inspect agentic service logs using the request or run ID.')
    )
    headers = getattr(exc, 'headers', None) or {}
    return {'error': 'Knowledge companion stream failed; no complete answer was delivered.',
            'category': category, 'action': action, 'request_id': request_id,
            'run_id': headers.get('X-DEPO-Run-ID')}
