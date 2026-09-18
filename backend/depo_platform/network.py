"""Small, dependency-free networking configuration helpers."""
from __future__ import annotations

import os


def bounded_timeout_seconds(name: str, *, default: float, minimum: float = 1.0, maximum: float = 3600.0) -> float:
    """Read an operator timeout without allowing a malformed value to break a request."""
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))
