"""Execute real merge/LLM boundaries with dependency-light service doubles."""
import ast
import asyncio
import copy
import json
import os
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class WithoutImports(ast.NodeTransformer):
    def visit_Import(self, node): return None
    def visit_ImportFrom(self, node): return None




class MergeTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.registration_calls = 0
        self.version_calls = 0
        metadata = {'ontology_name': 'Example', 'original_filename': 'example.rdf'}
        from rdflib import Graph as RdfGraph, Literal, URIRef, RDF as RdfType, OWL as OwlType, RDFS
        from rdflib.namespace import DC
        graph = RdfGraph()
        graph.add((URIRef('urn:example:Part'), RdfType.type, OwlType.Class))
        graph.add((URIRef('urn:example:Part'), RDFS.label, Literal('Part')))
        graph.add((URIRef('urn:example:Part'), RDFS.comment, Literal('A manufactured part')))
        graph.add((URIRef('urn:example:Part'), DC.source, URIRef('urn:example:source')))
        content = graph.serialize(format='xml', encoding='utf-8')
        def register(**kwargs):
            self.registration_calls += 1
            self.assertTrue(kwargs['source'].startswith('governed-merge:'))
            return {'ontology_id': 'merged_1', 'provenance': kwargs['extra_metadata']['provenance']}
        def version(**kwargs):
            self.version_calls += 1
            return {'version': '1'}
        catalog = SimpleNamespace(get=lambda _: metadata, read_artifact=lambda _: (metadata, content),
                                  with_publication_lock=lambda key, operation: operation(),
                                  _parse_ontology=lambda *_: {'rdf_format': 'xml'}, register=register)
        from backend.ontology_service.merge_service import GovernedMergeService
        self.merge = GovernedMergeService(catalog, SimpleNamespace(create_merge_version=version), Path(self.directory.name))

    def test_xml_merge_and_repeat_apply_reuse_receipt(self):
        preview = self.merge.preview({'source_ontology_ids': ['one', 'two']})
        self.assertEqual(preview['triple_count'], 4)
        self.assertEqual(preview['source_ontology_ids'], ['one', 'two'])
        first = self.merge.apply(preview['preview_id'], 'steward')
        self.assertEqual(self.merge.apply(preview['preview_id'], 'steward'), first)
        self.assertEqual((self.registration_calls, self.version_calls), (1, 1))

    def test_multivalued_labels_are_not_functional_conflicts(self):
        from rdflib import Graph, Literal, URIRef, RDF, OWL, RDFS
        graph = Graph()
        subject, property_id = URIRef('urn:example:Part'), URIRef('urn:example:serial')
        graph.add((subject, RDFS.label, Literal('English')))
        graph.add((subject, RDFS.label, Literal('French')))
        self.assertEqual(self.merge._literal_conflicts(graph), [])
        graph.add((property_id, RDF.type, OWL.FunctionalProperty))
        graph.add((subject, property_id, Literal('1')))
        graph.add((subject, property_id, Literal('2')))
        self.assertEqual(len(self.merge._literal_conflicts(graph)), 1)

    def test_missing_authored_label_still_blocks_merge(self):
        from rdflib import Graph, URIRef, RDF, OWL
        graph = Graph()
        graph.add((URIRef('urn:example:Unlabelled'), RDF.type, OWL.Class))
        content = graph.serialize(format='xml', encoding='utf-8')
        metadata = {'ontology_name': 'Incomplete', 'original_filename': 'incomplete.rdf'}
        self.merge.catalog.read_artifact = lambda _: (metadata, content)
        preview = self.merge.preview({'source_ontology_ids': ['one', 'two']})
        self.assertFalse(preview['semantic_checks']['shacl_conforms'])
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.merge.apply(preview['preview_id'], 'steward')
        self.assertEqual(self.registration_calls, 0)

    def test_custom_shape_targets_are_preserved(self):
        from rdflib import Graph, URIRef, RDF, OWL
        from backend.ontology_service.merge_semantics import _validate_merge
        graph = Graph()
        graph.add((URIRef('urn:example:Part'), RDF.type, OWL.Class))
        shape = Path(self.directory.name) / 'custom.ttl'
        shape.write_text('''
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            <urn:custom:shape> a sh:NodeShape; sh:targetNode owl:Thing;
                sh:property [ sh:path rdfs:label; sh:minCount 1 ] .
        ''', encoding='utf-8')
        result = _validate_merge(graph, [{'shacl_file_path': str(shape)}])
        self.assertFalse(result['shacl_conforms'])
        self.assertIn('owl:Thing', result['report'])

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
        import importlib.util
        import httpx
        self.environment = patch.dict(os.environ, {'USE_LLM':'ollama', 'LLM_MODEL_NAME':'offline:latest',
            'OLLAMA_BASE_URL':'http://127.0.0.1:11434/api/chat', 'OLLAMA_DISCOVERY_ENABLED':'true'}, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.models=['offline:latest']; self.fails=False; self.delay=0
        owner=self
        async def handle(request):
            owner.url=str(request.url)
            await asyncio.sleep(owner.delay)
            if owner.fails: raise httpx.ConnectError('Fixture connection unavailable')
            return httpx.Response(200,json={'models':[{'name':model} for model in owner.models]})
        real_client=httpx.AsyncClient
        def client(**kwargs):
            owner.timeout=kwargs['timeout']
            return real_client(transport=httpx.MockTransport(handle),**kwargs)
        spec=importlib.util.spec_from_file_location('backend.agentic_service.fixture_local_llm', ROOT/'backend/agentic_service/local_llm.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.httpx=SimpleNamespace(**{**vars(httpx),'AsyncClient':client})
        self.scope=module.__dict__

    async def test_health_distinguishes_ready_missing_and_unavailable(self):
        self.assertEqual((await self.scope['health']())['status'], 'ready')
        self.assertEqual(self.url, 'http://127.0.0.1:11434/api/tags')
        self.assertLessEqual(self.timeout, 5)
        self.models = []
        self.assertEqual((await self.scope['health']())['status'], 'model_missing')
        self.fails = True
        self.assertEqual((await self.scope['health']())['status'], 'connection_failed')

    async def test_summary_is_bounded_and_nonstreaming(self):
        from backend.agentic_service.prompt_limits import bounded_prompt_json
        self.scope['bounded_prompt_json'] = bounded_prompt_json
        from backend.agentic_service.prompt_security import protect, prompt_identity, evidence_ids, validate_summary
        self.scope.update(protect=protect, prompt_identity=prompt_identity, evidence_ids=evidence_ids, validate_summary=validate_summary)
        async def post(client, endpoint, headers, body):
            self.request = body
            return {'done':True, 'message':{'content':'Bounded summary [evidence:1]'}}
        self.scope['_post_json'] = post
        self.assertEqual(await self.scope['summarize']('question', [{'resource_id': '1'}]), 'Bounded summary [evidence:1]')
        self.assertFalse(self.request['stream'])
        self.assertEqual(self.request['options']['num_predict'], 256)

    async def test_invalid_configuration_is_not_reported_ready(self):
        os.environ['LLM_REQUEST_TIMEOUT_SECONDS'] = '0'
        self.assertEqual((await self.scope['health']())['status'], 'invalid_configuration')

    async def test_slow_runtime_respects_total_diagnostic_deadline(self):
        os.environ['LLM_REQUEST_TIMEOUT_SECONDS'] = '1'
        self.delay = 2
        self.assertEqual((await self.scope['health']())['status'], 'timeout')


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
        from backend.ingestion_service import engineering_workflow as module
        with patch.object(module, 'service_bearer_headers', return_value={}), \
                patch.object(module.httpx, 'AsyncClient', return_value=Client()), \
                patch.object(module, 'run_in_threadpool', side_effect=offload):
            workflow = module.EngineeringWorkflow(SimpleNamespace(convert=lambda **kwargs: conversion))
            workflow._governance_entities = lambda _: []
            await workflow._run(filename='example.xsd', content=b'xsd')
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
