"""Optional FastAPI compatibility adapter for the existing Depo frontend."""

from .depo_compat_router import create_depo_compat_router

__all__ = ["create_depo_compat_router"]
