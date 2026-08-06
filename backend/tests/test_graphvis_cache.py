from backend.core.graphvis_cache import (
    get_cached_graph,
    graphvis_cache,
    invalidate_graphvis_cache,
    store_cached_graph,
)


def test_graphvis_cache_invalidation_clears_shared_state(monkeypatch):
    monkeypatch.setattr("backend.core.graphvis_cache.GRAPHVIS_CACHE_ENABLED", True)
    store_cached_graph({"results": [1]})
    assert get_cached_graph() == {"results": [1]}

    invalidate_graphvis_cache("test")

    assert graphvis_cache == {"data": None, "ts": 0.0}
