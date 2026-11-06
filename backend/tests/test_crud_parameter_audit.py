import ast
import unittest
from pathlib import Path
class CrudParameterAudit(unittest.TestCase):
    def test_cleaning_requires_real_booleans(self):
        tree = ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
        helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_boolean_field')
        class Rejected(Exception):
            def __init__(self, status_code, detail): self.status_code = status_code
        ns = {'Any': object, 'HTTPException': Rejected}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), '<boolean>', 'exec'), ns)
        self.assertFalse(ns['_boolean_field']({'deduplicate':False}, 'deduplicate', True))
        self.assertTrue(ns['_boolean_field']({}, 'deduplicate', True))
        for value in ['false', 'true', 0, 1, None, [], {}]:
            with self.assertRaises(Rejected) as caught:
                ns['_boolean_field']({'deduplicate':value}, 'deduplicate', True)
            self.assertEqual(caught.exception.status_code,422)
    def test_start_demo_flag_is_validated(self):
        script=Path('infra/deployment/invoke-depo-lifecycle.ps1').read_text(encoding='utf-8')
        start=script.split('"Start" {',1)[1].split('"InitializeDatabase"',1)[0]
        for field in ['if ($LocalInsecureDemo)', 'AUTH_MODE', 'DEPO_ALLOW_INSECURE_LOCAL_AUTH', 'DEPO_SERVICE_HOST']:
            self.assertIn(field,start)
