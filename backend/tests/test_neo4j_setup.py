import pytest

from backend.depo_platform import neo4j_setup


def test_publication_schema_contains_only_idempotent_statements():
    statements = neo4j_setup._statements(neo4j_setup.SCHEMA_FILE.read_text(encoding="utf-8"))
    assert len(statements) == 4
    assert all("IF NOT EXISTS" in statement for statement in statements[:3])
    assert "depo_bridge_publication_id" in statements[2]
    assert statements[-1] == "CALL db.awaitIndexes(60)"
    assert not any(token in statement.upper() for statement in statements for token in (" DELETE ", " DETACH ", " DROP "))


def test_no_auth_mode_is_supported(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH_MODE", "none")
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)
    assert neo4j_setup._auth() is None


def test_token_auth_requires_both_credential_parts(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH_MODE", "token")
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="credentials"):
        neo4j_setup._auth()


def test_schema_parser_ignores_comments_and_empty_fragments():
    assert neo4j_setup._statements("// comment\nRETURN 1;\n;\n// ignored\nRETURN 2;") == ["RETURN 1", "RETURN 2"]
