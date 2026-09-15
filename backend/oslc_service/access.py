"""Explicit lifecycle grants; resource identifiers are not authorization."""
import json
import os
from fastapi import HTTPException


def authorize(identity: str, kind: str, identifier: str = "*") -> None:
    try:
        grants = json.loads(os.getenv("OSLC_LIFECYCLE_READ_GRANTS", "{}"))
        allowed = grants.get(identity, [])
        if not isinstance(allowed, list):
            raise ValueError("Invalid grants")
    except (ValueError, AttributeError):
        raise HTTPException(503, "Lifecycle access policy is invalid")
    if f"{kind}:*" not in allowed and f"{kind}:{identifier}" not in allowed:
        raise HTTPException(403, "No lifecycle resource grant")
