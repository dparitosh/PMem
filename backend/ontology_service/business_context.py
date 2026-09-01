"""Persistent DEPO business-object context backed by Semantica ContextGraph."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from semantica.context import ContextGraph


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:/#-]{0,255}$")


class BusinessContextService:
    """Own the domain context graph, not a second hand-built graph engine."""

    def __init__(self, root: Path) -> None:
        self.path = root / "business_context_graph.json"
        self.graph = ContextGraph(advanced_analytics=True)
        if self.path.exists():
            self.graph.load_from_file(self.path)

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        return {"engine": "Semantica ContextGraph", "persistence": str(self.path), **self.graph.stats()}

    def get(self, object_id: str, hops: int = 2, limit: int = 200) -> dict[str, Any]:
        self._validate_id(object_id)
        node = self.graph.find_node(object_id)
        if node is None:
            raise ValueError("Business object not found")
        return {"node": node, "neighbors": self.graph.get_neighbor_distances(object_id, hops=max(1, min(hops, 8)))[:limit]}

    def where_used(self, object_id: str, limit: int = 200) -> dict[str, Any]:
        self._validate_id(object_id)
        if not self.graph.has_node(object_id):
            raise ValueError("Business object not found")
        incoming = [edge for edge in self.graph.find_edges() if edge["target"] == object_id][:limit]
        return {"object_id": object_id, "used_by": incoming, "count": len(incoming)}

    def search(self, query: str, limit: int = 50) -> dict[str, Any]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("query is required")
        return {"query": query, "results": self.graph.query(query, limit=max(1, min(limit, 200)))}

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        self.graph.save_to_file(temporary)
        temporary.replace(self.path)

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
