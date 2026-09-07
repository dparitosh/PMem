import json
from unittest.mock import MagicMock, patch

from backend.graph_service.neo4j_publisher import Neo4jPublisher


def test_publication_preserves_typed_and_language_literals_as_supported_properties():
    publisher = Neo4jPublisher()
    publisher.password = "test"
    driver = MagicMock()
    session = driver.__enter__.return_value.session.return_value.__enter__.return_value
    tx = MagicMock()
    session.execute_write.side_effect = lambda operation: operation(tx)
    with patch("backend.graph_service.neo4j_publisher.GraphDatabase.driver", return_value=driver):
        publisher.publish_turtle(
            content=b'@prefix ex: <urn:test:> . ex:part ex:mass 42; ex:description "Rotor"@en .',
            ontology_id="test", prefix="ex",
        )
    session.execute_write.assert_called_once()
    session.run.assert_not_called()
    rows = tx.run.call_args_list[0].kwargs["rows"]
    properties = json.loads(next(row["rdf_properties"] for row in rows if row["iri"] == "urn:test:part"))
    assert properties["urn:test:mass"][0] == {"value": "42", "datatype": "http://www.w3.org/2001/XMLSchema#integer", "language": None}
    assert properties["urn:test:description"][0]["language"] == "en"
