import ast
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, AsyncMock
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry


def load(path, names, scope):
    tree=ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes=[node for node in tree.body if getattr(node,'name','') in names]
    for node in nodes:
        if hasattr(node,'decorator_list'): node.decorator_list=[]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),path,'exec'),scope)
    return scope


class IndustrialGovernanceTests(unittest.TestCase):
    def test_metadata_creation_uses_authenticated_actor_not_owner(self):
        graph=SimpleNamespace(query=Mock(return_value=[{'asset':{'asset_id':'asset'}}]))
        scope=dict(MetadataAssetRequest=object,Depends=lambda fn:None,_metadata_registry_identity=lambda:None,
            graph=graph,_now=lambda:'now',uuid4=lambda:'event',_ensure_metadata_constraints=Mock(),
            _asset_mutation_query=lambda _: 'CREATE (a:MetadataAsset)',_row_asset=lambda row:row['asset'],
            metadata_backend=SimpleNamespace(enabled=lambda:False),HTTPException=HTTPException)
        load('backend/routes/metadata_registry_routes.py',{'create_metadata_asset'},scope)
        request=SimpleNamespace(asset_id='asset',persistent_id='',owner='spoofed',model_dump=lambda:{'name':'Part','owner':'spoofed'})
        scope['create_metadata_asset'](request,actor='verified-steward')
        self.assertEqual(graph.query.call_args.kwargs['params']['actor'],'verified-steward')

    def test_context_lookup_supports_mixed_labels_and_rejects_ambiguity(self):
        scope=dict(__name__='backend.graph_service.context_router',__package__='backend.graph_service',Any=Any,HTTPException=HTTPException,publisher=SimpleNamespace(_session_rows=Mock(return_value=[{'id':'a','name':'Part'},{'id':'b','name':'Part'}])))
        load('backend/graph_service/context_router.py',{'_ontology_node_clause','_find_node'},scope)
        scope['publisher'].search=Mock(return_value={'nodes':[{'elementId':value,'properties':{'name':'Part'}} for value in ('a','b')]})
        clause=scope['_ontology_node_clause']()
        self.assertIn('n:OntologyResource',clause)
        self.assertIn('n:OntologyClass',clause)
        with self.assertRaises(HTTPException) as error: scope['_find_node']('Part')
        self.assertEqual(error.exception.status_code,409)
        scope['publisher']._session_rows.return_value=[{'id':'a','name':'Part'}]
        self.assertEqual(scope['_find_node']('',node_id='a')['id'],'a')

    def vocabulary(self):
        import re
        scope=dict(Any=Any,URIRef=str,_ID=re.compile(r'[a-z][a-z0-9-]{2,62}$'),
            _SEMVER=re.compile(r'\d+\.\d+\.\d+$'),datetime=datetime,timezone=timezone,
            _TRANSITIONS={'draft':{'in_review'},'in_review':{'approved'}},
            SemanticTaxonomyService=SimpleNamespace(validate=lambda concepts:{'valid':True},to_dict=lambda value:value),
            normalize_skos_payload=lambda payload:(SimpleNamespace(scheme_id='parts',version='1.0.0',pref_label='Parts',definition=''),[]))
        load('backend/ontology_service/vocabulary_service.py',{'VocabularyService'},scope)
        service=scope['VocabularyService'].__new__(scope['VocabularyService'])
        service.store=InMemoryRegistry()
        return service

    def test_vocabulary_create_is_atomic_even_after_stale_absence_check(self):
        service=self.vocabulary()
        service.store.get=Mock(return_value=None)
        payload={'base_uri':'https://example.org/parts/','steward':'owner','provenance':{'source':'engineering','rationale':'test'}}
        service.create(payload,'verified')
        with self.assertRaises(FileExistsError): service.create(payload,'other')
        self.assertEqual(service.store.values['parts:1.0.0']['provenance']['created_by'],'verified')

    def test_vocabulary_review_rejects_lost_update(self):
        service=self.vocabulary()
        service.store.put('parts:1.0.0',{'lifecycle_status':'draft','history':[]})
        service.store.compare_and_put=Mock(return_value=False)
        with self.assertRaisesRegex(ValueError,'changed during review'):
            service.transition('parts','1.0.0','in_review','verified','review')
        self.assertEqual(service.get('parts','1.0.0')['history'],[])

    def test_vocabulary_retry_reuses_retained_artifact_and_publication_identity(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'vocab.ttl'; path.write_bytes(b'vocabulary')
            store=InMemoryRegistry()
            store.put('parts:1.0.0',{'lifecycle_status':'approved','publication_status':'not_published'})
            artifact={'artifact_id':'sha256:fixture','filename':'vocab.ttl'}
            source=SimpleNamespace(store=store,key=lambda s,v:f'{s}:{v}',get=lambda s,v:store.get(f'{s}:{v}'),
                publication_artifact=Mock(return_value=(artifact,b'vocabulary')),
                artifacts=SimpleNamespace(resolve=lambda _: (artifact,path)),mark_published=Mock(return_value={'status':'published'}))
            dispatch=AsyncMock(side_effect=[TimeoutError('response lost'),{'status':'published'}])
            scope=dict(vocabularies=source,asyncio=asyncio,_publish=dispatch)
            import hashlib
            scope['hashlib']=hashlib
            load('backend/ontology_service/vocabulary_publication.py',{'publish','valid_receipt'},scope)
            with self.assertRaises(TimeoutError): scope['publish']('parts','1.0.0','verified')
            first=store.get('parts:1.0.0')['publication_attempt']
            scope['publish']('parts','1.0.0','verified')
            source.publication_artifact.assert_called_once()
            self.assertEqual(dispatch.call_args.args[0],first)
            self.assertFalse(scope['valid_receipt']({'status':'published','current':True},first))
