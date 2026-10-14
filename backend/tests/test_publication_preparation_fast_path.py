import ast
import io
import pickle
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest


class BNode: pass


class PreparationTests(unittest.TestCase):
    def test_retained_turtle_avoids_conversion_but_other_syntax_is_converted(self):
        from backend.depo_platform import rdf_preparation
        content = b'large retained Turtle'
        with patch.object(rdf_preparation, 'prepare_rdf', return_value=b'converted') as convert:
            self.assertIs(rdf_preparation.prepare_publication_turtle(content, 'turtle'), content)
            convert.assert_not_called()
            self.assertEqual(rdf_preparation.prepare_publication_turtle(content, 'xml'), b'converted')
            convert.assert_called_once_with(content, 'xml')

    def test_only_blank_node_graphs_are_canonicalized(self):
        tree = ast.parse(Path('backend/depo_platform/rdf_preparation.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        for blank in (False, True):
            triples = [(BNode() if blank else 'urn:a', 'urn:p', 'urn:b')]
            graph = SimpleNamespace(parse=lambda **kw: triples)
            canonicalize = Mock(side_effect=lambda value: value)
            output = io.BytesIO()
            scope = {'pickle':pickle, 'sys':SimpleNamespace(
                stdin=SimpleNamespace(buffer=io.BytesIO(pickle.dumps((b'ttl','turtle',True)))),
                stdout=SimpleNamespace(buffer=output))}
            with patch.dict('sys.modules', {
                'rdflib':SimpleNamespace(Graph=lambda:graph, BNode=BNode),
                'rdflib.compare':SimpleNamespace(to_canonical_graph=canonicalize)}):
                exec(compile(ast.Module(body=[main],type_ignores=[]),'<preparation>','exec'),scope)
                scope['main']()
            self.assertEqual(canonicalize.call_count, int(blank))
            self.assertEqual(len(pickle.loads(output.getvalue())),1)

    def test_retired_merge_has_no_mutation_or_index_creation(self):
        tree = ast.parse(Path('backend/Services/unified_import_router.py').read_text(encoding='utf-8'))
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == 'merge_ontologies')
        text = ast.unparse(method)
        self.assertNotIn('MERGED_INTO',text)
        self.assertNotIn('ensure_indexes',text)
        self.assertNotIn('update_metadata',text)
        self.assertIn('HTTPException(409',text)
