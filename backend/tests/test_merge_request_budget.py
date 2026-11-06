import os
import unittest
import asyncio
from unittest.mock import patch
from backend.depo_platform.qos import request_budget

class MergeRequestBudgetTests(unittest.TestCase):
    def test_middleware_allows_preview_past_generic_limit_without_extending_other_routes(self):
        import httpx
        from fastapi import FastAPI
        from backend.depo_platform.qos import QoSMiddleware, QoSState
        async def scenario():
            app = FastAPI()
            app.add_middleware(QoSMiddleware, state=QoSState())
            async def work():
                await asyncio.sleep(1.2)
                return {'complete': True}
            app.post('/api/v1/ontologies/merges/preview')(work)
            app.get('/ordinary')(work)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                preview, ordinary = await asyncio.gather(client.post('/api/v1/ontologies/merges/preview'), client.get('/ordinary'))
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(ordinary.status_code, 504)
        with patch.dict(os.environ, {'DEPO_REQUEST_TIMEOUT_SECONDS':'1', 'MERGE_VALIDATION_TIMEOUT_SECONDS':'2'}):
            asyncio.run(scenario())

    def test_preview_receives_configured_worker_budget_plus_transport_allowance(self):
        with patch.dict(os.environ, {'MERGE_VALIDATION_TIMEOUT_SECONDS':'900', 'DEPO_REQUEST_TIMEOUT_SECONDS':'90'}):
            self.assertEqual(request_budget('/api/v1/ontologies/merges/preview'), 930)
            self.assertEqual(request_budget('/api/v1/ontologies/merges/preview/'), 930)
            self.assertEqual(request_budget('/api/v1/ontologies/example'), 90)
            self.assertEqual(request_budget('/api/v1/ontologies/merges/preview-invalid'), 90)

    def test_apply_covers_validation_and_publication_but_status_reads_stay_short(self):
        with patch.dict(os.environ, {'MERGE_VALIDATION_TIMEOUT_SECONDS':'180', 'DEPO_REQUEST_TIMEOUT_SECONDS':'90'}), \
             patch('backend.depo_platform.network.ontology_publication_timeout_seconds', return_value=400):
            self.assertEqual(request_budget('/api/v1/ontologies/merges/id/apply'), 610)
            self.assertEqual(request_budget('/api/v1/ontologies/merges/id/apply-automatic'), 610)
            self.assertEqual(request_budget('/api/v1/ontologies/merges/id/receipt'), 90)

if __name__ == '__main__': unittest.main()
