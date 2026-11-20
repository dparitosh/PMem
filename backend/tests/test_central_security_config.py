from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from backend.depo_platform.authorization import require_active_token, token_actor
from backend.depo_platform.service_runtime import allowed_origins


def test_origins_have_no_implicit_hosts(monkeypatch):
    monkeypatch.delenv('ALLOWED_ORIGINS', raising=False)
    assert allowed_origins() == []
    monkeypatch.setenv('ALLOWED_ORIGINS', 'http://customer.example:3000')
    assert allowed_origins() == ['http://customer.example:3000']


@pytest.mark.parametrize('origin', ['*', 'http:////broken', 'http://host/path', 'http://user:pass@host', 'http://host:bad'])
def test_invalid_origins_rejected(monkeypatch, origin):
    monkeypatch.setenv('ALLOWED_ORIGINS', origin)
    with pytest.raises(RuntimeError):
        allowed_origins()


def test_key_expiration_and_override(monkeypatch):
    monkeypatch.setenv('DEPO_TOKEN_EXPIRES_AT', '2000-01-01T00:00:00Z')
    monkeypatch.delenv('GRAPH_READ_TOKEN_EXPIRES_AT', raising=False)
    with pytest.raises(HTTPException) as expired:
        require_active_token('GRAPH_READ_TOKEN')
    assert expired.value.status_code == 401
    monkeypatch.setenv('GRAPH_READ_TOKEN_EXPIRES_AT', (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    require_active_token('GRAPH_READ_TOKEN')
    monkeypatch.setenv('GRAPH_READ_TOKEN_EXPIRES_AT', '2030-01-01')
    with pytest.raises(HTTPException) as invalid:
        require_active_token('GRAPH_READ_TOKEN')
    assert invalid.value.status_code == 503


def test_server_actor_overrides_caller(monkeypatch):
    monkeypatch.setenv('GRAPH_READ_TOKEN_ACTOR', 'customer-reader')
    assert token_actor('GRAPH_READ_TOKEN', 'caller-name') == 'customer-reader'
    monkeypatch.delenv('GRAPH_READ_TOKEN_ACTOR')
    monkeypatch.setenv('DEPO_REQUIRE_TOKEN_ACTOR', 'true')
    with pytest.raises(HTTPException):
        token_actor('GRAPH_READ_TOKEN', 'caller-name')

def test_environment_approval_identity_is_not_supplied_by_caller(monkeypatch):
    from backend.depo_platform.authorization import approval_identity
    from starlette.requests import Request
    monkeypatch.setenv('AUTH_MODE','token')
    monkeypatch.setattr('backend.depo_platform.credentials.uses_postgres',lambda:False)
    monkeypatch.setenv('DATA_JOB_APPROVAL_TOKEN','test-only-key')
    monkeypatch.delenv('DATA_JOB_APPROVAL_TOKEN_ACTOR',raising=False)
    monkeypatch.delenv('DEPO_REQUIRE_TOKEN_ACTOR',raising=False)
    monkeypatch.delenv('DATA_JOB_APPROVAL_TOKEN_EXPIRES_AT',raising=False)
    monkeypatch.delenv('DEPO_TOKEN_EXPIRES_AT',raising=False)
    request=Request({'type':'http','headers':[(b'authorization',b'Bearer test-only-key')],'client':('127.0.0.1',1)})
    assert approval_identity(request,{'approved_by':'spoofed-person'},token_env='DATA_JOB_APPROVAL_TOKEN')=='credential:DATA_JOB_APPROVAL_TOKEN'
    assert approval_identity(request,{},token_env='DATA_JOB_APPROVAL_TOKEN')=='credential:DATA_JOB_APPROVAL_TOKEN'
    monkeypatch.setenv('DATA_JOB_APPROVAL_TOKEN_ACTOR','registered-owner')
    assert approval_identity(request,{'approved_by':'spoofed-person'},token_env='DATA_JOB_APPROVAL_TOKEN')=='registered-owner'


def test_postgres_approval_requires_credential_but_not_typed_identity(monkeypatch):
    from backend.depo_platform.authorization import approval_identity
    from starlette.requests import Request
    monkeypatch.setenv('AUTH_MODE','token')
    monkeypatch.setattr('backend.depo_platform.credentials.uses_postgres',lambda:True)
    calls=[]
    def verify(profile,key):
        calls.append((profile,key));return 'registered-person'
    monkeypatch.setattr('backend.depo_platform.credentials.verify_key',verify)
    request=Request({'type':'http','headers':[(b'authorization',b'Bearer test-only-key')],'client':('127.0.0.1',1)})
    assert approval_identity(request,{},token_env='DATA_JOB_APPROVAL_TOKEN')=='registered-person'
    assert calls==[('DATA_JOB_APPROVAL_TOKEN','test-only-key')]
