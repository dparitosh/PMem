"""Exercise upgrade failure boundaries without a live customer database."""
import unittest
import ast
import re
from unittest.mock import MagicMock, patch

from backend.depo_platform import database_setup as setup
from backend.depo_platform import schema_contract


class SchemaUpgradeSafetyTests(unittest.TestCase):
    def test_bound_catalog_queries_have_valid_psycopg_placeholders(self):
        from pathlib import Path
        tree = ast.parse(Path(schema_contract.__file__).read_text(encoding='utf-8'))
        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != 'execute' or len(node.args) < 2:
                continue
            if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                query = node.args[0].value
                self.assertIsNone(re.search(r'%(?![%sbt])', query.replace('%%', '')), query)
                checked += 1
        self.assertGreaterEqual(checked, 7)

    def test_client_programming_error_has_action_without_leaking_message(self):
        error = type('ProgrammingError', (Exception,), {})('secret connection details')
        with patch.object(setup, '_connection_context', return_value={}):
            result = setup._failure_action(error)
        self.assertIn('client rejected', result['action'])
        self.assertNotIn('secret', str(result))

    def test_each_required_privilege_is_checked(self):
        for privileges in ((False, True, True), (True, False, True), (True, True, False)):
            with self.subTest(privileges=privileges):
                db = MagicMock()
                cursor = db.cursor.return_value.__enter__.return_value
                cursor.fetchone.return_value = privileges
                with self.assertRaisesRegex(RuntimeError, 'privileges'):
                    setup.verify_migration_privileges(db)
                self.assertEqual(cursor.execute.call_args.args[1][::2], ('CONNECT', 'USAGE', 'CREATE'))

    def test_all_required_privileges_pass(self):
        db = MagicMock()
        db.cursor.return_value.__enter__.return_value.fetchone.return_value = (True, True, True)
        setup.verify_migration_privileges(db)

    def test_final_verification_failure_reaches_transaction_rollback(self):
        driver, db = MagicMock(), MagicMock()
        driver.connect.return_value.__enter__.return_value = db
        with patch.dict('sys.modules', {'psycopg': driver}), patch.dict('os.environ', {'DEPO_DATABASE_URL': 'postgresql://fixture'}), \
                patch.object(setup, 'initialise_schema'), patch.object(setup, 'verify_migration_privileges'), \
                patch.object(setup, 'apply_migrations') as migrate, \
                patch('backend.depo_platform.credentials.bootstrap_environment') as bootstrap, \
                patch.object(setup, 'verify_schema', side_effect=RuntimeError('schema incompatible')):
            with self.assertRaisesRegex(RuntimeError, 'schema incompatible'):
                setup.setup_database()
            migrate.assert_called_once_with(db)
            bootstrap.assert_called_once_with(db)
            self.assertIs(db.transaction.return_value.__exit__.call_args.args[0], RuntimeError)

    def test_check_only_does_not_migrate_or_bootstrap(self):
        driver, db = MagicMock(), MagicMock()
        driver.connect.return_value.__enter__.return_value = db
        with patch.dict('sys.modules', {'psycopg': driver}), patch.dict('os.environ', {'DEPO_DATABASE_URL': 'postgresql://fixture'}), \
                patch.object(setup, 'initialise_schema') as initialize, \
                patch.object(setup, 'apply_migrations') as migrate, \
                patch('backend.depo_platform.credentials.bootstrap_environment') as bootstrap, \
                patch.object(setup, 'verify_schema', return_value={'status': 'ok'}):
            self.assertEqual(setup.setup_database(check_only=True), {'status': 'ok'})
            initialize.assert_not_called()
            migrate.assert_not_called()
            bootstrap.assert_not_called()

    def test_documented_contract_matches_release(self):
        self.assertEqual(len(setup.EXPECTED_COLUMNS), 11)
        self.assertEqual(sum(map(len, setup.EXPECTED_COLUMNS.values())), 53)
        self.assertEqual(len(setup.EXPECTED_CONSTRAINTS), 22)
        self.assertEqual(len(setup.EXPECTED_INDEXES), 9)


if __name__ == '__main__':
    unittest.main()
