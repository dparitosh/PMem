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
