"""Persistent DEPO business-object context backed by Semantica ContextGraph."""
from __future__ import annotations

import re
import json
import tempfile
from pathlib import Path
from typing import Any

from semantica.context import ContextGraph
from backend.mesh_store import PostgresRegistry


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:/#-]{0,255}$")


class BusinessContextService:
    """Own Semantica ContextGraph state in PostgreSQL, not local JSON files."""
    _STATE_KEY = "context_graph"

    def __init__(self, root: Path, registry: Any | None = None) -> None:
        self.registry = registry or PostgresRegistry("ontology_business_context")
        self.graph = ContextGraph(advanced_analytics=True)
        self.root = root
        self._loaded = False
        self._persistence_error = ""

    def _load_persisted_state(self, *, require_persistence: bool = False) -> None:
        """Load state lazily so OpenAPI/service startup has no database side effect."""
        if self._loaded:
            return
        try:
            state = self.registry.get(self._STATE_KEY)
        except RuntimeError as exc:
            self._persistence_error = str(exc)
            if require_persistence:
                raise
            return
        legacy_path = self.root / "business_context_graph.json"
        if state is None and legacy_path.is_file():
            try:
                state = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Legacy business context is unreadable: {exc}") from exc
            if isinstance(state, dict):
                self.registry.put(self._STATE_KEY, state)
        if state:
            self._load(state)
        self._loaded = True

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Serialize cooperating writers and reload under the lock. Never mutate
        # the shared in-process graph before validation and persistence succeed.
        with self.registry.advisory_lock(self._STATE_KEY) as acquired:
            if not acquired:
                raise RuntimeError("Business context update in progress; retry")
            staged = BusinessContextService(self.root, registry=self.registry)
            result = staged._upsert(payload)
            self.graph = staged.graph
            self._loaded = True
            self._persistence_error = ""
            return result

    def _upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._load_persisted_state(require_persistence=True)
        nodes = list(payload.get("nodes") or [])
        edges = list(payload.get("relationships") or payload.get("edges") or [])
        if not nodes and not edges:
            raise ValueError("At least one business-object node or relationship is required")
        normalized_nodes = [self._node(item) for item in nodes]
        for node in normalized_nodes:
            self.graph.add_node(node["id"], node["type"], node["content"], **node["properties"])
        normalized_edges = [self._edge(item) for item in edges]
        missing = sorted({endpoint for edge in normalized_edges for endpoint in (edge["source"], edge["target"])
                          if not self.graph.has_node(endpoint)})
        if missing:
            raise ValueError(f"Relationships reference unknown business objects: {', '.join(missing)}")
        for edge in normalized_edges:
            self.graph.add_edge(edge["source"], edge["target"], edge["type"], edge["weight"], **edge["metadata"])
        self._save()
        return {"nodes_received": len(normalized_nodes), "relationships_received": len(normalized_edges),
                "context": self.summary()}

    def summary(self) -> dict[str, Any]:
        self._load_persisted_state()
        return {
            "engine": "Semantica ContextGraph",
            "persistence": "postgres" if not self._persistence_error else "unavailable",
            "persistence_error": self._persistence_error or None,
            **self.graph.stats(),
        }

    def get(self, object_id: str, hops: int = 2, limit: int = 200) -> dict[str, Any]:
        self._load_persisted_state()
        self._validate_id(object_id)
        node = self.graph.find_node(object_id)
        if node is None:
            raise ValueError("Business object not found")
        return {"node": node, "neighbors": self.graph.get_neighbor_distances(object_id, hops=max(1, min(hops, 8)))[:limit]}

    def where_used(self, object_id: str, limit: int = 200) -> dict[str, Any]:
        self._load_persisted_state()
        self._validate_id(object_id)
        if not self.graph.has_node(object_id):
            raise ValueError("Business object not found")
        incoming = [edge for edge in self.graph.find_edges() if edge["target"] == object_id][:limit]
        return {"object_id": object_id, "used_by": incoming, "count": len(incoming)}

    def search(self, query: str, limit: int = 50) -> dict[str, Any]:
        self._load_persisted_state()
        query = str(query or "").strip()
        if not query:
            raise ValueError("query is required")
        return {"query": query, "results": self.graph.query(query, limit=max(1, min(limit, 200)))}

    def _save(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            self.graph.save_to_file(temporary)
            self.registry.put(self._STATE_KEY, json.loads(temporary.read_text(encoding="utf-8")))
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self, state: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as stream:
            json.dump(state, stream)
            temporary = Path(stream.name)
        try:
            self.graph.load_from_file(temporary)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate_id(value: str) -> None:
        if not _ID.fullmatch(str(value or "")):
            raise ValueError("Business-object id must be a safe URI-like identifier")

    def _node(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("Each node must be an object")
        identifier = str(item.get("id") or item.get("object_id") or "")
        self._validate_id(identifier)
        object_type = str(item.get("type") or item.get("object_type") or "BusinessObject")
        content = str(item.get("name") or item.get("label") or identifier)
        properties = dict(item.get("properties") or {})
        # Preserve ontology, source and lifecycle links as Semantica metadata.
        for key in ("ontology_class", "source_artifact", "version", "oslc_uri", "lifecycle_state"):
            if item.get(key) is not None:
                properties[key] = item[key]
        return {"id": identifier, "type": object_type, "content": content, "properties": properties}

    def _edge(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("Each relationship must be an object")
        source, target = str(item.get("source") or item.get("source_id") or ""), str(item.get("target") or item.get("target_id") or "")
        self._validate_id(source); self._validate_id(target)
        return {"source": source, "target": target, "type": str(item.get("type") or item.get("relationship_type") or "RELATED_TO"),
                "weight": float(item.get("weight", 1.0)), "metadata": dict(item.get("metadata") or item.get("properties") or {})}
