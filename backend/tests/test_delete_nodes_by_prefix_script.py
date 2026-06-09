from unittest.mock import MagicMock, patch

from backend.tests.delete_electronicassembly_componentinstance import delete_test_nodes


def test_delete_test_nodes_uses_prefix_batch_delete():
    mock_session = MagicMock()
    mock_single = MagicMock()
    mock_single.__getitem__.return_value = 42
    mock_session.run.return_value.single.return_value = mock_single

    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_session

    with patch("backend.tests.delete_electronicassembly_componentinstance.get_config") as get_config, \
         patch("backend.tests.delete_electronicassembly_componentinstance.Neo4jConnection", return_value=mock_conn):
        get_config.return_value.database = "neo4j"

        deleted = delete_test_nodes(prefix="ap242", batch_size=2500)

    assert deleted == 42
    assert mock_session.run.call_count == 2
    first_query = mock_session.run.call_args_list[0].args[0]
    second_query = mock_session.run.call_args_list[1].args[0]
    assert "coalesce(n.ontology_prefix, n.prefix) = $prefix" in first_query
    assert "IN TRANSACTIONS OF 2500 ROWS" in second_query
