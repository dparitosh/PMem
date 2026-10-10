import ast
import io
import json
import tempfile
import typing
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.Services.reqif_source import reqif_xml, parse_reqif


class Contract:
    def normalize_entity(self, **kw):
        return kw['record']

    def normalize_relationship(self, **kw):
        return kw['record']


class ReqIFRegressions(unittest.TestCase):
    def setUp(self):
        # Isolate parser logic from unavailable service dependencies. The DTD
        # rejection tests exercise the real shared byte guard before parsing.
        self.patch = patch.dict('sys.modules', {'defusedxml': SimpleNamespace(ElementTree=ET)})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        tree = ast.parse(Path('backend/ceim/reqif_adapter.py').read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        scope = {'Any': typing.Any, 'ET': ET, 'json': json, 'CEIMContract': Contract, 'parse_reqif': parse_reqif}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<reqif adapter>', 'exec'), scope)
        self.normalize = scope['reqif_to_ceim_batch']
        tree = ast.parse(Path('backend/Services/unified_data_import.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FileParser')
        function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_parse_reqif')
        function.decorator_list = []
        scope = dict(vars(typing))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<legacy ReqIF>', 'exec'), scope)
        self.legacy = scope['_parse_reqif']

    def archive(self, files):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return output.getvalue()

    def test_archive_document_selection_and_ambiguity(self):
        document = b'<REQ-IF><SPEC-OBJECT IDENTIFIER="a"/></REQ-IF>'
        content = self.archive({'attachment.xml': '<attachment/>', 'source.reqif': document})
        self.assertEqual(reqif_xml(content), document)
        self.assertEqual(len(self.normalize(content)['entities']), 1)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            reqif_xml(self.archive({'one.reqif': document, 'two.reqif': document}))

    def test_invalid_inputs_fail_in_both_paths(self):
        documents = [b'<OTHER/>', b'<REQ-IF><SPEC-OBJECT/></REQ-IF>', b'PKbroken',
                     b'<REQ-IF><SPEC-OBJECT IDENTIFIER="a"/><SPEC-OBJECT IDENTIFIER="a"/></REQ-IF>',
                     b'<!DOCTYPE REQ-IF [<!ENTITY a "text">]><REQ-IF/>',
                     b'<REQ-IF><SPEC-OBJECT IDENTIFIER="a"/><SPEC-RELATION IDENTIFIER="r"><SOURCE><SPEC-OBJECT-REF>a</SPEC-OBJECT-REF></SOURCE><TARGET><SPEC-OBJECT-REF>missing</SPEC-OBJECT-REF></TARGET></SPEC-RELATION></REQ-IF>']
        for document in documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    self.normalize(document)
                rows, stats = self.legacy(document)
                self.assertEqual(rows, [])
                self.assertIn('error', stats)

    def test_full_text_and_nested_hierarchy_preserved(self):
        text = 'x' * 1500
        document = f'<REQ-IF><SPEC-OBJECT IDENTIFIER="a" DESC="{text}"/><SPEC-OBJECT IDENTIFIER="b"/><SPECIFICATION IDENTIFIER="s"><CHILDREN><SPEC-HIERARCHY IDENTIFIER="h1"><OBJECT><SPEC-OBJECT-REF>a</SPEC-OBJECT-REF></OBJECT><CHILDREN><SPEC-HIERARCHY IDENTIFIER="h2"><OBJECT><SPEC-OBJECT-REF>b</SPEC-OBJECT-REF></OBJECT></SPEC-HIERARCHY></CHILDREN></SPEC-HIERARCHY></CHILDREN></SPECIFICATION></REQ-IF>'.encode()
        batch = self.normalize(document)
        self.assertEqual(batch['entities'][0]['attributes']['DESC'], text)
        self.assertEqual([(r['source_id'], r['target_id']) for r in batch['relationships']], [('s', 'a'), ('a', 'b')])
        rows, stats = self.legacy(document)
        self.assertNotIn('error', stats)
        self.assertEqual(rows[0]['description'], text)
        self.assertEqual(rows[2]['hierarchy'][1]['source'], 'a')

    def test_xhtml_requirement_text_available_to_mapping(self):
        document = b'<REQ-IF><SPEC-OBJECT IDENTIFIER="a"><VALUES><ATTRIBUTE-VALUE-XHTML><THE-VALUE><div>Shall work</div></THE-VALUE></ATTRIBUTE-VALUE-XHTML></VALUES></SPEC-OBJECT></REQ-IF>'
        self.assertEqual(self.normalize(document)['entities'][0]['attributes']['DESC'], 'Shall work')


if __name__ == '__main__':
    unittest.main()
