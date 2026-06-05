"""Compatibility package for the refactored backend application.

The runnable FastAPI package lives in ``backend/backend``. Some test runners
import this outer directory as ``backend`` first, so expose the inner package
path here as well.
"""

from pathlib import Path

_inner_package = Path(__file__).resolve().parent / "backend"
if _inner_package.is_dir() and "__path__" in globals():
    _inner_path = str(_inner_package)
    if _inner_path not in __path__:
        __path__.append(_inner_path)
