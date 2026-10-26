"""Offline regression checks; also runnable with Python's unittest runner."""
import importlib.util
import os
from pathlib import Path
import unittest
import shutil
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

from backend.depo_platform import database_setup as pg
from backend.depo_platform import neo4j_setup as neo

ROOT = Path(__file__).resolve().parents[2]


class UpgradePreflightTests(unittest.TestCase):
    def test_view_select_access_and_table_ownership_remain_distinct(self):
        for tables, views, error in [([], [], None), ([('depo_registry',)], [], 'cannot alter'), ([], [('depo_ontology_analytics',)], 'requires SELECT')]:
            conn = MagicMock()
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = (True, True, True)
            cur.fetchall.side_effect = [tables, views]
            if error:
                with self.assertRaisesRegex(RuntimeError, error):
                    pg.verify_migration_privileges(conn)
            else:
                pg.verify_migration_privileges(conn)
            self.assertIn("c.relkind IN ('r','p')", cur.execute.call_args_list[1].args[0])
            if not tables:
                self.assertIn('has_table_privilege', cur.execute.call_args_list[2].args[0])

    def history(self, rows, checksum_column=True):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ('semantic.depo_schema_migrations',)
        cursor.fetchall.side_effect = [[('checksum',)] if checksum_column else [], rows]
        return conn, cursor

    def test_pending_migrations_allowed_without_writes(self):
        version, name, sql = pg.MIGRATIONS[0]
        conn, cur = self.history([(version, name, pg.migration_checksum(sql))])
        pg.verify_upgrade_history(conn)
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list))

    def test_unknown_gap_and_changed_checksum_rejected(self):
        for rows in [[(999, 'unknown', 'x')], [(2, 'gap', 'x')], [(1, pg.MIGRATIONS[0][1], 'changed')]]:
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                pg.verify_upgrade_history(self.history(rows)[0])

    def test_legacy_history_requires_explicit_consent(self):
        row = (1, pg.MIGRATIONS[0][1], None)
        with patch.dict(os.environ, {'DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS': 'false'}):
            with self.assertRaises(RuntimeError):
                pg.verify_upgrade_history(self.history([row], False)[0])
        with patch.dict(os.environ, {'DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS': 'true'}):
            pg.verify_upgrade_history(self.history([row], False)[0])

    def test_neo4j_missing_new_objects_allowed_but_conflicts_rejected(self):
        self.assertEqual(neo.verify_constraints([], allow_missing=True), [])
        self.assertEqual(neo.verify_indexes([], allow_missing=True), [])
        with self.assertRaises(RuntimeError):
            neo.verify_constraints([{'name': 'uq_ontologyresource_identity', 'type': 'EXISTS'}], allow_missing=True)
        with self.assertRaises(RuntimeError):
            neo.verify_indexes([{'name': 'idx_depo_ontologyresource_scope', 'state': 'FAILED'}], allow_missing=True)
        with self.assertRaises(RuntimeError):
            neo.verify_constraints([])

    def test_database_checks_precede_shutdown(self):
        source = (ROOT / 'infra/windows/update-depo-windows.ps1').read_text()
        stop = source.index("'stop-depo-services.ps1'")
        self.assertLess(source.index("'initialize-depo-schema.ps1'"), stop)
        self.assertLess(source.index("'test-depo-neo4j.ps1'"), stop)
        self.assertLess(source.index('backend.agentic_service.configuration --preflight'), stop)
        self.assertLess(source.index('backend.agentic_service.configuration --preflight'), source.index('if ($PreflightOnly)'))

    def test_linux_public_routing_excludes_secrets(self):
        spec = importlib.util.spec_from_file_location('browser_routing', ROOT / 'infra/linux/browser-routing.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        values = {'DEPO_ROUTING_MODE': 'gateway', 'DEPO_API_GATEWAY_URL': 'https://example.test/depo', 'ADMIN_API_KEY': 'private'}
        result = module.browser_routing(values)
        self.assertEqual(result['VITE_ONTOLOGY_SERVICE_URL'], 'https://example.test/depo/ontology')
        self.assertNotIn('private', str(result))
        result = module.browser_routing({'DEPO_ROUTING_MODE': 'local', 'AUTH_MODE': 'token', 'DEPO_LOCAL_SERVICE_HOST': '10.0.2.16'})
        self.assertEqual(result['VITE_API_GATEWAY_URL'], '')
        self.assertEqual(result['VITE_AGENTIC_SERVICE_URL'], 'http://10.0.2.16:8012')
        with self.assertRaises(ValueError):
            module.browser_routing({**values, 'DEPO_GATEWAY_GRAPH_PATH': '../graph'})


    def test_linux_environment_comments_quotes_and_redaction(self):
        bash = shutil.which('bash') or ('C:/Program Files/Git/bin/bash.exe' if Path('C:/Program Files/Git/bin/bash.exe').exists() else None)
        if not bash:
            self.skipTest('Bash is unavailable')
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            env_file = Path(directory) / 'fixture.env'
            relative = env_file.relative_to(ROOT).as_posix()
            env_file.write_text('A=value # comment\nB="quoted # literal" # comment\nC=url#fragment\n', encoding='utf-8')
            command = 'source infra/linux/common.sh; depo_load_env "$1"; printf "%s|%s|%s" "$A" "$B" "$C"'
            result = subprocess.run([bash, '-c', command, 'test', relative], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'value|quoted # literal|url#fragment')
            for malformed in ['private_secret_without_equals', 'BAD KEY=private_secret', 'A="private_secret']:
                env_file.write_text(malformed, encoding='utf-8')
                result = subprocess.run([bash, '-c', 'source infra/linux/common.sh; depo_load_env "$1"', 'test', relative], cwd=ROOT, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('private_secret', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
