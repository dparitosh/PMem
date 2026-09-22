"""Fail-closed, evidence-grounded retrieval for the Knowledge Companion."""
from __future__ import annotations

import os
import re
from typing import Any

import httpx


class KnowledgeCompanion:
    max_nodes = 900
    max_evidence = 12

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 3}

    @staticmethod
    def _graph_root() -> str:
        configured = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1").rstrip("/")
        return configured if configured.endswith("/api/v1") else f"{configured}/api/v1"

    async def ask(self, message: str, *, headers: dict | None = None) -> dict[str, Any]:
        query = " ".join(str(message or "").split())
        if not query:
            raise ValueError("message is required")
        endpoint = f"{self._graph_root()}/graph/search"
        try:
            async with httpx.AsyncClient(timeout=float(os.getenv("COMPANION_RETRIEVAL_TIMEOUT_SECONDS", "15"))) as client:
                if headers is None:
                    headers = {"Authorization": f"Bearer {os.environ['GRAPH_READ_TOKEN']}"} if os.getenv('GRAPH_READ_TOKEN') else {}
                response = await client.get(endpoint, params={"query": query, "limit": min(self.max_nodes, 200)}, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Knowledge graph retrieval is unavailable; no answer was generated") from exc
        graph = dict(response.json())
        nodes, relationships = list(graph.get("nodes") or []), list(graph.get("relationships") or [])
        query_tokens = self._tokens(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for node in nodes:
            properties = dict(node.get("properties") or {})
            text = " ".join(str(properties.get(key) or "") for key in ("label", "iri", "kind", "ontology_id"))
            score = int(properties.get("search_score") or len(query_tokens & self._tokens(text)))
            if score:
                scored.append((score, node))
        scored.sort(key=lambda item: (-item[0], str((item[1].get("properties") or {}).get("label") or item[1].get("elementId"))))
        selected = [node for _, node in scored[: min(8, self.max_evidence)]]
        selected_ids = {str(node.get("elementId")) for node in selected}
        edge_budget = max(0, self.max_evidence - len(selected))
        selected_edges = [edge for edge in relationships if str(edge.get("start")) in selected_ids or str(edge.get("end")) in selected_ids][:edge_budget]
        evidence = [
            {
                "evidence_type": "graph_resource", "resource_id": str(node.get("elementId") or ""),
                "label": str((node.get("properties") or {}).get("label") or node.get("elementId") or ""),
                "kind": str((node.get("properties") or {}).get("kind") or (node.get("labels") or ["resource"])[0]),
                "ontology_id": (node.get("properties") or {}).get("ontology_id"), "source": endpoint,
            }
            for node in selected
        ]
        evidence.extend({
            "evidence_type": "graph_relationship", "source_id": str(edge.get("start") or ""),
            "target_id": str(edge.get("end") or ""), "relationship": str(edge.get("type") or "RELATED_TO"), "source": endpoint,
        } for edge in selected_edges)
        retrieval = {"nodes_examined": len(nodes), "relationships_examined": len(relationships), "truncated": bool((graph.get("view") or {}).get("truncated"))}
        if not evidence:
            return {
                "status": "no_evidence", "answerable": False,
                "response": "No bounded graph evidence matched this question, so the companion did not generate an answer.",
                "evidence": [], "sources": [endpoint], "retrieval": retrieval,
            }
        labels = [item["label"] for item in evidence if item["evidence_type"] == "graph_resource"]
        relation_types = sorted({item["relationship"] for item in evidence if item["evidence_type"] == "graph_relationship"})
        response_text = f"Grounded graph matches: {', '.join(labels[:6])}."
        if relation_types:
            response_text += f" Connected relationship types: {', '.join(relation_types[:6])}."
        return {
            "status": "grounded", "answerable": True, "response": response_text,
            "evidence": evidence, "sources": [endpoint], "retrieval": retrieval,
        }


companion = KnowledgeCompanion()
