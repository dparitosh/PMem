import ast
import re
import unittest
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, Mock


class EmbeddingWriteTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('backend/Services/graph_embeddings.py').read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if
                 (isinstance(node, ast.FunctionDef) and node.name in {'upsert_chunks', 'ensure_indexes'})
                 or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                     and target.id == 'UPSERT_CHUNK' for target in node.targets))]
        self.scope = dict(re=re, List=List, Dict=Dict, logger=Mock(), NEO4J_DATABASE='neo4j',
                          CHUNK_LABEL='GraphChunk', DATASHEET_CHUNK_LABEL='DatasheetChunk',
                          TEXT_PROPERTY='content', EMBEDDING_PROPERTY='embedding',
                          EMBEDDING_VECTOR_DIMENSIONS=2, VECTOR_INDEX_NAME='graph_embedding',
                          KEYWORD_INDEX_NAME='keyword_index', DATASHEET_VECTOR_INDEX='datasheet_index',
                          DATASHEET_KEYWORD_INDEX='datasheetkeyword')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'embedding-writes', 'exec'), self.scope)
        self.driver = MagicMock()
        self.session = self.driver.session.return_value.__enter__.return_value

    def test_missing_source_raises_inside_managed_transaction(self):
        tx = Mock()
        tx.run.return_value.single.return_value = {'written': 0}
        self.session.execute_write.side_effect = lambda callback: callback(tx)
        with self.assertRaisesRegex(RuntimeError, 'batch rolled back'):
            self.scope['upsert_chunks'](self.driver, [{'node_id': 'deleted'}])
        query = tx.run.call_args.args[0]
        self.assertLess(query.index('MATCH (src)'), query.index('MERGE (c:'))
        self.session.run.assert_not_called()

    def test_success_returns_persisted_batch_count(self):
        tx = Mock()
        tx.run.return_value.single.return_value = {'written': 1}
        self.session.execute_write.side_effect = lambda callback: callback(tx)
        self.assertEqual(self.scope['upsert_chunks'](self.driver, [{'node_id': 'source'}]), 1)

    def test_deferred_schema_error_fails_explicit_run(self):
        def run(query):
            result = Mock()
            if 'CREATE VECTOR INDEX `graph_embedding`' in query:
                result.consume.side_effect = RuntimeError('schema failure')
            return result
        self.session.run.side_effect = run
        with self.assertRaisesRegex(RuntimeError, 'GraphChunk vector index'):
            self.scope['ensure_indexes'](self.driver, strict=True)
        self.scope['ensure_indexes'](self.driver)

    def test_invalid_index_identifier_never_reaches_database(self):
        self.scope['VECTOR_INDEX_NAME'] = 'invalid`index'
        with self.assertRaises(ValueError):
            self.scope['ensure_indexes'](self.driver)
        self.driver.session.assert_not_called()

    def test_existing_vector_dimension_mismatch_blocks_run(self):
        indexes = [
            {'name': 'graph_embedding', 'type': 'VECTOR', 'labelsOrTypes': ['GraphChunk'],
             'properties': ['embedding'], 'options': {'indexConfig': {
                 'vector.dimensions': 3, 'vector.similarity_function': 'cosine'}}},
            {'name': 'keyword_index', 'type': 'FULLTEXT', 'labelsOrTypes': ['GraphChunk'],
             'properties': ['content'], 'options': {}},
        ]
        self.session.run.return_value.data.return_value = indexes
        with self.assertRaisesRegex(RuntimeError, 'configuration mismatch'):
            self.scope['ensure_indexes'](self.driver, strict=True)
        indexes[0]['options']['indexConfig']['vector.dimensions'] = 2
        self.scope['ensure_indexes'](self.driver, strict=True)


if __name__ == '__main__':
    unittest.main()
