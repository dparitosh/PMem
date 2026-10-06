import ast
import math
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List
from types import SimpleNamespace
from unittest.mock import Mock, patch


class EmbeddingPipelineFailureTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('backend/Services/graph_embeddings.py').read_text(encoding='utf-8'))
        names = {'_validate_vectors', '_standalone_auth', 'run_graph_embeddings',
                 '_clean_value', '_props_sentence', 'build_node_chunk_text'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.driver = Mock()
        self.write = Mock()
        self.scope = dict(math=math, os=os, List=List, Dict=Dict, Any=Any, BATCH_SIZE=20,
                          EMBEDDING_VECTOR_DIMENSIONS=2, EMBEDDER_AVAILABLE=True,
                          CENTRALIZED_CONFIG_AVAILABLE=True, NEO4J_URI='bolt://localhost:7687',
                          NEO4J_USER=None, NEO4J_PASS=None, NEO4J_DATABASE='neo4j',
                          logger=Mock(), get_driver=Mock(return_value=self.driver),
                          fetch_graph_nodes=Mock(return_value=[dict(eid='1', labels=[], props={}, rels=[])]),
                          build_node_chunk_text=Mock(return_value='source'), _token_count=lambda text: 1,
                          _embed_batch=Mock(return_value=[[0.1, 0.2]]), upsert_chunks=self.write,
                          ensure_indexes=Mock(), time=Mock())
        self.scope.update(MAX_RELS_PER_CHUNK=40, MAX_TOKENS_PER_CHUNK=512,
                          EMBEDDING_PROPERTY='embedding',
                          _encoding=SimpleNamespace(encode=lambda text: list(text),
                                                    decode=lambda tokens: ''.join(tokens)))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'embedding-pipeline', 'exec'), self.scope)

    def test_failed_or_malformed_provider_batches_never_write(self):
        for output in (None, [], [[0.0, 0.0]], [[1.0]], [[1.0, float('nan')]], [[True, 1.0]],
                       [['bad', 1.0]], [[1.0, float('inf')]], [[1.0, 2.0], [3.0, 4.0]]):
            with self.subTest(output=output):
                self.scope['_embed_batch'].return_value = output
                with self.assertRaises(RuntimeError):
                    self.scope['run_graph_embeddings'](force_rebuild=True)
                self.write.assert_not_called()

    def test_unavailable_model_and_invalid_batch_size_fail(self):
        self.scope['EMBEDDER_AVAILABLE'] = False
        with self.assertRaises(RuntimeError):
            self.scope['run_graph_embeddings']()
        for size in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.scope['run_graph_embeddings'](batch_size=size)
        self.scope['get_driver'].assert_not_called()

    def test_central_no_auth_driver_is_accepted(self):
        self.scope['run_graph_embeddings'](force_rebuild=True)
        self.write.assert_called_once()
        self.assertEqual(self.write.call_args.args[1][0]['embedding'], [0.1, 0.2])
        self.driver.close.assert_not_called()

    def test_pipeline_calls_real_chunk_builder_and_enforces_token_budget(self):
        self.scope['_token_count'] = lambda text: len(text)
        self.scope['fetch_graph_nodes'].return_value[0]['props'] = {'description': 'x' * 1000}
        self.scope['run_graph_embeddings'](force_rebuild=True)
        text = self.write.call_args.args[1][0]['content']
        self.assertLessEqual(len(text), 512)

    def test_standalone_no_auth_and_authenticated_configuration(self):
        with patch.dict(os.environ, {'NEO4J_AUTH_MODE': 'none'}, clear=True):
            self.assertIsNone(self.scope['_standalone_auth']())
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                self.scope['_standalone_auth']()
            self.scope.update(NEO4J_USER='user', NEO4J_PASS='fixture')
            self.assertEqual(self.scope['_standalone_auth'](), ('user', 'fixture'))


if __name__ == '__main__':
    unittest.main()
