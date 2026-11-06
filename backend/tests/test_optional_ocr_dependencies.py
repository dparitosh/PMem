"""Provider isolation without importing document/database service dependencies."""
import ast
import builtins
from pathlib import Path
import types
import unittest
from unittest.mock import patch


class OptionalOcrTests(unittest.TestCase):
    def test_missing_tesseract_does_not_disable_easyocr_rendering(self):
        tree = ast.parse(Path('backend/Services/document_processor.py').read_text(encoding='utf-8'))
        imports = [node for node in tree.body if isinstance(node, ast.Try)
                   and any(isinstance(item, ast.Import) and item.names[0].name in {'fitz', 'pytesseract'}
                           or isinstance(item, ast.ImportFrom) and item.module == 'PIL'
                           for item in node.body)]
        renderer = types.ModuleType('fitz')
        imaging = types.ModuleType('PIL')
        imaging.Image = object()
        original = builtins.__import__

        def load(name, *args, **kwargs):
            if name == 'pytesseract':
                raise ImportError('optional provider absent')
            if name == 'fitz':
                return renderer
            if name == 'PIL':
                return imaging
            return original(name, *args, **kwargs)

        namespace = {}
        with patch('builtins.__import__', side_effect=load):
            exec(compile(ast.Module(body=imports, type_ignores=[]), '<optional OCR imports>', 'exec'), namespace)
        self.assertIs(namespace['fitz'], renderer)
        self.assertIs(namespace['Image'], imaging.Image)
        self.assertIsNone(namespace['pytesseract'])


if __name__ == '__main__':
    unittest.main()
