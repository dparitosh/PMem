"""Upgrade ordering and immutable-history safeguards without a live database."""
import unittest
from unittest.mock import MagicMock, patch

from backend import postgres_migrations as migrations


class UpgradeHistoryTests(unittest.TestCase):
    def run_upgrade(self, history):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = history
        migrations.apply_migrations(connection)
        return cursor

    def test_existing_prefix_applies_only_pending_sql(self):
        first = migrations.MIGRATIONS[0]
        cursor = self.run_upgrade([(first[0], first[1], migrations.migration_checksum(first[2]))])
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        for statement in first[2]:
            self.assertNotIn(statement, executed)
        for _, _, statements in migrations.MIGRATIONS[1:]:
            for statement in statements:
                self.assertIn(statement, executed)

    def test_complete_history_is_idempotent(self):
        cursor = self.run_upgrade([(v, n, migrations.migration_checksum(s)) for v, n, s in migrations.MIGRATIONS])
        self.assertFalse(any(call.args[0].startswith('INSERT INTO depo_schema_migrations') for call in cursor.execute.call_args_list))

    def test_missing_earlier_version_is_rejected(self):
        v, n, s = migrations.MIGRATIONS[1]
        with self.assertRaisesRegex(RuntimeError, 'missing earlier versions'):
            self.run_upgrade([(v, n, migrations.migration_checksum(s))])

    def test_changed_sql_is_rejected(self):
        v, n, _ = migrations.MIGRATIONS[0]
        with self.assertRaisesRegex(RuntimeError, 'checksum differs'):
            self.run_upgrade([(v, n, 'changed')])

    def test_newer_release_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'newer than or unknown'):
            self.run_upgrade([(999, 'future', 'checksum')])


if __name__ == '__main__':
    unittest.main()
