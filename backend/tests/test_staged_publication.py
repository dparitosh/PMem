"""Exercise committed checkpoints, rollback and public activation without Neo4j."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.graph_service.staged_publication import publish_initial
from contextlib import nullcontext


class Session:
    def __init__(self):
        self.receipt = None
        self.nodes = set()
        self.edges = set()
        self.active = False
        self.fail_edges = False
        self.wrong_count = False
        self.writes = []
        self.queries = []
        self.canonical = set()

    def run(self, query, **params):
        self.queries.append((query, params))
        result = None
        if 'SET p.activation_owner=$owner_id' in query:
            self.receipt['activation_owner'] = params['owner_id']
        elif 'RETURN p {.*}' in query:
            result = {'receipt': self.receipt} if self.receipt else None
        elif 'RETURN p.activation_owner AS owner' in query:
            if self.receipt and self.receipt.get('activation_owner') == params['owner_id'] and self.receipt.get('status') == 'staging':
                result = {'owner': params['owner_id']}
        elif 'RETURN active + retained AS count' in query:
            result = {'count': int(self.active)}
        elif 'LIMIT $batch_size' in query:
            result = {'count': 0}
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
        elif 'MERGE (node:OntologyResource' in query:
            self.canonical.update(params['iris'])
        elif 'SET p.activation_resource_offset' in query:
            self.receipt['activation_resource_offset'] = params['offset']
        elif 'SET p.activation_relationship_offsets' in query:
            self.receipt['activation_relationship_offsets'] = params['offsets']
        elif 'SET p.resource_offset' in query:
            self.receipt['resource_offset'] = params['offset']
        elif 'SET p.relationship_offsets' in query:
            self.receipt['relationship_offsets'] = params['offsets']
        elif 'SET n:OntologyResource REMOVE n:StagedOntologyResource' in query:
            self.active = True
        elif "SET p.status='published'" in query:
            self.active = True
            self.receipt['status'] = 'published'
            self.receipt['current'] = True
            self.receipt['hierarchy_edges'] = params['hierarchy_edges']
            self.receipt.update({key: params[key] for key in ('ontology_id', 'publication_id', 'prefix', 'resources', 'relationships')})
        return SimpleNamespace(single=lambda: result, consume=lambda: None)

    def execute_write(self, operation):
        before = copy.deepcopy((self.receipt, self.nodes, self.edges, self.active, self.canonical))
        try:
            result = operation(self)
            self.writes.append(operation.__name__)
            return result
        except Exception:
            self.receipt, self.nodes, self.edges, self.active, self.canonical = before
            raise


class StagedPublicationTests(unittest.TestCase):
    def setUp(self):
        barrier = patch('backend.graph_service.publication_activation.replacement_access',
                        lambda *args, **kwargs: nullcontext(SimpleNamespace(begin_mutation=lambda: None, owner_id='fixture-owner')))
        barrier.start()
        self.addCleanup(barrier.stop)

    def test_current_legacy_receipt_is_idempotent_without_staging_metadata(self):
        session = Session()
        session.active = True
        session.receipt = {'status': 'published', 'current': True, 'resources': 1201,
                           'relationships': 1200, 'hierarchy_edges': 0, 'prefix': 'd'}
        self.assertEqual(self.publish(session, artifact_sha256='digest')['resources'], 1201)
        self.assertEqual(session.writes, [])
        # Same-size content with another digest cannot inherit a legacy receipt.
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            self.publish(session, artifact_sha256='different-content-digest')
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            self.publish(session)
        session.receipt['resources'] = 1200
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            self.publish(session, artifact_sha256='digest')

    def publish(self, session, count=1201, artifact_sha256=None):
        return publish_initial(session, ontology_id='demo', publication_id='digest', prefix='d',
            resources=[{'iri': str(i)} for i in range(count)],
            relationships={'SUBCLASS_OF': [], 'HAS_PART': [], 'SEMANTIC_RELATION': [
                {'source': str(i), 'target': str(i+1), 'predicate': 'p'} for i in range(count-1)]},
            relation_queries={'SUBCLASS_OF': '', 'HAS_PART': '', 'SEMANTIC_RELATION': 'MERGE (source)-[edge:SEMANTIC_RELATION]->(target)'},
            resource_query='UNWIND $rows AS row MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})',
            timeout=180, unit_of_work=lambda **_: lambda fn: fn, artifact_sha256=artifact_sha256)

    def test_preparation_and_activation_commit_bounded_batches(self):
        session = Session()
        result = self.publish(session)
        self.assertEqual(result['resources'], 1201)
        self.assertEqual(session.writes.count('write_resources'), 2)
        self.assertEqual(session.writes.count('copy'), 2)
        self.assertEqual(session.writes[-1], 'finish')
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

    def test_existing_projection_commits_staging_before_identity_preserving_activation(self):
        session = Session(); session.active = True
        self.assertEqual(self.publish(session)['resources'], 1201)
        self.assertEqual(session.writes.count('write_resources'), 2)
        self.assertEqual(session.writes[-1], 'finish')
        self.assertEqual(session.receipt['status'], 'published')

    def test_completed_receipt_retry_does_not_replay_any_write(self):
        session = Session()
        self.publish(session)
        writes = list(session.writes)
        self.publish(session)
        self.assertEqual(session.writes, writes)

    def test_replacement_interruption_preserves_active_projection_and_resumes(self):
        session = Session(); session.active = True; session.fail_edges = True
        with self.assertRaises(TimeoutError): self.publish(session)
        self.assertTrue(session.active)
        self.assertEqual(session.receipt['resource_offset'], 1201)
        resource_batches = session.writes.count('write_resources')
        self.publish(session)
        self.assertEqual(session.writes.count('write_resources'), resource_batches)

    def test_replacement_reads_staged_properties_in_bounded_identity_batches(self):
        session = Session(); session.active = True
        self.publish(session)
        copies = [(q, p) for q, p in session.queries if 'MERGE (node:OntologyResource' in q]
        self.assertEqual([len(p['iris']) for q, p in copies], [1000, 201])
        self.assertTrue(all('MATCH (staged:StagedOntologyResource' in q for q, p in copies))
        self.assertTrue(all('rows' not in p for q, p in copies))
        self.assertEqual(len(session.canonical), 1201)
        self.assertFalse(any('DETACH DELETE' in q for q, p in session.queries))

    def test_replacement_activation_does_not_grant_a_second_full_write_budget(self):
        session = Session(); session.active = True
        elapsed = [0]
        budgets = []
        original = session.execute_write
        def write(operation):
            value = original(operation)
            if operation.__name__ == 'write_resources': elapsed[0] = 130
            return value
        session.execute_write = write
        def unit_of_work(**options):
            budgets.append(options['timeout'])
            return lambda function: function
        with patch('backend.graph_service.staged_publication.time.monotonic', side_effect=lambda: elapsed[0]):
            publish_initial(session, ontology_id='demo', publication_id='revision', prefix='d',
                resources=[{'iri': 'a'}], relationships={'SUBCLASS_OF': [], 'HAS_PART': []},
                relation_queries={'SUBCLASS_OF': '', 'HAS_PART': ''},
                resource_query='UNWIND $rows AS row MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})',
                timeout=180, activation_timeout=60, unit_of_work=unit_of_work)
        self.assertTrue(all(0 < budget <= 30 for budget in budgets[-7:]))

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
            if operation.__name__ == 'copy':
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
            resource_query='UNWIND $rows AS row MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})',
            timeout=180, activation_timeout=60, unit_of_work=lambda **kw: lambda fn: fn,
            query_factory=lambda query, timeout: reads.append(timeout) or query)
        self.assertEqual(len(reads), 1)
        self.assertTrue(all(0 < timeout <= 10 for timeout in reads))


if __name__ == '__main__': unittest.main()
