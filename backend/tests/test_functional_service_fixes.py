"""Execute real merge/LLM boundaries with dependency-light service doubles."""
import ast
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from typing import Any
from backend.core.ollama_auth import ollama_headers
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class WithoutImports(ast.NodeTransformer):
    def visit_Import(self, node): return None
    def visit_ImportFrom(self, node): return None


def load(path, scope):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    tree = WithoutImports().visit(tree)
    exec(compile(ast.fix_missing_locations(tree), path, 'exec'), scope)
    return scope


class Literal(str):
    def n3(self): return json.dumps(str(self))


class Graph:
    parsed = []
    def __init__(self): self.triples = []
    def parse(self, *, data, format): self.parsed.append(format)
    def subjects(self, predicate, value):
        return [subject for subject, p, v in self.triples if p == predicate and v == value]
    def __iter__(self): return iter(self.triples)
    def __len__(self): return max(1, len(self.triples))
    def add(self, triple): self.triples.append(triple)
    def serialize(self, format): return 'retained preview'


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.registration_calls = 0
        self.version_calls = 0
        metadata = {'ontology_name': 'Example', 'original_filename': 'example.rdf'}
        def register(**kwargs):
            self.registration_calls += 1
            self.assertTrue(kwargs['source'].startswith('governed-merge:'))
            return {'ontology_id': 'merged_1', 'provenance': kwargs['extra_metadata']['provenance']}
        def version(**kwargs):
            self.version_calls += 1
            return {'version': '1'}
        catalog = SimpleNamespace(get=lambda _: metadata, read_artifact=lambda _: (metadata, b'xml'),
                                  _parse_ontology=lambda *_: {'rdf_format': 'xml'}, register=register)
        scope = load('backend/ontology_service/merge_service.py', dict(
            json=json, hashlib=hashlib, threading=threading, Path=Path, Any=Any,
            Graph=Graph, Literal=Literal, uuid=__import__('uuid'),
            datetime=__import__('datetime').datetime, timezone=__import__('datetime').timezone,
            RDF=SimpleNamespace(type='rdf:type'), OWL=SimpleNamespace(FunctionalProperty='functional')))
        self.merge = scope['GovernedMergeService'](catalog, SimpleNamespace(create_version=version), Path(self.directory.name))

    def test_xml_merge_and_repeat_apply_reuse_receipt(self):
        Graph.parsed = []
        preview = self.merge.preview({'source_ontology_ids': ['one', 'two']})
        self.assertEqual(Graph.parsed, ['xml', 'xml'])
        first = self.merge.apply(preview['preview_id'], 'steward')
        self.assertEqual(self.merge.apply(preview['preview_id'], 'steward'), first)
        self.assertEqual((self.registration_calls, self.version_calls), (1, 1))

    def test_multivalued_labels_are_not_functional_conflicts(self):
        graph = Graph()
        graph.triples = [('class', 'label', Literal('English')), ('class', 'label', Literal('French'))]
        self.assertEqual(self.merge._literal_conflicts(graph), [])
        graph.triples += [('property', 'rdf:type', 'functional'), ('class', 'property', Literal('1')), ('class', 'property', Literal('2'))]
        self.assertEqual(len(self.merge._literal_conflicts(graph)), 1)

    def test_invalid_source_shapes_rejected(self):
        for value in ['one,two', ['one', {}], ['one', 'one'], ['']]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.merge.preview({'source_ontology_ids': value})

    def test_concurrent_previews_are_retained(self):
        threads = [threading.Thread(target=self.merge.preview, args=({'source_ontology_ids': ['one', 'two']},)) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(self.merge._load()), 8)

    def test_central_merge_store_writes_only_changed_preview(self):
        records, writes = {}, []
        def put(key, value): records[key] = copy.deepcopy(value); writes.append(key)
        self.merge.registry = SimpleNamespace(
            advisory_lock=lambda _: self.merge.lock, put=put,
            get=lambda key: copy.deepcopy(records.get(key)), all=lambda: copy.deepcopy(records))
        first = self.merge.preview({'source_ontology_ids': ['one', 'two']})
        second = self.merge.preview({'source_ontology_ids': ['one', 'two']})
        self.assertEqual(len(writes), 2)
        self.merge.apply(first['preview_id'], 'steward')
        self.assertEqual(writes[-1], first['preview_id'])
        self.assertNotIn('applied_result', records[second['preview_id']])


class LocalLlmTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'USE_LLM': 'ollama', 'LLM_MODEL_NAME': 'offline:latest', 'OLLAMA_BASE_URL': 'http://127.0.0.1:11434/api/chat'}, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.models = ['offline:latest']
        self.fails = False
        self.delay = 0
        owner = self
        class HttpError(Exception): pass
        class Client:
            def __init__(self, timeout): owner.timeout = timeout
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, url, **kwargs):
                owner.url = url
                await asyncio.sleep(owner.delay)
                if owner.fails: raise HttpError()
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'models': [{'name': model} for model in owner.models]})
            async def post(self, url, **kwargs):
                owner.request = kwargs['json']
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'message': {'content': 'Bounded summary'}})
        self.scope = load('backend/agentic_service/local_llm.py', dict(ollama_headers=ollama_headers, os=os, json=json, asyncio=asyncio, urlsplit=urlsplit, urlunsplit=urlunsplit,
                          httpx=SimpleNamespace(AsyncClient=Client, HTTPError=HttpError, HTTPStatusError=type('StatusError', (Exception,), {}))))

    async def test_health_distinguishes_ready_missing_and_unavailable(self):
        self.assertEqual((await self.scope['health']())['status'], 'ready')
        self.assertEqual(self.url, 'http://127.0.0.1:11434/api/tags')
        self.assertLessEqual(self.timeout, 5)
        self.models = []
        self.assertEqual((await self.scope['health']())['status'], 'model_missing')
        self.fails = True
        self.assertEqual((await self.scope['health']())['status'], 'unavailable')

    async def test_summary_is_bounded_and_nonstreaming(self):
        self.assertEqual(await self.scope['summarize']('question', [{'resource_id': '1'}]), 'Bounded summary')
        self.assertFalse(self.request['stream'])
        self.assertEqual(self.request['options']['num_predict'], 256)

    async def test_invalid_configuration_is_not_reported_ready(self):
        os.environ['LLM_REQUEST_TIMEOUT_SECONDS'] = '0'
        self.assertEqual((await self.scope['health']())['status'], 'invalid_configuration')

    async def test_slow_runtime_respects_total_diagnostic_deadline(self):
        os.environ['LLM_REQUEST_TIMEOUT_SECONDS'] = '1'
        self.delay = 2
        self.assertEqual((await self.scope['health']())['status'], 'unavailable')


class EvidenceReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_conversion_references_reach_registration(self):
        captured = {}
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, **kwargs):
                if url.endswith('/register'): captured.update(kwargs['data'])
                return SimpleNamespace(raise_for_status=lambda: None,
                    json=lambda: {'compliant': True, 'publish_recommended': True, 'ontology_id': 'demo_1'})
        conversion = {'ontology': {'name': 'Demo', 'prefix': 'demo', 'turtle': 'rdf'},
                      'artifacts': {'source': 'sha256:source', 'structural_model': 'sha256:model'},
                      'data_product_draft': {'contract': 'schema-analytics-data-product-v2'}}
        async def offload(callback, *args, **kwargs): return callback(*args, **kwargs)
        scope = load('backend/ingestion_service/engineering_workflow.py', dict(
            os=os, json=json, hashlib=hashlib, Any=Any, Path=Path,
            service_url=lambda key, fallback: fallback, EngineeringSchemaConverter=object,
            run_in_threadpool=offload, service_bearer_headers=lambda *args, **kwargs: {},
            httpx=SimpleNamespace(AsyncClient=lambda **kwargs: Client())))
        workflow = scope['EngineeringWorkflow'](SimpleNamespace(convert=lambda **kwargs: conversion))
        workflow._governance_entities = lambda _: []
        await workflow.run(filename='example.xsd', content=b'xsd')
        metadata = json.loads(captured['extra_metadata'])
        self.assertEqual(metadata['engineering_artifacts'], conversion['artifacts'])
        self.assertEqual(metadata['data_product_draft'], conversion['data_product_draft'])

    def test_native_report_uses_retained_structural_model(self):
        with TemporaryDirectory() as directory:
            model = Path(directory) / 'content'
            model.write_text(json.dumps({'tables': [], 'columns': [], 'source_file': 'source.xsd'}), encoding='utf-8')
            metadata = {'ontology_id': 'native_1', 'source_filename': 'customer.xsd',
                        'engineering_artifacts': {'structural_model': 'sha256:model'}}
            tree = ast.parse((ROOT / 'backend/ingestion_service/router.py').read_text(encoding='utf-8'))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'xsd_relational_report')
            function.decorator_list = []
            function = WithoutImports().visit(function)
            scope = dict(Request=object, Query=lambda *args, **kwargs: None, Path=Path, json=json,
                         graph_read_identity=lambda _: 'reader',
                         OntologyUploadManager=SimpleNamespace(get_ontology=lambda _: {'status': 'not_found'}),
                         OntologyTaxonomyService=SimpleNamespace(_resolve_metadata=lambda _: metadata),
                         ArtifactStore=lambda: SimpleNamespace(resolve=lambda _: ({}, model)),
                         build_analytics_schema_plan=lambda report: {'table_count': len(report['tables'])})
            exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), 'native-report', 'exec'), scope)
            report = scope['xsd_relational_report'](object(), 'native_1')
            self.assertEqual(report['source_file'], 'customer.xsd')
            self.assertEqual(report['ontology_id'], 'native_1')
            self.assertEqual(report['analytics_schema_plan']['table_count'], 0)
