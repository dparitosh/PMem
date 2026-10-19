import unittest
from unittest.mock import Mock
from backend.graph_service.publication_cleanup import cleanup_completed_staging, try_cleanup_completed_staging


def result(row):
    response = Mock()
    response.single.return_value = row
    return response


class PublicationCleanupTests(unittest.TestCase):
    def test_unpublished_attempt_is_untouched(self):
        session = Mock()
        session.run.return_value = result(None)
        self.assertEqual(cleanup_completed_staging(session, ontology_id='o', publication_id='p'), 0)
        session.execute_write.assert_not_called()

    def test_count_mismatch_retains_recovery_data(self):
        session = Mock()
        session.run.side_effect = [result({'resources': 2, 'relationships': 1}), result({'resources': 1, 'relationships': 1})]
        with self.assertRaises(ValueError):
            cleanup_completed_staging(session, ontology_id='o', publication_id='p')
        session.execute_write.assert_not_called()

    def test_deletes_only_completed_exact_publication_in_bounded_batches(self):
        session = Mock()
        session.run.side_effect = [result({'resources': 1001, 'relationships': 1000}), result({'resources': 1001, 'relationships': 1000})]
        tx = Mock()
        tx.run.side_effect = [result({'removed': 1000}), result({'removed': 1})]
        session.execute_write.side_effect = lambda operation: operation(tx)
        self.assertEqual(cleanup_completed_staging(session, ontology_id='o', publication_id='p'), 1001)
        for call in tx.run.call_args_list:
            query = call.args[0]
            self.assertIn('n:StagedOntologyResource', query)
            self.assertIn('publication_id:$publication_id', query)
            self.assertIn("p.status='published' AND p.current=true", query)
            self.assertIn('LIMIT 1000', query)
            self.assertNotIn('n:OntologyResource', query)
            self.assertEqual(call.kwargs, {'ontology_id':'o', 'publication_id':'p'})

    def test_cleanup_failure_does_not_invalidate_publication(self):
        session = Mock()
        session.run.side_effect = RuntimeError('database unavailable')
        with self.assertLogs('backend.graph_service.publication_cleanup', level='ERROR'):
            self.assertIsNone(try_cleanup_completed_staging(session, ontology_id='o', publication_id='p'))


if __name__ == '__main__': unittest.main()
