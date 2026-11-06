from pathlib import Path


def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")


def test_graphfilter_avoids_unbounded_property_key_scans():
    source = _main_source()
    graphfilter_source = source[source.index('@app.post("/graphfilter")'):source.index('class ComparativeSearchRequest')]

    assert "any(key IN keys(n)" not in graphfilter_source
    assert "any(key IN keys(matched_rel)" not in graphfilter_source
    assert "$search_fields" in graphfilter_source
    assert "$relationship_search_fields" in graphfilter_source
    assert "GRAPH_SEARCH_PROPERTY_KEYS" in source
    assert "requirement_id" in source
    assert "part_number" in source


def test_graphfilter_multi_limits_result_set_and_uses_search_fields():
    source = _main_source()
    multi_source = source[source.index('@app.post("/graphfilter-multi")'):source.index('@app.get("/graphtraverse/{node_id}")')]

    assert "any(key IN keys(n)" not in multi_source
    assert "collect(DISTINCT n)[..250]" in multi_source
    assert "$search_fields" in multi_source
    assert "wildcard_prefix_search" in multi_source
