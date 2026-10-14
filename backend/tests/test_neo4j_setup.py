import pytest

from backend.depo_platform import neo4j_setup


def constraint_rows(kind='UNIQUENESS'):
    return [{'name': name, 'type': kind, 'entityType': 'NODE',
             'labelsOrTypes': [label], 'properties': list(properties)}
            for name, (label, properties) in neo4j_setup.CONSTRAINT_DEFINITIONS.items()]


@pytest.mark.parametrize('kind', ['UNIQUENESS', 'NODE_PROPERTY_UNIQUENESS'])
def test_constraint_validation_accepts_supported_cypher_type_names(kind):
    assert neo4j_setup.verify_constraints(constraint_rows(kind)) == sorted(neo4j_setup.REQUIRED_CONSTRAINTS)


@pytest.mark.parametrize('field,value', [
    ('type', 'RELATIONSHIP_PROPERTY_UNIQUENESS'), ('type', 'NODE_KEY'),
    ('entityType', 'RELATIONSHIP'), ('labelsOrTypes', ['WrongLabel']),
    ('properties', ['wrong_property']), ('properties', ['iri', 'ontology_id']),
])
def test_constraint_validation_still_rejects_incompatible_definitions(field, value):
    rows = constraint_rows('NODE_PROPERTY_UNIQUENESS')
    rows[0][field] = value
    with pytest.raises(RuntimeError, match='Incompatible Neo4j publication constraints'):
        neo4j_setup.verify_constraints(rows)


def test_publication_schema_contains_only_idempotent_statements():
    statements = neo4j_setup._statements(neo4j_setup.SCHEMA_FILE.read_text(encoding="utf-8"))
    assert len(statements) == 7
    assert all("IF NOT EXISTS" in statement for statement in statements[:-1])
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
