from backend.depo_platform.network import bounded_timeout_seconds


def test_timeout_configuration_falls_back_for_invalid_value(monkeypatch):
    monkeypatch.setenv("GRAPH_PUBLICATION_TIMEOUT_SECONDS", "not-a-number")
    assert bounded_timeout_seconds("GRAPH_PUBLICATION_TIMEOUT_SECONDS", default=180) == 180


def test_timeout_configuration_is_bounded(monkeypatch):
    monkeypatch.setenv("GRAPH_PUBLICATION_TIMEOUT_SECONDS", "99999")
    assert bounded_timeout_seconds("GRAPH_PUBLICATION_TIMEOUT_SECONDS", default=180) == 3600
