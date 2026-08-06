"""Shared graph-visualization cache state, independent of the API composition root."""

from __future__ import annotations

import logging
import os
import time
from typing import Any


logger = logging.getLogger(__name__)
GRAPHVIS_CACHE_TTL = 60
GRAPHVIS_CACHE_ENABLED = os.getenv("GRAPHVIS_CACHE_ENABLED", "false").lower() == "true"
graphvis_cache: dict[str, Any] = {"data": None, "ts": 0.0}


def invalidate_graphvis_cache(reason: str = "explicit invalidation") -> None:
    graphvis_cache["data"] = None
    graphvis_cache["ts"] = 0.0
    logger.info("Graph cache invalidated: %s", reason)


def get_cached_graph() -> Any | None:
    if not GRAPHVIS_CACHE_ENABLED or graphvis_cache["data"] is None:
        return None
    if time.monotonic() - graphvis_cache["ts"] >= GRAPHVIS_CACHE_TTL:
        invalidate_graphvis_cache("expired")
        return None
    return graphvis_cache["data"]


def store_cached_graph(data: Any) -> None:
    if GRAPHVIS_CACHE_ENABLED:
        graphvis_cache["data"] = data
        graphvis_cache["ts"] = time.monotonic()
