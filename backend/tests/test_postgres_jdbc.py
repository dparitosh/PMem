from pathlib import Path

import pytest

from backend.data_pipeline_service import postgres_jdbc


def _configure(monkeypatch, tmp_path: Path, dsn: str) -> Path:
    jar = tmp_path / "postgresql-42.7.13.jar"
    jar.write_bytes(b"test")
    monkeypatch.setenv("DEPO_DATABASE_URL", dsn)
    monkeypatch.setenv("DEPO_SPARK_POSTGRES_DRIVER_JAR", str(jar.resolve()))
    return jar


def test_configuration_builds_credential_free_jdbc_url(monkeypatch, tmp_path):
    jar = _configure(
        monkeypatch,
        tmp_path,
        "postgresql://depo_user:p%40ss%2Fword@db.internal:5433/depo?sslmode=disable",
    )
    config = postgres_jdbc.configuration()
    assert config["url"] == "jdbc:postgresql://db.internal:5433/depo?sslmode=disable"
    assert config["user"] == "depo_user"
    assert config["password"] == "p@ss/word"
    assert config["driver"] == "org.postgresql.Driver"
    assert config["driver_jar"] == str(jar.resolve())
    assert "p%40ss" not in config["url"]


def test_configuration_supports_ipv6_and_default_port(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, "postgresql://depo:secret@[2001:db8::10]/depo")
    assert postgres_jdbc.configuration()["url"] == "jdbc:postgresql://[2001:db8::10]:5432/depo"


@pytest.mark.parametrize(
    "dsn, message",
    [
        ("postgresql://depo:secret@db.internal:not-a-port/depo", "invalid PostgreSQL port"),
        ("postgresql://depo:secret@db.internal/depo#fragment", "must not contain a URL fragment"),
        ("postgresql://depo:secret@db.internal/depo?password=secret", "not query parameters"),
    ],
)
def test_configuration_rejects_unsafe_or_invalid_urls(monkeypatch, tmp_path, dsn, message):
    _configure(monkeypatch, tmp_path, dsn)
    with pytest.raises(postgres_jdbc.PostgresJdbcConfigurationError, match=message):
        postgres_jdbc.configuration()


def test_read_probe_uses_a_bounded_query(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, "postgresql://depo:secret@db.internal/depo")

    class Reader:
        def __init__(self):
            self.options = {}

        def format(self, value):
            assert value == "jdbc"
            return self

        def option(self, key, value):
            self.options[key] = value
            return self

        def load(self):
            return self

        def first(self):
            return {"connectivity_check": 1}

    class Spark:
        read = Reader()

    assert postgres_jdbc.read_probe(Spark()) == 1
    assert Spark.read.options["query"] == "SELECT 1 AS connectivity_check"
