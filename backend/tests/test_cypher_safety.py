import pytest

from backend.core.cypher_safety import UnsafeCypherError, assert_read_only_cypher


@pytest.mark.parametrize("query", [
    "CREATE (n)",
    "MATCH (n) SET n.name = 'x' RETURN n",
    "MATCH (n) DETACH DELETE n",
    "MERGE (n:Thing {id: 1}) RETURN n",
    "CALL apoc.create.node(['Thing'], {})",
    "MATCH (n) RETURN n; MATCH (m) DELETE m",
])
def test_generated_cypher_rejects_writes_and_procedures(query):
    with pytest.raises(UnsafeCypherError):
        assert_read_only_cypher(query)


def test_generated_cypher_accepts_parameterized_read_query():
    query = "MATCH (n:Product) WHERE n.name = $name RETURN n LIMIT 10"
    assert assert_read_only_cypher(query) == query


def test_write_keywords_inside_string_literals_do_not_trigger_guard():
    query = "MATCH (n) WHERE n.name = 'CREATE SET DELETE' RETURN n"
    assert assert_read_only_cypher(query) == query


@pytest.mark.parametrize('literal',["'https://example.test'", "'/* comment marker'", '"https://example.test"', "'escaped \\' // marker'"])
def test_quoted_comment_markers_cannot_hide_a_later_mutation(literal):
    with pytest.raises(UnsafeCypherError):
        assert_read_only_cypher(f'MATCH (n) WITH n, {literal} AS text DELETE n RETURN text')


def test_urls_and_quoted_identifiers_remain_valid_read_data():
    query="MATCH (n) WHERE n.`DELETE` = 'https://example.test' RETURN n /* normal comment */"
    assert assert_read_only_cypher(query)==query
    with pytest.raises(UnsafeCypherError):
        assert_read_only_cypher('MATCH (n) // comment\rDELETE n RETURN n')


@pytest.mark.parametrize('query',["RETURN 'unterminated",'RETURN 1 /* unterminated'])
def test_malformed_literals_and_comments_fail_closed(query):
    with pytest.raises(UnsafeCypherError):assert_read_only_cypher(query)
