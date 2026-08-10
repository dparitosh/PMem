from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request


class _ChunkedUpload:
    def __init__(self, chunks: list[bytes]):
        self._chunks = iter(chunks)

    async def read(self, _size: int = -1) -> bytes:
        return next(self._chunks, b"")


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/reset-database",
            "headers": headers or [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
async def test_main_upload_reader_rejects_before_unbounded_buffering():
    from backend.main import _read_upload_with_limit

    with pytest.raises(HTTPException) as exc_info:
        await _read_upload_with_limit(_ChunkedUpload([b"1234", b"5678"]), 7)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_admin_key_is_required_for_destructive_routes(monkeypatch):
    from backend.routes.admin_routes import require_admin_api_key

    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_api_key(_request())
    assert exc_info.value.status_code == 503

    monkeypatch.setenv("APP_ENV", "development")
    await require_admin_api_key(_request())

    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_api_key(_request([(b"x-api-key", b"wrong")]))
    assert exc_info.value.status_code == 401

    await require_admin_api_key(_request([(b"x-api-key", b"test-admin-key")]))


def test_destructive_admin_routes_have_auth_dependencies():
    from backend.routes.admin_routes import router

    protected = {
        route.path: route
        for route in router.routes
        if route.path in {"/admin/clean-schema", "/admin/delete-data", "/admin/reset-database", "/admin/clear-cache"}
    }
    assert set(protected) == {
        "/admin/clean-schema",
        "/admin/delete-data",
        "/admin/reset-database",
        "/admin/clear-cache",
    }
    assert all(route.dependant.dependencies for route in protected.values())
