"""Small durable JSON registry shared by mesh control-plane services."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

class JsonRegistry:
    def __init__(self, path: Path) -> None: self.path = path; path.parent.mkdir(parents=True, exist_ok=True)
    def all(self) -> dict[str, Any]: return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        values = self.all(); values[key] = value; temporary = self.path.with_suffix(".tmp"); temporary.write_text(json.dumps(values, indent=2), encoding="utf-8"); temporary.replace(self.path); return value
