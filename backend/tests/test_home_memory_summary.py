"""Home memory uses the existing owner boundary, before scope/identity limits."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.agentic_service import router as module

class Cursor:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params=None): self.calls.append((query, params))
    def fetchall(self): return [({'job_id':'old-turn','user_request':'Bearing?','graph_context':{'ontology':'parts'},'response':'private answer','evidence':['private evidence']},)]
class Database:
    def __init__(self, cursor): self.value = cursor
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def transaction(self): return self
    def cursor(self): return self.value

def test_scope_and_owner_are_applied_before_limit_and_summary_excludes_answer(monkeypatch):
    cursor = Cursor()
    class Store:
        namespace = 'agentic_companion_jobs'
        def __init__(self, namespace): pass
        def _connect(self): return Database(cursor)
    monkeypatch.setattr(module, 'PostgresRegistry', Store)
    report = module._memory_report('owner-a', 'parts', 'old-turn', 3, True)
    query, params = cursor.calls[-1]
    assert params == ['agentic_companion_jobs','owner-a','parts','old-turn',3]
    assert query.index("value->'graph_context'->>'ontology'=%s") < query.index('LIMIT %s')
    assert "value->>'owner'=%s" in query and "value->>'job_id'=%s" in query
    assert "value->'response'" not in query and "value->'evidence'" not in query
    assert 'response' not in report['records'][0] and 'evidence' not in report['records'][0]

def test_memory_query_bounds_are_validated_and_owner_is_not_a_client_parameter(monkeypatch):
    app = FastAPI(); app.include_router(module.router)
    app.dependency_overrides[module.graph_read_identity] = lambda: 'reader'
    monkeypatch.setattr(module, 'graph_read_identity', lambda request: 'reader')
    monkeypatch.setattr(module.sessions, 'owner', lambda request, actor: 'owner-a')
    calls=[]
    monkeypatch.setattr(module, '_memory_report', lambda *args: calls.append(args) or {'records':[]})
    client=TestClient(app)
    assert client.get('/api/v1/memory/records?limit=26').status_code == 422
    assert client.get('/api/v1/memory/records?limit=0').status_code == 422
    assert client.get('/api/v1/memory/records?ontology_id=parts&job_id=old-turn&limit=3&summary=true&owner=other').status_code == 200
    assert calls[-1] == ('owner-a','parts','old-turn',3,True)
