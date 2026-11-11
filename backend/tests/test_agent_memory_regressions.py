"""Memory identity, scope and configuration regressions (no database required)."""
import ast
import __future__
import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.Services.agent_memory_service import AgentMemoryService as Memory, _stable_id
from backend.depo_platform import agent_memory_config as config


class MemoryRegressions(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'AGENT_MEMORY_ENABLED': 'true',
            'AGENT_MEMORY_SCOPE': 'tcs:nexus', 'AGENT_MEMORY_QUERY_TIMEOUT': '5',
            'NEO4J_DATABASE': 'graph', 'AGENT_MEMORY_NEO4J_DATABASE': 'conversation'}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_different_field_boundaries_have_different_ids(self):
        self.assertNotEqual(_stable_id('a|b', 'c'), _stable_id('a', 'b|c'))
        first = Memory._mapping_fact_row('ontology', 'import', {'source_term':'a|b', 'target_term':'c'}, '')
        second = Memory._mapping_fact_row('ontology', 'import', {'source_term':'a', 'target_term':'b|c'}, '')
        self.assertNotEqual(first['fact_id'], second['fact_id'])

    def test_long_scopes_are_rejected_instead_of_colliding(self):
        for suffix in ('a', 'b'):
            with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE': 'x' * 256 + suffix}):
                with self.assertRaisesRegex(ValueError, 'AGENT_MEMORY_SCOPE'):
                    Memory.scope()

    def test_requested_settings_and_derived_scope_are_valid(self):
        self.assertEqual(Memory.scope(), 'tcs:nexus')
        self.assertEqual(config.query_timeout(), 5)
        with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE':'', 'DEPO_TENANT_ID':'tcs', 'DEPO_PROJECT_ID':'nexus'}):
            self.assertEqual(Memory.scope(), 'tcs:nexus')
        with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE':'', 'DEPO_TENANT_ID':'a:b', 'DEPO_PROJECT_ID':'c'}):
            with self.assertRaises(ValueError): Memory.scope()

    def test_invalid_timeout_and_boolean_do_not_silently_fall_back(self):
        for value in ('0', '31', '5cls', ''):
            with patch.dict(os.environ, {'AGENT_MEMORY_QUERY_TIMEOUT':value}):
                self.assertEqual(Memory.status()['invalid_setting'], 'AGENT_MEMORY_QUERY_TIMEOUT')
        with patch.dict(os.environ, {'AGENT_MEMORY_ENABLED':'yes'}):
            self.assertEqual(Memory.status()['status'], 'configuration_invalid')
