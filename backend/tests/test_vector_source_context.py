import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import Mock


class Document:
    def __init__(self, page_content='', metadata=None):
        self.page_content = page_content
        self.metadata = metadata or {}


class VectorSourceContextTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('backend/chains/vector.py').read_text(encoding='utf-8'))
        names = {'_match_docs_by_labels', 'format_graph_context', 'deep_vector_search', '_require_general_chain'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.scope = dict(List=List, Dict=Dict, Any=Any, Optional=Optional, Document=Document,
                          logger=Mock(), graph=SimpleNamespace(query=Mock(return_value=[])),
                          general_retrieval_chain=Mock(), general_qa_chain=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'vector-context', 'exec'), self.scope)

    def test_source_labels_filter_without_graph_lookup(self):
        wanted = Document(metadata={'source_labels': ['Requirement']})
        other = Document(metadata={'source_labels': ['Part']})
        self.assertEqual(self.scope['_match_docs_by_labels']([wanted, other], ['requirement']), [wanted])
        self.scope['graph'].query.assert_not_called()

    def test_missing_identity_does_not_bypass_filter(self):
        self.assertEqual(self.scope['_match_docs_by_labels']([Document()], ['Requirement']), [])

    def test_lookup_failure_does_not_return_unfiltered_documents(self):
        self.scope['graph'].query.side_effect = RuntimeError('offline')
        with self.assertRaisesRegex(RuntimeError, 'filtering is unavailable'):
            self.scope['_match_docs_by_labels']([Document(metadata={'node_id': '1'})], ['Part'])

    def test_legacy_lookup_uses_source_labels(self):
        self.scope['graph'].query.return_value = [{'node_id': '1', 'labels': ['Part']}]
        document = Document(metadata={'node_id': '1'})
        self.assertEqual(self.scope['_match_docs_by_labels']([document], ['Part']), [document])
        query = self.scope['graph'].query.call_args.args[0]
        self.assertIn('[:EMBEDDED_FROM]->(source)', query)

    def test_deep_context_queries_source_relationships(self):
        self.scope['general_retrieval_chain'].invoke.return_value = {
            'context': [Document('source', {'node_id': '1'})]}
        self.scope['general_qa_chain'].invoke.return_value = 'answer'
        self.assertEqual(self.scope['deep_vector_search']('question')['answer'], 'answer')
        query = self.scope['graph'].query.call_args.args[0]
        self.assertIn('[:EMBEDDED_FROM]->(a)-[r]-(b)', query)
        self.assertIn('elementId(startNode(r))', query)
        self.assertIn('elementId(endNode(r))', query)
        self.assertEqual(self.scope['graph'].query.call_args.kwargs['params'], {'node_ids': ['1']})

    def test_unlabelled_sources_format_safely(self):
        context = self.scope['format_graph_context']([], [{'rel': {
            'type': 'LINK', 'properties': {}, 'source': {'labels': []}, 'target': {'labels': []}}}])
        self.assertIn('Node', context)


if __name__ == '__main__':
    unittest.main()
