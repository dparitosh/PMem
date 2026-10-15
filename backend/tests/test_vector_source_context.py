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
        names = {'format_graph_context', 'deep_vector_search', '_require_general_chain', '_answer', '_retrieve_scoped'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.scope = dict(List=List, Dict=Dict, Any=Any, Optional=Optional, Document=Document,
                          logger=Mock(), graph=SimpleNamespace(query=Mock(return_value=[])),
                          general_retrieval_chain=Mock(), general_retriever=Mock(), general_qa_chain=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'vector-context', 'exec'), self.scope)





    def test_deep_context_queries_source_relationships(self):
        self.scope['general_retriever'].invoke.return_value = [Document('source', {'node_id': '1'})]
        self.scope['general_qa_chain'].invoke.return_value = 'answer'
        self.assertEqual(self.scope['deep_vector_search']('question')['answer'], 'answer')
        query = self.scope['graph'].query.call_args.args[0]
        self.assertIn('[:EMBEDDED_FROM]->(a)-[r]-(b)', query)
        self.assertIn('elementId(startNode(r))', query)
        self.assertIn('elementId(endNode(r))', query)
        self.assertEqual(self.scope['graph'].query.call_args.kwargs['params'], {'node_ids': ['1']})
        self.scope['general_retrieval_chain'].invoke.assert_not_called()
        self.scope['general_qa_chain'].invoke.assert_called_once()
        self.assertIn('LIMIT 200',query)

    def test_empty_retrieval_never_generates(self):
        vector=Mock()
        vector.as_retriever.return_value.invoke.return_value=[]
        qa=Mock()
        result=self.scope['_answer'](vector,qa,'question',None,5)
        self.assertFalse(result['answerable'])
        qa.invoke.assert_not_called()

    def test_label_filter_precedes_similarity_ranking(self):
        vector=Mock()
        self.scope.update(general_vector=vector,embeddings=SimpleNamespace(embed_query=lambda _: [.1,.2]))
        self.scope['graph'].query.return_value=[]
        self.scope['_retrieve_scoped'](vector,'question',['Part'],5)
        query=self.scope['graph'].query.call_args.args[0]
        self.assertLess(query.index('toLower(label) IN $labels'),query.index('ORDER BY score'))
        self.assertEqual(self.scope['graph'].query.call_args.kwargs['params']['labels'],['part'])

    def test_unlabelled_sources_format_safely(self):
        context = self.scope['format_graph_context']([], [{'rel': {
            'type': 'LINK', 'properties': {}, 'source': {'labels': []}, 'target': {'labels': []}}}])
        self.assertIn('Node', context)


if __name__ == '__main__':
    unittest.main()
