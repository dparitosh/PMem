from contextlib import nullcontext
from unittest import TestCase, main
from unittest.mock import Mock, patch, MagicMock
from backend.depo_platform import credential_import as importer


class CredentialImportTests(TestCase):
    def setUp(self):
        self.cursor = MagicMock()
        self.cursor.__enter__.return_value = self.cursor
        self.db = Mock()
        self.db.cursor.return_value = self.cursor
        self.transaction = MagicMock()
        self.db.transaction.return_value = self.transaction
        self.key = 'random-fixture-key-' * 3
        self.values = {'GRAPH_READ_TOKEN': self.key, 'GRAPH_READ_TOKEN_ACTOR': 'reader'}
        self.valid_record = ('a1' * 32, importer.key_digest('a1' * 32, self.key), False, 'reader', None)
        self.cursor.fetchall.return_value = [('ADMIN_API_KEY',), ('GRAPH_READ_TOKEN',)]

    def apply(self, replace=False):
        with patch.object(importer, 'connection', return_value=nullcontext(self.db)), patch.object(importer, 'register_key') as register:
            result = importer.apply_values(self.values, replace)
            return result, register

    def test_new_key_is_registered_without_disclosing_it_in_result(self):
        self.cursor.fetchone.side_effect = [None, self.valid_record]
        results, register = self.apply()
        self.assertEqual(results, [{'profile': 'GRAPH_READ_TOKEN', 'status': 'created'}])
        self.assertNotIn(self.key, str(results))
        register.assert_called_once_with('GRAPH_READ_TOKEN', self.key, 'reader', None, db=self.db, audit_actor='deployment-import', bootstrap=True)

    def test_matching_key_is_not_rotated(self):
        salt = 'a1' * 32
        self.cursor.fetchone.return_value = (salt, importer.key_digest(salt, self.key), False, 'reader', None)
        results, register = self.apply()
        self.assertEqual(results[0]['status'], 'unchanged'); register.assert_not_called()

    def test_conflict_exits_transaction_with_error_without_overwrite(self):
        self.cursor.fetchone.return_value = ('a1' * 32, '0' * 64, False, 'reader', None)
        with self.assertRaisesRegex(ValueError, 'ReplaceExisting'): self.apply()
        self.assertIs(self.transaction.__exit__.call_args.args[0], importer.ImportValidationError)

    def test_explicit_replace_rotates(self):
        self.cursor.fetchone.side_effect = [('a1' * 32, '0' * 64, True, 'reader', None), self.valid_record]
        result, register = self.apply(True)
        self.assertEqual(result[0]['status'], 'replaced'); register.assert_called_once()

    def test_invalid_expiry_is_safe_and_checked_before_database(self):
        self.values['GRAPH_READ_TOKEN_EXPIRES_AT'] = 'sensitive-invalid-value'
        with patch.object(importer, 'connection') as connect:
            with self.assertRaises(ValueError) as caught: importer.apply_values(self.values)
            self.assertNotIn('sensitive-invalid-value', str(caught.exception)); connect.assert_not_called()

    def test_concurrent_new_profile_conflict_is_rejected(self):
        self.cursor.fetchone.side_effect = [None, ('a1' * 32, '0' * 64, False, 'other', None)]
        with self.assertRaisesRegex(importer.ImportValidationError, 'concurrently'):
            self.apply()
        self.assertIs(self.transaction.__exit__.call_args.args[0], importer.ImportValidationError)

    def test_initial_import_requires_active_admin_and_read_profiles(self):
        self.cursor.fetchone.return_value = self.valid_record
        self.cursor.fetchall.return_value = [('GRAPH_READ_TOKEN',)]
        with self.assertRaisesRegex(importer.ImportValidationError, 'active ADMIN_API_KEY'):
            self.apply()

    def test_secret_connection_errors_are_not_printed(self):
        import io
        from contextlib import redirect_stdout
        output = io.StringIO()
        stdin = Mock(buffer=io.BytesIO(b'{}'))
        with patch.object(importer, 'uses_postgres', return_value=True), patch.object(importer.sys, 'stdin', stdin), patch.object(importer.sys, 'argv', ['credential_import']), patch.object(importer, 'apply_values', side_effect=ValueError('password=secret-fixture')), redirect_stdout(output):
            self.assertEqual(importer.main(), 1)
        self.assertNotIn('secret-fixture', output.getvalue())


if __name__ == '__main__': main()
