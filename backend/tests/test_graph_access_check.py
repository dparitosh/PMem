import ast, unittest, os, hmac
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from backend.depo_platform.openapi_contract import credential_profiles
class GraphAccessTest(unittest.TestCase):
    def test_access_requires_read_identity_without_graph_query(self):
        tree=ast.parse(Path('backend/graph_service/router.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='access')
        def graph_read_identity(): pass
        scope={'Depends':lambda dependency:dependency, 'graph_read_identity':graph_read_identity}
        node.decorator_list=[]
        exec(compile(ast.Module(body=[node],type_ignores=[]),'access','exec'),scope)
        self.assertEqual(scope['access']('reader'), {'status':'authorized','service':'graph'})
        self.assertEqual(scope['access'].__defaults__, (graph_read_identity,))
        self.assertEqual(credential_profiles(scope['access'], [graph_read_identity],method='GET',path='/graph/access'),['GRAPH_READ_TOKEN'])
    def test_authentication_distinguishes_configuration_header_and_mismatch(self):
        class HTTPException(Exception):
            def __init__(self, status_code, detail):
                self.status_code, self.detail = status_code, detail
        tree = ast.parse(Path('backend/depo_platform/authorization.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'_request_api_key', 'graph_read_identity'}]
        scope = {'os': os, 'hmac': hmac, 'Request': object, 'HTTPException': HTTPException,
                 'require_active_token': lambda key: None, 'token_actor': lambda key, fallback: fallback}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'authorization','exec'),scope)
        authorize = scope['graph_read_identity']
        with patch.dict(os.environ, {'AUTH_MODE':'token', 'GRAPH_READ_TOKEN':' correct '}, clear=True):
            self.assertEqual(authorize(SimpleNamespace(headers={'authorization':'Bearer correct'})), 'service-token-reader')
            for headers, message in [({}, 'header is missing'), ({'authorization':'Bearer wrong'}, 'does not match')]:
                with self.assertRaises(HTTPException) as caught:
                    authorize(SimpleNamespace(headers=headers))
                self.assertEqual(caught.exception.status_code, 403)
                self.assertIn(message, caught.exception.detail)
        with patch.dict(os.environ, {'AUTH_MODE':'token'}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                authorize(SimpleNamespace(headers={'authorization':'Bearer correct'}))
            self.assertEqual(caught.exception.status_code, 503)
            self.assertIn('not configured', caught.exception.detail)

    def test_frontend_checks_authorization_separately(self):
        shell=Path('frontend/src/app/AppShell.js').read_text(encoding='utf-8')
        self.assertIn('await graphApi.verifyAccess(apiKey);', shell)
        self.assertNotIn('await graphApi.getOverview(1);',shell)
if __name__=='__main__': unittest.main()
