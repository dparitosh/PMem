import os
import unittest
from unittest.mock import patch
from backend.depo_platform.network import graph_dispatch_timeout_seconds, ontology_publication_timeout_seconds


class PublicationBudgets(unittest.TestCase):
    def test_nested_waits_cover_downstream_stages(self):
        for value, stage in [('180',180), ('900',900), ('invalid',180), ('99999',3600)]:
            with self.subTest(value=value), patch.dict(os.environ, {'GRAPH_PUBLICATION_TIMEOUT_SECONDS':value}):
                self.assertEqual(graph_dispatch_timeout_seconds(), 2 * stage + 30)
                self.assertEqual(ontology_publication_timeout_seconds(), 3 * stage + 60)
