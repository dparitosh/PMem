"""Shared graph-visualization cache state, independent of the API composition root."""

from __future__ import annotations

import logging
import os
import time
import threading
import copy
from typing import Any


logger = logging.getLogger(__name__)
from backend.depo_platform.network import bounded_timeout_seconds
GRAPHVIS_CACHE_TTL = bounded_timeout_seconds('GRAPHVIS_CACHE_TTL_SECONDS', default=60, maximum=3600)
_lock = threading.RLock()
GRAPHVIS_CACHE_ENABLED = os.getenv("GRAPHVIS_CACHE_ENABLED", "false").lower() == "true"
graphvis_cache: dict[str, Any] = {"data": None, "ts": 0.0, "generation": None}


def invalidate_graphvis_cache(reason: str = "explicit invalidation") -> None:
    with _lock:
        graphvis_cache.update(data=None, ts=0.0, generation=None)
    logger.info("Graph cache invalidated: %s", reason)


def get_cached_graph() -> Any | None:
    if not GRAPHVIS_CACHE_ENABLED or graphvis_cache["data"] is None:
        return None
    from backend.depo_platform.maintenance import cache_generation
    generation = cache_generation()
    with _lock:
        if generation is None or generation != graphvis_cache.get('generation'):
            invalidate_graphvis_cache('shared maintenance invalidation')
            return None
        if time.monotonic() - graphvis_cache["ts"] >= GRAPHVIS_CACHE_TTL:
            invalidate_graphvis_cache("expired")
            return None
        return copy.deepcopy(graphvis_cache["data"])


def store_cached_graph(data: Any) -> None:
    if GRAPHVIS_CACHE_ENABLED:
        from backend.depo_platform.maintenance import cache_generation
        generation = cache_generation()
        with _lock:
            graphvis_cache.update(generation=generation, data=copy.deepcopy(data), ts=time.monotonic())
