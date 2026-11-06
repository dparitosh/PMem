from unittest.mock import MagicMock

import pytest

from backend.core import db_config, graph as graph_module


def _config(database="customer-db"):
    return db_config.Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="secret",
        database=database,
        deployment_type=db_config.Neo4jDeploymentType.ON_PREMISES,
        encrypted=False,
    )


def test_invalid_reconnection_cooldown_uses_default(monkeypatch, caplog):
    monkeypatch.setenv("NEO4J_RECONNECTION_COOLDOWN", "not-a-number")

    assert db_config._float_environment("NEO4J_RECONNECTION_COOLDOWN", 60.0) == 60.0
    assert "Ignoring invalid NEO4J_RECONNECTION_COOLDOWN" in caplog.text


def test_driver_kwargs_keep_sandbox_tls_policy_explicit():
    config = _config()
    config.encrypted = True
    config.tls_verify = False

    options = db_config._driver_kwargs(config)

    assert options["encrypted"] is True
    assert isinstance(options["trusted_certificates"], db_config.TrustAll)


def test_driver_database_is_selected_on_session_not_driver(monkeypatch):
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = MagicMock()
    factory = MagicMock(return_value=driver)
    monkeypatch.setattr(db_config, "get_config", lambda: _config())
    monkeypatch.setattr(db_config.GraphDatabase, "driver", factory)

    pool = object.__new__(db_config.Neo4jDriverPool)
    pool._driver = None
    pool._last_connection_error_time = 0
    created = pool._create_driver()

    assert created is driver
    assert "database" not in factory.call_args.kwargs
    driver.session.assert_called_with(database="customer-db")


def test_connection_uses_configured_default_database(monkeypatch):
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value = session
    monkeypatch.setattr(db_config, "get_driver", lambda: driver)
    monkeypatch.setattr(db_config, "get_config", lambda: _config("configured-db"))

    with db_config.Neo4jConnection() as opened:
        assert opened is session

    driver.session.assert_called_once_with(database="configured-db")
    session.close.assert_called_once()


def test_graph_proxy_routes_queries_through_timeout_gateway(monkeypatch):
    gateway = MagicMock(return_value=[{"ok": 1}])
    monkeypatch.setattr(graph_module, "query_with_timeout", gateway)

    result = graph_module.GraphProxy().query("RETURN $value AS ok", {"value": 1}, timeout=7)

    assert result == [{"ok": 1}]
    gateway.assert_called_once_with(
        "RETURN $value AS ok", params={"value": 1}, timeout=7
    )


def test_empty_schema_cache_uses_short_recovery_ttl(monkeypatch):
    monkeypatch.setattr(graph_module, "_schema_cache", {
        "nodeLabels": {}, "relationshipTypes": {}, "displayKeys": {}
    })
    monkeypatch.setattr(
        graph_module, "_schema_cache_ts",
        graph_module.time.time() - graph_module._EMPTY_SCHEMA_CACHE_TTL - 1,
    )
    rows = [[{
        "nodeType": ":`OntologyClass`",
        "properties": [{"name": "name", "types": ["STRING"]}],
    }], []]
    gateway = MagicMock(side_effect=rows)
    monkeypatch.setattr(graph_module, "query_with_timeout", gateway)

    schema = graph_module.get_graph_schema()

    assert schema["nodeLabels"] == {"OntologyClass": ["name"]}
    assert schema["displayKeys"] == {"OntologyClass": "name"}


def test_read_only_guard_rejects_write_hidden_after_read_clause():
    from backend.core.cypher_safety import UnsafeCypherError, assert_read_only_cypher

    with pytest.raises(UnsafeCypherError):
        assert_read_only_cypher("MATCH (n) WITH n DELETE n")


def test_sandbox_mode_disables_tls_by_default_but_remains_overridable(monkeypatch):
    monkeypatch.setattr(db_config, "_load_environment", lambda: None)
    for key in ("NEO4J_ENCRYPTED", "NEO4J_TLS_VERIFY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASS", "secret")
    monkeypatch.setenv("SANDBOX_MODE", "true")
    db_config.get_config.cache_clear()

    sandbox = db_config.get_config()
    assert sandbox.encrypted is False
    assert sandbox.tls_verify is False

    monkeypatch.setenv("NEO4J_ENCRYPTED", "true")
    monkeypatch.setenv("NEO4J_TLS_VERIFY", "true")
    db_config.get_config.cache_clear()
    explicit = db_config.get_config()
    assert explicit.encrypted is True
    assert explicit.tls_verify is True
    db_config.get_config.cache_clear()
