import ast
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from types import SimpleNamespace
import unittest


class NamespaceVersionTests(unittest.TestCase):
    def test_namespace_prevents_prefix_collision_and_allows_prefix_change(self):
        tree = ast.parse(Path('backend/Services/ontology_upload_manager.py').read_text(encoding='utf-8'))
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == '_find_existing')
        fn.decorator_list = []
        scope = dict(Optional=Optional, Dict=Dict, Any=Any, logger=logging.getLogger('versions'))
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<versions>', 'exec'), scope)
        records = [dict(ontology_id='old', prefix='oldprefix', file_type='xsd', generation_type='owl', namespace='urn:example:one', original_filename='one.xsd',version=1),
                   dict(ontology_id='other',prefix='newprefix',file_type='xsd',generation_type='owl',namespace='urn:example:two',original_filename='two.xsd',version=2)]
        store = SimpleNamespace(list_ontologies=lambda: {'status':'success','ontologies':records})
        find = scope[fn.name]
        self.assertEqual(find(store,'newprefix','xsd','owl',source_namespace='urn:example:one',source_filename='one.xsd')['ontology_id'],'old')
        self.assertIsNone(find(store,'newprefix','xsd','owl',source_namespace='urn:new',source_filename='one.xsd'))
        self.assertIsNone(find(store,'newprefix','xsd','owl',source_namespace='',source_filename='unknown.xsd'))


if __name__ == '__main__':
    unittest.main()
