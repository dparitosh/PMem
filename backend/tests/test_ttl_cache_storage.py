import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.Services import ttl_cache


class TurtleCacheTests(unittest.TestCase):
    def test_configured_storage_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"ARTIFACT_STORAGE": directory}):
            ttl_cache.write_ttl("run-1", "first")
            ttl_cache.write_ttl("run-1", "second")
            self.assertEqual(ttl_cache.read_ttl("run-1"), "second")
            self.assertEqual(list((Path(directory) / "ttl_cache").iterdir()), [ttl_cache.cache_path("run-1")])

    def test_legacy_reads_and_current_precedence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"ARTIFACT_STORAGE": directory}), patch.object(ttl_cache, "LEGACY_ROOT", Path(directory) / "legacy"):
            ttl_cache.LEGACY_ROOT.mkdir()
            legacy = ttl_cache.cache_path("old", ttl_cache.LEGACY_ROOT)
            legacy.write_text("legacy", encoding="utf-8")
            self.assertEqual(ttl_cache.read_ttl("old"), "legacy")
            ttl_cache.write_ttl("old", "new")
            self.assertEqual(ttl_cache.read_ttl("old"), "new")
            self.assertEqual(legacy.read_text(), "legacy")

    def test_invalid_identifiers(self):
        for value in ("../secret", "", "a/b", "a\\b", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ttl_cache.cache_path(value)

    def test_default_root_is_outside_source(self):
        with patch.dict(os.environ, {"ARTIFACT_STORAGE": ""}):
            self.assertEqual(ttl_cache.cache_root(), ttl_cache.REPOSITORY_ROOT / "data" / "artifacts" / "ttl_cache")
