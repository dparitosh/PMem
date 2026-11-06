"""A slow graph registry read must not block the ingestion event loop."""
import threading
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_slow_registry_read_keeps_unrelated_requests_responsive(monkeypatch):
 from backend.Services import unified_import_router as module
 import sys
 monkeypatch.setitem(sys.modules,'core.graph',SimpleNamespace(graph=None))
 started=threading.Event();release=threading.Event()
 def slow(graph):
  started.set();release.wait(3);return {'ontologies':[]}
 monkeypatch.setattr(module.OntologyUploadManager,'list_ontologies_with_neo4j_counts',slow)
 app=FastAPI();app.add_api_route('/registry',module.list_registered_ontologies)
 @app.get('/probe')
 async def probe():return {'status':'ready'}
 with TestClient(app) as client,ThreadPoolExecutor(max_workers=1) as executor:
  result=executor.submit(client.get,'/registry')
  try:
   assert started.wait(2)
   begin=time.monotonic();assert client.get('/probe').status_code==200
   assert time.monotonic()-begin<1
  finally:release.set()
  assert result.result(timeout=3).status_code==200
