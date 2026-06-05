"""
🔒 MEDIUM PRIORITY: Webhook signature validation
Ensures webhook requests come from authorized sources
Prevents webhook injection attacks
"""

import hmac
import hashlib
import json
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Webhook configuration
WEBHOOK_SECRETS = {}  # { "webhook_name": "secret_key" }
WEBHOOK_MAX_TIMESTAMP_DELTA = 300  # 5 minutes - reject if timestamp is older

def load_webhook_secrets(secrets_dict: Dict[str, str]) -> None:
    """
    Load webhook secrets from configuration
    Example: {'neo4j_events': 'secret123', 'external_service': 'secret456'}
    """
    global WEBHOOK_SECRETS
    WEBHOOK_SECRETS = secrets_dict
    logger.info(f"Loaded {len(WEBHOOK_SECRETS)} webhook secrets")


def compute_signature(payload: bytes, secret: str, algorithm: str = 'sha256') -> str:
    """
    Compute HMAC signature for webhook payload
    
    Args:
        payload: Raw request body bytes
        secret: Webhook secret key
        algorithm: Hash algorithm ('sha256', 'sha1', etc.)
    
    Returns:
        Hex-encoded HMAC signature
    
    Example:
        signature = compute_signature(body, webhook_secret)
        # Returns: 'abcdef123456...'
    """
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    
    return hmac.new(
        secret,
        payload,
        getattr(hashlib, algorithm)
    ).hexdigest()


def verify_signature(
    payload: bytes,
    received_signature: str,
    secret: str,
    algorithm: str = 'sha256',
    header_prefix: str = 'sha256='
) -> bool:
    """
    Verify webhook signature using constant-time comparison
    
    Args:
        payload: Raw request body bytes
        received_signature: Signature from webhook header (e.g., 'sha256=abc123...')
        secret: Webhook secret key
        algorithm: Hash algorithm (must match signature header)
        header_prefix: Prefix in signature header (e.g., 'sha256=', 'v1=')
    
    Returns:
        True if signature is valid, False otherwise
    
    Example:
        is_valid = verify_signature(
            body,
            signature_from_header,
            webhook_secret
        )
    """
    if not received_signature:
        logger.warning("Webhook rejected: missing signature")
        return False
    
    try:
        # Extract signature value (remove prefix if present)
        if header_prefix in received_signature:
            _, sig_value = received_signature.split(header_prefix, 1)
        else:
            sig_value = received_signature
        
        # Compute expected signature
        expected_signature = compute_signature(payload, secret, algorithm)
        
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(sig_value, expected_signature)
    
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


def validate_webhook_timestamp(timestamp: Optional[int], max_delta: int = WEBHOOK_MAX_TIMESTAMP_DELTA) -> bool:
    """
    Validate webhook timestamp to prevent replay attacks
    
    Args:
        timestamp: Unix timestamp from webhook header (seconds)
        max_delta: Maximum age in seconds (default 5 minutes)
    
    Returns:
        True if timestamp is recent enough, False if too old
    
    Example:
        if not validate_webhook_timestamp(received_timestamp):
            raise HTTPException(400, "Webhook timestamp too old (replay attack?)")
    """
    if timestamp is None:
        logger.warning("Webhook rejected: missing timestamp")
        return False
    
    import time
    current_time = int(time.time())
    time_delta = abs(current_time - timestamp)
    
    if time_delta > max_delta:
        logger.warning(f"Webhook rejected: timestamp too old ({time_delta}s > {max_delta}s)")
        return False
    
    return True


class WebhookValidator:
    """
    Complete webhook validation helper
    Handles signature verification, timestamp validation, and request parsing
    """
    
    def __init__(self, webhook_name: str, secret: str):
        """
        Initialize validator for a specific webhook
        
        Args:
            webhook_name: Name of the webhook (for logging)
            secret: Webhook secret key
        """
        self.webhook_name = webhook_name
        self.secret = secret
    
    def validate_request(
        self,
        payload: bytes,
        signature_header: str,
        timestamp_header: Optional[str] = None,
        check_timestamp: bool = True
    ) -> tuple[bool, Optional[str]]:
        """
        Validate complete webhook request
        
        Args:
            payload: Raw request body
            signature_header: Value of signature header
            timestamp_header: Value of timestamp header (optional)
            check_timestamp: Whether to validate timestamp
        
        Returns:
            (is_valid, error_message)
        
        Example:
            is_valid, error = validator.validate_request(body, header_sig, header_ts)
            if not is_valid:
                raise HTTPException(401, f"Webhook validation failed: {error}")
        """
        # Validate signature
        if not verify_signature(payload, signature_header, self.secret):
            msg = f"{self.webhook_name}: Invalid signature"
            logger.warning(msg)
            return False, msg
        
        # Validate timestamp if enabled
        if check_timestamp and timestamp_header:
            try:
                timestamp = int(timestamp_header)
            except (ValueError, TypeError):
                msg = f"{self.webhook_name}: Invalid timestamp format"
                logger.warning(msg)
                return False, msg
            
            if not validate_webhook_timestamp(timestamp):
                msg = f"{self.webhook_name}: Timestamp too old (possible replay attack)"
                logger.warning(msg)
                return False, msg
        
        logger.info(f"Webhook validated: {self.webhook_name}")
        return True, None
    
    def validate_and_parse_json(
        self,
        payload: bytes,
        signature_header: str,
        timestamp_header: Optional[str] = None
    ) -> tuple[bool, Optional[Dict], Optional[str]]:
        """
        Validate webhook and parse JSON payload in one step
        
        Args:
            payload: Raw request body
            signature_header: Value of signature header
            timestamp_header: Value of timestamp header
        
        Returns:
            (is_valid, parsed_data, error_message)
        
        Example:
            is_valid, data, error = validator.validate_and_parse_json(
                body,
                request.headers.get('X-Webhook-Signature')
            )
            if not is_valid:
                raise HTTPException(401, error)
            # Use data
        """
        # Validate signature and timestamp
        is_valid, error = self.validate_request(
            payload, 
            signature_header,
            timestamp_header,
            check_timestamp=True
        )
        
        if not is_valid:
            return False, None, error
        
        # Parse JSON
        try:
            data = json.loads(payload)
            return True, data, None
        except json.JSONDecodeError as e:
            msg = f"{self.webhook_name}: Invalid JSON: {str(e)}"
            logger.error(msg)
            return False, None, msg


# ─────────────────────────────────────────────────────────────────
# FastAPI Integration Examples
# ─────────────────────────────────────────────────────────────────

def webhook_signature_required(webhook_name: str):
    """
    FastAPI decorator for webhook endpoints with signature validation
    
    Usage:
        @app.post("/webhooks/neo4j")
        @webhook_signature_required("neo4j_events")
        async def handle_neo4j_webhook(request: Request):
            data = request.state.webhook_data
            # Handle webhook
    
    In request headers:
        X-Webhook-Signature: sha256=abc123...
        X-Webhook-Timestamp: 1234567890
    """
    from functools import wraps
    from fastapi import Request, HTTPException
    
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get webhook secret
            if webhook_name not in WEBHOOK_SECRETS:
                logger.error(f"Webhook secret not configured: {webhook_name}")
                raise HTTPException(500, "Webhook not configured")
            
            secret = WEBHOOK_SECRETS[webhook_name]
            
            # Read request body
            body = await request.body()
            
            # Get headers
            signature_header = request.headers.get("X-Webhook-Signature", "")
            timestamp_header = request.headers.get("X-Webhook-Timestamp", "")
            
            # Validate
            validator = WebhookValidator(webhook_name, secret)
            is_valid, data, error = validator.validate_and_parse_json(
                body,
                signature_header,
                timestamp_header
            )
            
            if not is_valid:
                raise HTTPException(401, f"Webhook validation failed: {error}")
            
            # Store parsed data in request state for handler access
            request.state.webhook_data = data
            
            # Call handler
            return await func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator
