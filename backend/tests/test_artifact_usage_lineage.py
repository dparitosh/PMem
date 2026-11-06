import json
from pathlib import Path
import tempfile
import unittest
from backend.artifact_store import ArtifactStore


class ArtifactUsageTests(unittest.TestCase):
    def test_identical_bytes_keep_distinct_workflow_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(root=Path(directory))
            first = store.ingest_bytes(b'same', filename='a.ttl', provenance={'run_id':'one'})
            second = store.ingest_bytes(b'same', filename='b.ttl', provenance={'run_id':'two'})
            self.assertEqual(first['artifact_id'], second['artifact_id'])
            self.assertNotEqual(first['usage_id'], second['usage_id'])
            usages = list(Path(directory).rglob('usage-*.json'))
            self.assertEqual(len(usages), 2)
            self.assertEqual({json.loads(path.read_text())['provenance']['run_id'] for path in usages}, {'one','two'})
