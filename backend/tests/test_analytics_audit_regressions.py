import ast, asyncio, unittest
from pathlib import Path
from types import SimpleNamespace
from backend.Services.schema_upload_paths import validate_schema_upload

class AuditRegressions(unittest.TestCase):
    def test_upload_paths(self):
        for filename in ('../a.xsd', 'C:/a.xsd', r'..\a.xsd', '/a.xsd'):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                validate_schema_upload(filename, b'')
        root=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="types/child.xsd"/></xs:schema>'
        child=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
        self.assertEqual(validate_schema_upload('root.xsd',root,{'types/child.xsd':child}),{'types/child.xsd':child})
        with self.assertRaises(ValueError):
            validate_schema_upload('root.xsd',root.replace(b'types/child.xsd',b'../outside.xsd'))

    def test_owl_engine_receives_nested_dependencies(self):
        import tempfile, sys
        from unittest.mock import patch
        tree=ast.parse(Path('backend/Services/owl_generation_service.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OWLGenerationService')
        node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='generate_owl_from_xsd')
        node.decorator_list=[]
        content=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="types/part.xsd"/></xs:schema>'
        dependency=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
        def engine(cfg):
            self.assertEqual((Path(cfg.schema_dir)/'types/part.xsd').read_bytes(),dependency)
            self.assertEqual(cfg.target_files,['root'])
            return 'result'
        ns={'__name__':'backend.Services.owl_generation_service','Path':Path,'tempfile':tempfile,'Optional':__import__('typing').Optional,
            'Tuple':__import__('typing').Tuple,'Dict':__import__('typing').Dict,'Any':object,
            '_extract_xsd_target_namespace':lambda c:'urn:test','_derive_prefix_from_namespace':lambda *a,**kw:'test',
            '_normalize_base_uri':lambda *a,**kw:'urn:test:','_read_and_validate':lambda p:('turtle',{}),
            '_inspect_with_owlready':lambda *a:{},'logger':SimpleNamespace(error=lambda *a:None)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'owl','exec'),ns)
        module=SimpleNamespace(convert_xsd_to_owl=engine,minimal_config=lambda **kw:SimpleNamespace(**kw))
        with patch.dict(sys.modules,{'backend.Services.owl_xsd_engine':module}):
            self.assertEqual(ns['generate_owl_from_xsd'](content,'root.xsd',schema_files={'types/part.xsd':dependency})[0],'turtle')

    def test_legacy_catalog_shape(self):
        tree=ast.parse(Path('backend/data_product_service/router.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_catalog_payload')
        ns={}; exec(compile(ast.Module(body=[node],type_ignores=[]),'catalog','exec'),ns)
        old=ns['_catalog_payload']({'product_id':'test','version':'1.0.0'})
        self.assertNotIn('product_kind',old); self.assertNotIn('analytics_readiness',old)
        new=ns['_catalog_payload']({'product_id':'test','version':'1.0.0','product_kind':'schema-design-evidence'})
        self.assertEqual(new['product_kind'],'schema-design-evidence')

    def test_malformed_registry_is_controlled(self):
        tree=ast.parse(Path('backend/depo_platform/semantic_registry.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef))
        class Client:
            def __init__(self,**kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def get(self,*args,**kw): return response
        for value in (None, [], [['version','1.0.0']], {}, {'version':4,'lifecycle_status':'approved'}):
            response=SimpleNamespace(status_code=200,is_error=False,json=lambda:value)
            ns={'Any':object,'release_reference':lambda v:v,'service_url':lambda *a:'http://test','quote':lambda v,**kw:v,
                'service_bearer_headers':lambda *a,**kw:{},'httpx':SimpleNamespace(AsyncClient=Client,HTTPError=OSError)}
            exec(compile(ast.Module(body=[node],type_ignores=[]),'registry','exec'),ns)
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                asyncio.run(ns['resolve_approved_release']({'asset_id':'test','version':'1.0.0'}))

if __name__=='__main__': unittest.main()
