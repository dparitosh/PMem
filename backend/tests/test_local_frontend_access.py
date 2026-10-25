import json
import socket
import tempfile
import threading
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch
import httpx
from http.server import ThreadingHTTPServer
from backend.depo_platform.frontend_server import FrontendHandler, allowed_request, configuration, COOKIE, PREFIX, validate_delegate

class LocalFrontendAccessTests(unittest.TestCase):
    def test_manual_is_default_and_local_rejects_network_or_gateway_deployments(self):
        self.assertEqual(configuration({}, '0.0.0.0')['mode'], 'manual')
        values={'DEPO_BROWSER_AUTH_MODE':'local','ADMIN_API_KEY':'server-secret'}
        for bind, extra in [('0.0.0.0',{}), ('localhost',{}), ('127.0.0.1',{'DEPO_ROUTING_MODE':'apim'}),
                            ('127.0.0.1',{'DEPO_LOCAL_SESSION_AUTHORITY_URL':'http://example.test'}),
                            ('127.0.0.1',{'VITE_API_GATEWAY_URL':'https://gateway.test'})]:
            with self.subTest(bind=bind, extra=extra), self.assertRaises(ValueError): configuration({**values,**extra},bind)
        self.assertFalse(configuration(values,'127.0.0.1')['writes'])

    def test_read_only_scope_and_expiry_are_enforced(self):
        body = {'token':'depo_session_valid_opaque_token','profiles':['GRAPH_READ_TOKEN'],
                'expires_at':'2099-01-01T00:00:00Z','absolute_expires_at':'2099-01-02T00:00:00Z'}
        self.assertEqual(validate_delegate(body, False), body)
        for change in [{'profiles':['GRAPH_READ_TOKEN','ONTOLOGY_APPROVAL_TOKEN']},
                       {'profiles':['GRAPH_READ_TOKEN','ADMIN_API_KEY']},
                       {'profiles':['GRAPH_READ_TOKEN','UNKNOWN_TOKEN']},
                       {'profiles':['GRAPH_READ_TOKEN','GRAPH_READ_TOKEN']},
                       {'expires_at':'2000-01-01T00:00:00Z'}, {'expires_at':'invalid'},
                       {'expires_at':'2099-01-03T00:00:00Z'}, {'token':'bad'}]:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                validate_delegate({**body, **change}, False)
        self.assertIn('ONTOLOGY_APPROVAL_TOKEN',validate_delegate({**body,'profiles':['GRAPH_READ_TOKEN','ONTOLOGY_APPROVAL_TOKEN']},True)['profiles'])
        with self.assertRaises(ValueError):
            configuration({'DEPO_BROWSER_AUTH_MODE':'local','ADMIN_API_KEY':'secret',
                           'DEPO_LOCAL_SESSION_AUTHORITY_URL':'http://127.0.0.1:bad'},'127.0.0.1')

    def test_mutation_requires_loopback_host_origin_and_launcher_cookie(self):
        good=dict(client='127.0.0.1',host='127.0.0.1:3000',origin='http://127.0.0.1:3000',port=3000,
                  cookie=f'{COOKIE}=cap',capability='cap',mutation=True,fetch_site='same-origin')
        self.assertTrue(allowed_request(**good))
        for change in [{'client':'192.0.2.5'},{'host':'rebind.example:3000'},{'origin':'https://attacker.test'},
                       {'origin':''},{'cookie':''},{'cookie':f'{COOKIE}=wrong'},{'fetch_site':'cross-site'}]:
            with self.subTest(change=change): self.assertFalse(allowed_request(**{**good,**change}))

    def test_http_broker_hides_admin_key_and_never_grants_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(FrontendHandler,directory=directory))
            server.local_settings=configuration({'DEPO_BROWSER_AUTH_MODE':'local','ADMIN_API_KEY':'server-secret','DEPO_LOCAL_BROWSER_WRITES':'true'},'127.0.0.1')
            server.capability='launch-capability'
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            url=f'http://127.0.0.1:{server.server_port}'
            upstream=httpx.Response(200,json={'token':'depo_session_opaque_valid_token','profiles':['GRAPH_READ_TOKEN'],
                                            'expires_at':'2099-01-01T00:00:00+00:00','absolute_expires_at':'2099-01-02T00:00:00+00:00','ignored':'server-secret'})
            with httpx.Client(base_url=url,trust_env=False) as client:
                response=client.get(PREFIX+'config')
                self.assertEqual(response.status_code,200)
                self.assertIn('HttpOnly',response.headers['set-cookie'])
                self.assertIn('SameSite=Strict',response.headers['set-cookie'])
                with patch('httpx.stream') as exchange:
                    exchange.return_value.__enter__.return_value = upstream
                    self.assertEqual(client.post(PREFIX+'session',headers={'Origin':'https://attacker.test'}).status_code,403)
                    exchange.assert_not_called()
                    response=client.post(PREFIX+'session',headers={'Origin':url,'Sec-Fetch-Site':'same-origin'})
                self.assertEqual(response.status_code,200)
                self.assertNotIn('server-secret',response.text)
                self.assertEqual(exchange.call_args.kwargs['json'],{'include_writes':True,'include_maintenance':False})
                self.assertFalse(exchange.call_args.kwargs['follow_redirects'])
                self.assertFalse(exchange.call_args.kwargs['trust_env'])
                self.assertEqual(client.get(PREFIX+'config',headers={'Host':'evil.test'}).status_code,403)
                with patch('httpx.stream') as exchange:
                    response=client.post(PREFIX+'session',headers={'Origin':url},content='x'*65)
                    self.assertEqual(response.status_code,400)
                    exchange.assert_not_called()
                    exchange.return_value.__enter__.return_value=httpx.Response(200,content=b'x'*16385)
                    self.assertEqual(client.post(PREFIX+'session',headers={'Origin':url}).status_code,503)
                    exchange.side_effect=httpx.ReadTimeout('private upstream details')
                    response=client.post(PREFIX+'session',headers={'Origin':url})
                    self.assertEqual(response.status_code,503)
                    self.assertNotIn('private upstream details',response.text)
                self.assertEqual(client.get('/').status_code,403)

    def test_absolute_request_deadline_closes_stalled_header_read(self):
        with tempfile.TemporaryDirectory() as directory:
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(FrontendHandler,directory=directory))
            server.request_deadline_seconds=0.1
            server.local_settings={'mode':'manual','writes':False}
            server.capability='unused'
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
            with socket.create_connection(server.server_address,timeout=2) as client:
                client.sendall(b'GET / HTTP/1.1\r\nHost:')
                self.assertEqual(client.recv(1),b'')



def test_startup_probe_checks_business_reads_and_revokes_its_session(monkeypatch):
    from backend.depo_platform.frontend_server import verify_local_access
    seen=[]
    def handle(request):
        seen.append((request.method,request.url.path))
        if request.url.path.endswith('/config'):return httpx.Response(200,json={'mode':'local','writes':False})
        if request.url.path.endswith('/session'):
            return httpx.Response(200,json={'token':'depo_session_opaque_valid_token','profiles':['GRAPH_READ_TOKEN'],
                'expires_at':'2099-01-01T00:00:00Z','absolute_expires_at':'2099-01-02T00:00:00Z'})
        return httpx.Response(200,json={})
    real=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    assert verify_local_access('http://127.0.0.1:3000','http://127.0.0.1:8011')['status']=='ok'
    assert ('GET','/api/v1/ontologies/health') in seen
    assert ('GET','/api/v1/ontologies') in seen
    assert seen[-1]==('DELETE','/auth/browser-session')


if __name__ == '__main__': unittest.main()
