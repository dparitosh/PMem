import ast
from pathlib import Path
from typing import Any
import unittest
from fastapi import APIRouter, FastAPI, Request
from backend.depo_platform.request_bodies import ApprovalBody
from backend.ontology_service.publication_contracts import PublicationJobResponse


class PublicationOpenApiTests(unittest.TestCase):
    def test_actual_route_documents_queued_job_response(self):
        tree = ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
        route = next(node for node in tree.body if getattr(node,'name','') == 'publish_registered_ontology')
        router = APIRouter()
        scope = {'router':router,'Request':Request,'ApprovalBody':ApprovalBody,'Any':Any,
                 'PublicationJobResponse':PublicationJobResponse}
        exec(compile(ast.Module(body=[route],type_ignores=[]),'<publication-route>','exec'),scope)
        app=FastAPI()
        app.include_router(router)
        document=app.openapi()
        response=document['paths']['/{ontology_id}/publish']['post']['responses']['202']
        self.assertEqual(response['content']['application/json']['schema']['$ref'], '#/components/schemas/PublicationJobResponse')
        schema=document['components']['schemas']['PublicationJobResponse']
        self.assertIn('job_id',schema['required'])
        self.assertIn('timed_out',schema['properties']['status']['enum'])
