"""Exercise committed checkpoints, rollback and public activation without Neo4j."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.graph_service.staged_publication import publish_initial


class Session:
    def __init__(self):
        self.receipt = None
        self.nodes = set()
        self.edges = set()
        self.active = False
        self.fail_edges = False
        self.wrong_count = False
        self.writes = []

    def run(self, query, **params):
        result = None
        if 'RETURN p {.*}' in query:
            result = {'receipt': self.receipt} if self.receipt else None
        elif 'RETURN active + retained AS count' in query:
            result = {'count': int(self.active)}
        elif 'RETURN count(r)' in query:
            result = {'count': len(self.edges)}
        elif 'RETURN count(n)' in query:
            result = {'count': len(self.nodes) + int(self.wrong_count)}
        elif "ON CREATE SET p.status='staging'" in query:
            if self.receipt is None:
                self.receipt = {'status': 'staging', 'resources_expected': params['resources'],
                    'relationships_expected': params['relationships'], 'resource_offset': 0,
                    'relationship_offsets': '{}', 'batch_size': params['batch_size'],
                    'manifest_sha256': params['manifest_sha256']}
        elif 'MERGE (node:StagedOntologyResource' in query:
            self.nodes.update(row['iri'] for row in params['rows'])
        elif 'MATCH (source:StagedOntologyResource' in query:
            if self.fail_edges:
                self.fail_edges = False
                raise TimeoutError('Interrupted batch')
            self.edges.update((row['source'], row['predicate'], row['target']) for row in params['rows'])
        elif 'SET p.resource_offset' in query:
            self.receipt['resource_offset'] = params['offset']
        elif 'SET p.relationship_offsets' in query:
            self.receipt['relationship_offsets'] = params['offsets']
        elif 'SET n:OntologyResource REMOVE n:StagedOntologyResource' in query:
            self.active = True
        elif "SET p.status='published'" in query:
            self.receipt['status'] = 'published'
        return SimpleNamespace(single=lambda: result, consume=lambda: None)

    def execute_write(self, operation):
        before = copy.deepcopy((self.receipt, self.nodes, self.edges, self.active))
        try:
            result = operation(self)
            self.writes.append(operation.__name__)
            return result
        except Exception:
            self.receipt, self.nodes, self.edges, self.active = before
            raise


class StagedPublicationTests(unittest.TestCase):
    def publish(self, session, count=1201):
        return publish_initial(session, ontology_id='demo', publication_id='digest', prefix='d',
            resources=[{'iri': str(i)} for i in range(count)],
            relationships={'SUBCLASS_OF': [], 'HAS_PART': [], 'SEMANTIC_RELATION': [
                {'source': str(i), 'target': str(i+1), 'predicate': 'p'} for i in range(count-1)]},
            relation_queries={'SUBCLASS_OF': '', 'HAS_PART': '', 'SEMANTIC_RELATION': 'MERGE (source)-[edge:SEMANTIC_RELATION]->(target)'},
            resource_query='MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})',
            timeout=180, unit_of_work=lambda **_: lambda fn: fn)

    def test_batches_commit_before_one_atomic_activation(self):
        session = Session()
        result = self.publish(session)
        self.assertEqual(result['resources'], 1201)
        self.assertEqual(session.writes, ['initialize', 'write_resources', 'write_resources',
                                         'write_edges', 'write_edges', 'activate'])
        self.assertTrue(session.active)
        self.assertEqual(session.receipt['status'], 'published')

    def test_interrupted_batches_remain_hidden_and_resume_without_resource_replay(self):
        session = Session(); session.fail_edges = True
        with self.assertRaises(TimeoutError): self.publish(session)
        self.assertFalse(session.active)
        self.assertEqual(session.receipt['resource_offset'], 1201)
        committed_resource_batches = session.writes.count('write_resources')
        self.publish(session)
        self.assertTrue(session.active)
        self.assertEqual(session.writes.count('write_resources'), committed_resource_batches)

    def test_count_mismatch_prevents_activation_and_keeps_previous_commits_hidden(self):
        session = Session(); session.wrong_count = True
        with self.assertRaisesRegex(ValueError, 'counts'): self.publish(session)
        self.assertFalse(session.active)
        self.assertEqual(session.receipt['status'], 'staging')

    def test_changed_manifest_cannot_resume_same_publication_id(self):
        session = Session(); session.fail_edges = True
        with self.assertRaises(TimeoutError): self.publish(session)
        with self.assertRaisesRegex(ValueError, 'manifest changed'): self.publish(session, count=1202)

    def test_existing_projection_uses_identity_preserving_atomic_path(self):
        session = Session(); session.active = True
        self.assertIsNone(self.publish(session))
        self.assertEqual(session.writes, [])

    def test_deadline_stops_between_batches_and_resume_preserves_commits(self):
        session = Session()
        # Start, initialization, first batch, then expiry before the next batch.
        with patch('backend.graph_service.staged_publication.time.monotonic',
                   side_effect=lambda: 181 if session.writes.count('write_resources') else 0):
            with self.assertRaisesRegex(TimeoutError, 'deadline'):
                self.publish(session)
        self.assertFalse(session.active)
        self.assertEqual(session.receipt['resource_offset'], 1000)
        self.publish(session)
        self.assertTrue(session.active)
        self.assertEqual(session.writes.count('write_resources'), 2)

    def test_unrecognized_resource_query_fails_before_any_write(self):
        session = Session()
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            publish_initial(session, ontology_id='demo', publication_id='digest', prefix='d',
                resources=[], relationships={}, relation_queries={}, resource_query='CREATE (node:OntologyResource)',
                timeout=180, unit_of_work=lambda **_: lambda fn: fn)
        self.assertEqual(session.writes, [])

    def test_activation_failure_retains_batches_and_retries_only_activation(self):
        session = Session()
        original = session.execute_write
        def execute(operation):
            if operation.__name__ == 'activate':
                raise TimeoutError('Activation transaction timed out')
            return original(operation)
        session.execute_write = execute
        with self.assertRaises(TimeoutError): self.publish(session)
        self.assertFalse(session.active)
        self.assertEqual(session.receipt['resource_offset'], 1201)
        writes = list(session.writes)
        session.execute_write = original
        self.publish(session)
        self.assertEqual(session.writes.count('write_resources'), writes.count('write_resources'))
        self.assertEqual(session.writes.count('write_edges'), writes.count('write_edges'))
        self.assertTrue(session.active)

    def test_preliminary_reads_receive_query_deadlines(self):
        reads = []
        publish_initial(Session(), ontology_id='demo', publication_id='digest', prefix='d', resources=[],
            relationships={'SUBCLASS_OF':[], 'HAS_PART':[]}, relation_queries={'SUBCLASS_OF':'','HAS_PART':''},
            resource_query='MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})',
            timeout=180, activation_timeout=60, unit_of_work=lambda **kw: lambda fn: fn,
            query_factory=lambda query, timeout: reads.append(timeout) or query)
        self.assertEqual(len(reads), 2)
        self.assertTrue(all(0 < timeout <= 10 for timeout in reads))


if __name__ == '__main__': unittest.main()
