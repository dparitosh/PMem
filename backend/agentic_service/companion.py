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
               'datatype', 'unit', 'units', 'value', 'prefLabel', 'altLabel', 'prefix', 'updated_at', 'publication_revision'}
    result = {}
    for key in sorted(allowed):
        value = properties.get(key)
        if isinstance(value, (str, int, float, bool)):
            result[key] = str(value)[:1000]
        elif isinstance(value, list):
            result[key] = [str(item)[:250] for item in value[:8] if isinstance(item, (str, int, float, bool))]
    return result


class KnowledgeCompanion:
    max_nodes = 200
    max_evidence = 12

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) >= 3}

    @staticmethod
    def _graph_root() -> str:
        configured = service_url("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1")
        return configured if configured.endswith("/api/v1") else f"{configured}/api/v1"

    async def ask(self, message: str, *, headers: dict | None = None, ontology_id: str = '', ontology_prefix: str = '', page: str = '', on_token=None) -> dict[str, Any]:
        import hashlib
        from datetime import datetime, timezone
        query = " ".join(str(message or "").split())
        if not query:
            raise ValueError("message is required")
        if headers is None:
            headers = {"Authorization": f"Bearer {os.environ['GRAPH_READ_TOKEN']}"} if os.getenv('GRAPH_READ_TOKEN') else {}
        from .companion_context import mapping_context
        context = {'evidence': [], 'status': 'unavailable'}
        try:
            context = await mapping_context(query, headers=headers, ontology_id=ontology_id, ontology_prefix=ontology_prefix)
        except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
            logging.getLogger(__name__).warning('Companion retained mapping retrieval unavailable')
        page_result={'evidence':[],'status':'not_requested'}
        if page:
            from .companion_context import page_context
            try:
                page_result=await page_context(query,page=page,headers=headers,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
            except (httpx.HTTPError,TimeoutError,ValueError,RuntimeError):
                page_result={'evidence':[],'status':'unavailable'}
                logging.getLogger(__name__).warning('Companion page evidence unavailable: page=%s',page)
        context['evidence']+=page_result['evidence']
        endpoint = f"{self._graph_root()}/graph/search"
        graph_status = 'available'
        try:
            from backend.depo_platform.network import bounded_timeout_seconds
            timeout = bounded_timeout_seconds("COMPANION_RETRIEVAL_TIMEOUT_SECONDS", default=15, maximum=120)
            async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                from backend.depo_platform.network import gateway_subscription_headers
                headers = {**headers, **gateway_subscription_headers(endpoint)}
                from .response_limits import read_bounded_response
                async with client.stream('GET', endpoint, params={"query": query, "limit": self.max_nodes, "ontology_id": ontology_id, "ontology_prefix": ontology_prefix}, headers=headers) as response:
                    response.raise_for_status()
                    graph = json.loads(await read_bounded_response(response))
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            if not context['evidence']:
                raise RuntimeError("Knowledge graph retrieval is unavailable; no answer was generated. Check graph service readiness and read access in Admin.") from exc
            graph = {'nodes': [], 'relationships': []}
            graph_status = 'unavailable'
        if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('relationships'), list):
            raise RuntimeError('Graph retrieval returned invalid evidence')
        nodes, relationships = graph['nodes'], graph['relationships']
        if len(nodes)>200 or len(relationships)>800:
            raise RuntimeError('Graph retrieval exceeded its evidence limits')
        if any(not isinstance(node, dict) or not isinstance(node.get('properties'), dict) for node in nodes) or any(not isinstance(edge, dict) for edge in relationships):
            raise RuntimeError('Graph retrieval returned invalid evidence')
        identities=[node.get('elementId') for node in nodes]
        if any(not isinstance(value,str) or not value.strip() or len(value)>2000 for value in identities) or len(identities)!=len(set(identities)):
            raise RuntimeError('Graph retrieval returned invalid or duplicate evidence identities')
        if ontology_id and any(node['properties'].get('ontology_id') != ontology_id for node in nodes):
            raise RuntimeError('Graph retrieval returned evidence outside the selected ontology scope')
        if ontology_prefix and any(node['properties'].get('prefix') != ontology_prefix for node in nodes):
            raise RuntimeError('Graph retrieval returned evidence outside the selected prefix scope')
        if any(not isinstance(edge.get('start'), str) or not isinstance(edge.get('end'), str)
               or edge['start'] not in identities or edge['end'] not in identities for edge in relationships):
            raise RuntimeError('Graph retrieval returned a relationship outside its evidence resources')
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
        selected_edges = [edge for edge in relationships if str(edge.get("start")) in selected_ids and str(edge.get("end")) in selected_ids][:edge_budget]
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
            "target_id": str(edge.get("end") or ""), "relationship": str((edge.get('properties') or {}).get('predicate') or edge.get("type") or "RELATED_TO"), "source": endpoint,
        } for edge in selected_edges)
        from .prompt_security import protect
        evidence = protect(context['evidence'] + evidence)[:26]
        selection_truncated = len(scored)>len(selected) or len(relationships)>len(selected_edges)
        retrieval = {"nodes_examined": len(nodes), "relationships_examined": len(relationships), "truncated": bool((graph.get("view") or {}).get("truncated")), 'graph_status': graph_status, 'mapping_history_status': context['status'], 'page_evidence_status': page_result['status'], 'page':page, 'selection_truncated': selection_truncated, 'selected_resources': len(selected), 'selected_relationships': len(selected_edges), 'answer_scope': 'bounded_retrieval', 'semantic_entailment_verified': False, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'evidence_sha256': hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
        retrieval['page_representation'] = page_result.get('representation', 'not_available')
        retrieval['page_coverage'] = page_result.get('coverage')
        retrieval['source_revision_status'] = 'unverified'
        if not evidence:
            return {
                "status": "no_evidence", "answerable": False,
                "response": ("No matching graph resources were found in the current ontology scope. "
                             + ("No saved mapping reviews matched either. " if context['status'] == 'available' else
                                "Saved mapping history could not be checked; verify ontology service readiness and read access in Admin. " if context['status'] == 'unavailable' else '')
                             + "For data questions, select the relevant ontology and check its Neo4j publication. Try a specific class, property or instance name. The Companion cannot infer facts from data it cannot retrieve."),
                "evidence": [], "sources": [endpoint], "retrieval": retrieval,
            }
        labels = [item["label"] for item in evidence if item["evidence_type"] == "graph_resource"]
        relation_types = sorted({item["relationship"] for item in evidence if item["evidence_type"] == "graph_relationship"})
        review_items = [item for item in evidence if item['evidence_type'] == 'mapping_review']
        response_text = '\n\n'.join(item['description'] + f" [evidence:{item['resource_id']}]" for item in review_items[:3])
        if review_items:
            response_text = f"Found {len(review_items)} retained mapping review(s); showing up to three newest matching records.\n\n" + response_text
        application_items=[item for item in evidence if item['evidence_type']=='application_record']
        if application_items:
            response_text+=('\n\n' if response_text else '')+'\n'.join(item['description']+f" [evidence:{item['resource_id']}]" for item in application_items)
        if labels:
            response_text += ("\n\n" if response_text else '') + f"Matching graph resources: {', '.join(labels[:6])}."
            for item in evidence:
                if item['evidence_type'] != 'graph_resource': continue
                props = item.get('properties') or {}
                description = props.get('definition') or props.get('description') or props.get('comment')
                if description: response_text += f"\n- {item['label']}: {str(description)[:500]} [evidence:{item['resource_id']}]"
        if retrieval['truncated'] or selection_truncated: response_text += '\n\nThis answer uses a limited evidence selection; it does not establish whole-graph counts, completeness or absence of other matches.'
        if page_result.get('representation') == 'postgres_business_context':
            response_text += '\n\nBusiness-context evidence comes from the PostgreSQL-backed Semantica context graph; synchronization with Neo4j is not established.'
        if page_result['status']=='unavailable': response_text+='\n\nThe current page service could not be checked; this answer does not establish its current state.'
        if graph_status == 'unavailable': response_text += '\n\nGraph retrieval is unavailable; this answer uses owning-service records only.'
        if context['status'] == 'unavailable': response_text += '\n\nSaved mapping history could not be checked. Verify ontology service readiness and read access in Admin.'
        if relation_types:
            response_text += f" Connected relationship types: {', '.join(relation_types[:6])}."
        if on_token:
            await on_token(response_text)
        generation = {'enabled': False, 'status': 'disabled', 'action': 'This is a retrieval answer. Enable COMPANION_LLM_ENABLED=true with a configured provider for cited model summaries.'}
        if os.getenv('COMPANION_LLM_ENABLED', 'false').lower() == 'true':
            prompt_details = {}
            try:
                from .local_llm import summarize
                summary = await summarize(query, evidence, prompt_details=prompt_details)
                if on_token: await on_token('\n\nModel-assisted summary (review against the evidence): ' + summary)
                response_text += '\n\nModel-assisted summary (review against the evidence): ' + summary
                generation = {'enabled': True, 'status': 'completed', 'provider': os.getenv('USE_LLM', 'ollama').strip().lower(), 'prompt_details': prompt_details, 'grounding': 'citation-identifiers-checked', 'semantic_entailment_verified': False}
            except Exception as failure:
                code = getattr(getattr(failure, 'response', None), 'status_code', None)
                status = ('authentication_rejected' if code in (401, 403) else 'route_missing' if code == 404
                          else 'rate_limited' if code == 429 else 'timeout' if isinstance(failure, (TimeoutError, httpx.TimeoutException))
                          else 'invalid_response' if isinstance(failure, ValueError) else 'unavailable')
                logging.getLogger(__name__).warning('Companion generation failed: stage=generation status=%s error_type=%s', status, type(failure).__name__)
                generation = {'enabled': True, 'status': status, 'prompt_details': prompt_details, 'provider': os.getenv('USE_LLM', 'ollama').strip().lower(), 'action': 'The provider returned HTTP 429. Check its quota, billing and rate limits before retrying.' if code == 429 else 'Check the selected provider configuration and capability diagnostics in Admin, and the agentic service logs.'}
                response_text += '\n\nThe configured language model is unavailable; the retrieved evidence above remains available.'
        return {
            "status": "grounded", "answerable": True, "response": response_text,
            "evidence": evidence, "sources": sorted({item['source'] for item in evidence}), "retrieval": retrieval, 'generation': generation,
        }


companion = KnowledgeCompanion()
