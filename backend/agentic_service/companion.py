"""Fail-closed, evidence-grounded retrieval for the Knowledge Companion."""
from __future__ import annotations

import os
import json
import asyncio
from backend.depo_platform.service_urls import service_url
import re
import logging
from typing import Any

import httpx


def descriptive_properties(properties):
    """Bound descriptive evidence; never forward arbitrary credential properties."""
    allowed = {'iri', 'definition', 'description', 'comment', 'domain', 'range',
               'datatype', 'unit', 'units', 'value', 'prefLabel', 'altLabel'}
    result = {}
    for key in sorted(allowed):
        value = properties.get(key)
        if isinstance(value, (str, int, float, bool)):
            result[key] = str(value)[:1000]
        elif isinstance(value, list):
            result[key] = [str(item)[:250] for item in value[:8] if isinstance(item, (str, int, float, bool))]
    return result


class KnowledgeCompanion:
    max_nodes = 900
    max_evidence = 12

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 3}

    @staticmethod
    def _graph_root() -> str:
        configured = service_url("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1")
        return configured if configured.endswith("/api/v1") else f"{configured}/api/v1"

    async def ask(self, message: str, *, headers: dict | None = None, ontology_id: str = '', ontology_prefix: str = '', on_token=None) -> dict[str, Any]:
        query = " ".join(str(message or "").split())
        if not query:
            raise ValueError("message is required")
        endpoint = f"{self._graph_root()}/graph/search"
        try:
            from backend.depo_platform.network import bounded_timeout_seconds
            timeout = bounded_timeout_seconds("COMPANION_RETRIEVAL_TIMEOUT_SECONDS", default=15, maximum=120)
            async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                if headers is None:
                    headers = {"Authorization": f"Bearer {os.environ['GRAPH_READ_TOKEN']}"} if os.getenv('GRAPH_READ_TOKEN') else {}
                from backend.depo_platform.network import gateway_subscription_headers
                headers = {**headers, **gateway_subscription_headers(endpoint)}
                from .response_limits import read_bounded_response
                async with client.stream('GET', endpoint, params={"query": query, "limit": min(self.max_nodes, 200), "ontology_id": ontology_id, "ontology_prefix": ontology_prefix}, headers=headers) as response:
                    response.raise_for_status()
                    graph = json.loads(await read_bounded_response(response))
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise RuntimeError("Knowledge graph retrieval is unavailable; no answer was generated") from exc
        if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('relationships'), list):
            raise RuntimeError('Graph retrieval returned invalid evidence')
        nodes, relationships = graph['nodes'], graph['relationships']
        if any(not isinstance(node, dict) or not isinstance(node.get('properties'), dict) for node in nodes) or any(not isinstance(edge, dict) for edge in relationships):
            raise RuntimeError('Graph retrieval returned invalid evidence')
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
                "properties": descriptive_properties(node.get("properties") or {}),
            }
            for node in selected
        ]
        evidence.extend({
            "evidence_type": "graph_relationship", "source_id": str(edge.get("start") or ""),
            "target_id": str(edge.get("end") or ""), "relationship": str(edge.get("type") or "RELATED_TO"), "source": endpoint,
        } for edge in selected_edges)
        from .prompt_security import protect
        evidence = protect(evidence)
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
        if on_token:
            await on_token(response_text)
        generation = {'enabled': False, 'status': 'disabled'}
        if os.getenv('COMPANION_LLM_ENABLED', 'false').lower() == 'true':
            prompt_details = {}
            try:
                from .local_llm import summarize
                if on_token:
                    await on_token('\n\nModel-assisted summary (review against the evidence): ')
                summary = await summarize(query, evidence, on_token=on_token, prompt_details=prompt_details)
                response_text += '\n\nModel-assisted summary (review against the evidence): ' + summary
                generation = {'enabled': True, 'status': 'completed', 'provider': 'ollama', 'prompt_details': prompt_details}
            except Exception as failure:
                code = getattr(getattr(failure, 'response', None), 'status_code', None)
                status = ('authentication_rejected' if code in (401, 403) else 'route_missing' if code == 404
                          else 'timeout' if isinstance(failure, (TimeoutError, httpx.TimeoutException))
                          else 'invalid_response' if isinstance(failure, ValueError) else 'unavailable')
                logging.getLogger(__name__).warning('Companion generation failed: stage=generation status=%s error_type=%s', status, type(failure).__name__)
                generation = {'enabled': True, 'status': status, 'prompt_details': prompt_details, 'action': 'Check Admin Ollama capability diagnostics and agentic service logs.'}
                response_text += '\n\nThe configured language model is unavailable; the graph evidence above remains available.'
        return {
            "status": "grounded", "answerable": True, "response": response_text,
            "evidence": evidence, "sources": [endpoint], "retrieval": retrieval, 'generation': generation,
        }


companion = KnowledgeCompanion()
