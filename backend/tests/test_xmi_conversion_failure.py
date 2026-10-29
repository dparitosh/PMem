"""Isolated regression checks for the conversion/output failure boundary."""
import ast
import logging
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


def load_function(path, name, scope):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), path, 'exec'), scope)
    return scope[name]


class XmiFailureTests(unittest.TestCase):
    def test_engine_preserves_failure_and_legacy_boolean_contract(self):
        scope = dict(Path=Path, logger=logging.getLogger('xmi-test'),
                     Optional=__import__('typing').Optional, Dict=__import__('typing').Dict,
                     Namespace=object)
        convert = load_function('backend/Services/owl_xmi_engine.py', 'convert_xmi_to_ttl', scope)
        with tempfile.TemporaryDirectory() as directory:
            source = str(Path(directory) / 'missing.xmi')
            output = str(Path(directory) / 'output.ttl')
            self.assertFalse(convert(source, output))
            with self.assertRaisesRegex(ValueError, 'XMI file not found') as caught:
                convert(source, output, raise_on_error=True)
            self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
            self.assertFalse(Path(output).exists())

    def run_upload(self, converter):
        module = ModuleType('backend.Services.owl_xmi_engine')
        module.convert_xmi_to_ttl = converter
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.xmi'
            def write(content, suffix):
                source.write_bytes(content)
                return source
            scope = dict(__package__='backend.Services', Path=Path,
                         Optional=__import__('typing').Optional, Tuple=__import__('typing').Tuple,
                         Dict=__import__('typing').Dict, Any=object,
                         logger=logging.getLogger('xmi-test'), _write_tmp=write,
                         _read_and_validate=lambda path: (path.read_text(), {'valid': True}),
                         _inspect_semantics=lambda *args: {})
            upload = load_function('backend/Services/owl_generation_service.py',
                                   'generate_owl_from_xmi', scope)
            with patch.dict(sys.modules, {'backend.Services.owl_xmi_engine': module}):
                try:
                    return upload(b'<model/>', 'model.xmi')
                finally:
                    self.assertFalse(source.exists())
                    self.assertFalse(source.with_suffix('.ttl').exists())

    def test_upload_preserves_original_conversion_diagnostic(self):
        def converter(**kwargs):
            self.assertTrue(kwargs['raise_on_error'])
            raise ValueError('Unsupported model namespace')
        with self.assertRaisesRegex(ValueError, 'Unsupported model namespace'):
            self.run_upload(converter)

    def test_upload_rejects_missing_output_without_file_not_found(self):
        for result in (False, True):
            with self.assertRaisesRegex(ValueError, 'did not produce an ontology'):
                self.run_upload(lambda **kwargs: result)

    def test_success_reads_output_before_cleanup(self):
        def converter(**kwargs):
            Path(kwargs['output_path']).write_text('valid turtle', encoding='utf-8')
            return True
        text, metadata = self.run_upload(converter)
        self.assertEqual(text, 'valid turtle')
        self.assertTrue(metadata['validation']['valid'])


if __name__ == '__main__':
    unittest.main()
