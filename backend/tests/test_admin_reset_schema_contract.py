import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock
from backend.depo_platform.neo4j_setup import REQUIRED_CONSTRAINTS


class ResetSchemaTests(TestCase):
    def test_recreated_schema_includes_all_release_constraints(self):
        tree = ast.parse(Path('backend/Services/neo4j_schema_cleaner.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Neo4jSchemaCleaner')
        fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'create_indexes')
        namespace = {'Tuple': __import__('typing').Tuple, 'logger': MagicMock()}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), '<actual schema recreation>', 'exec'), namespace)
        driver = MagicMock()
        result = namespace['create_indexes'](SimpleNamespace(driver=driver, database='ontology'))
        self.assertTrue(result[0])
        statements = [call.args[0] for call in driver.session.return_value.__enter__.return_value.run.call_args_list]
        for constraint in REQUIRED_CONSTRAINTS:
            self.assertTrue(any(f'CREATE CONSTRAINT {constraint} ' in statement for statement in statements))
        driver.session.assert_called_once_with(database='ontology')


if __name__ == '__main__':
    main()
