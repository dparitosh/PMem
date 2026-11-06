"""Durable generated Turtle cache, with read compatibility for older installs."""
import os
import re
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPOSITORY_ROOT / "backend" / "ttl_cache"


def cache_root():
    return Path(os.getenv("ARTIFACT_STORAGE") or REPOSITORY_ROOT / "data" / "artifacts") / "ttl_cache"


def cache_path(task_id, root=None):
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
        raise ValueError("Invalid Turtle cache task ID")
    directory = cache_root() if root is None else Path(root)
    path = directory / f"{task_id}.ttl"
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Turtle cache path escapes its storage directory")
    return path


def write_ttl(task_id, ttl):
    destination = cache_path(task_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(ttl)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_ttl(task_id):
    current = cache_path(task_id)
    if current.is_file():
        return current.read_text(encoding="utf-8")
    legacy = cache_path(task_id, LEGACY_ROOT)
    if legacy.is_file():
        # Retain the legacy copy; operators may still run the previous release.
        return legacy.read_text(encoding="utf-8")
    return None
