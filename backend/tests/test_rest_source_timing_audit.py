"""Real child-process deadline tests; no external calls or credentials."""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from backend.data_pipeline_service import rest_sources


def test_response_deadline_interrupts_small_slow_chunks(monkeypatch):
    connected=threading.Event()
    class SlowResponse(BaseHTTPRequestHandler):
        def do_GET(self):
            connected.set()
            body=json.dumps([{'name':'Part'}]).encode()+b' '*1000
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:
                for offset in range(0,len(body),20):
                    self.wfile.write(body[offset:offset+20]);self.wfile.flush();time.sleep(.2)
            except (BrokenPipeError,ConnectionResetError): pass
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),SlowResponse)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    # Only this fixture redirects the guarded transport to a local test server.
    code=f'''
import socket
from semantica.ingest import api_ingestor as a
old=socket.getaddrinfo
socket.getaddrinfo=lambda host,*args,**kw: [(2,1,6,'',('93.184.216.34',80))] if host=='api.example.com' else old(host,*args,**kw)
a.request_with_ssrf_guard=lambda method,url,session,allow_private_ips,**kw: session.request(method,'http://127.0.0.1:{server.server_port}/records',**kw)
from backend.data_pipeline_service.rest_fetch_worker import main
raise SystemExit(main())
'''
    monkeypatch.setattr(rest_sources,'_worker_command',lambda:[sys.executable,'-c',code])
    monkeypatch.setattr(rest_sources,'FETCH_TIMEOUT_SECONDS',2)
    monkeypatch.setenv('DEPO_REST_ALLOWED_HOSTS','api.example.com')
    started=time.monotonic()
    try:
        with pytest.raises(ValueError,match='absolute time limit'):
            rest_sources.fetch({'endpoint':'http://api.example.com/records'})
        assert connected.is_set(), 'Fixture must reach the real HTTP reader'
        assert time.monotonic()-started < 3.5
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def test_deadline_includes_blocked_dns_or_startup(monkeypatch):
    monkeypatch.setattr(rest_sources,'_worker_command',lambda:[sys.executable,'-c','import time; time.sleep(10)'])
    monkeypatch.setattr(rest_sources,'FETCH_TIMEOUT_SECONDS',.2)
    started=time.monotonic()
    with pytest.raises(ValueError,match='absolute time limit'): rest_sources.fetch({})
    assert time.monotonic()-started < 1.5


def test_real_worker_returns_safe_policy_error(monkeypatch):
    monkeypatch.setenv('DEPO_REST_ALLOWED_HOSTS','')
    with pytest.raises(ValueError,match='DEPO_REST_ALLOWED_HOSTS'):
        rest_sources.fetch({'endpoint':'https://not-allowed.example/records'})


def test_child_self_terminates_without_parent_deadline(monkeypatch):
    code="from backend.data_pipeline_service import rest_fetch_worker as w; import time; w.FETCH_TIMEOUT_SECONDS=.2; w._fetch_in_process=lambda *a,**k:time.sleep(10); raise SystemExit(w.main())"
    monkeypatch.setattr(rest_sources,'_worker_command',lambda:[sys.executable,'-c',code])
    started=time.monotonic()
    with pytest.raises(ValueError,match='absolute time limit'): rest_sources.fetch({'endpoint':'unused'})
    assert time.monotonic()-started < 2
