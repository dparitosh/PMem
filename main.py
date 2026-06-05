"""Repository-level shim exposing the FastAPI `app` for tests that import `main`.

This file intentionally re-exports `app` from the backend package so tests
that import `main` (for convenience) can resolve the application.
"""
from backend.main import app  # re-export for tests

__all__ = ["app"]
