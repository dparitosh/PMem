"""Small durable JSON registry shared by mesh control-plane services."""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any

class JsonRegistry:
    def __init__(self, path: Path) -> None: self.path = path; path.parent.mkdir(parents=True, exist_ok=True); self.lock = threading.RLock()
    def all(self) -> dict[str, Any]:
        with self.lock:
            try: return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            except json.JSONDecodeError as exc: raise RuntimeError(f"Registry is unreadable: {self.path}") from exc
    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            values = self.all(); values[key] = value; temporary = self.path.with_suffix(".tmp"); temporary.write_text(json.dumps(values, indent=2), encoding="utf-8"); temporary.replace(self.path); return value
