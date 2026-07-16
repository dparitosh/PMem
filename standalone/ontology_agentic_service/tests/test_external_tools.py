import json

import pytest

from AgentsRegistry.CodedTools import ontology_external_api_tools as tools


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size):
        return self.payload


def test_registered_ontologies_uses_configured_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured.update(url=request.full_url, method=request.method, auth=request.headers.get("Authorization"), timeout=timeout)
        return Response({"items": []})

    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_BASE_URL", "https://ontology.example/api")
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_TOKEN", "secret")
    monkeypatch.setattr(tools, "urlopen", fake_urlopen)
    assert tools.external_registered_ontologies() == {"items": []}
    assert captured == {
        "url": "https://ontology.example/api/v1/ontology/registered",
        "method": "GET",
        "auth": "Bearer secret",
        "timeout": 30.0,
    }


def test_context_search_posts_json(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["method"] = request.method
        return Response({"matches": [1]})

    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_ENABLED", "true")
    monkeypatch.setattr(tools, "urlopen", fake_urlopen)
    assert tools.external_context_graph_search("pump", "ex") == {"matches": [1]}
    assert captured == {"body": {"search": "pump", "ontology_prefix": "ex"}, "method": "POST"}


def test_external_target_and_input_are_validated(monkeypatch):
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_BASE_URL", "file:///etc/passwd")
    with pytest.raises(ValueError, match="HTTP"):
        tools.external_registered_ontologies()
    with pytest.raises(ValueError, match="search"):
        tools.external_context_graph_search("  ")


def test_external_configuration_rejects_embedded_credentials_and_bad_timeout(monkeypatch):
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_BASE_URL", "https://user:secret@ontology.example")
    with pytest.raises(ValueError, match="credentials"):
        tools.external_registered_ontologies()
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_BASE_URL", "https://ontology.example")
    monkeypatch.setenv("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS", "later")
    with pytest.raises(ValueError, match="numeric"):
        tools.external_registered_ontologies()


def test_external_api_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ONTOLOGY_EXTERNAL_API_ENABLED", raising=False)
    called = False

    def fake_urlopen(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(tools, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="disabled"):
        tools.external_registered_ontologies()
    assert called is False
