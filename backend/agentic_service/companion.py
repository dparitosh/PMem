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
    from backend.graph_service.search_evidence import BUSINESS_FIELDS, search_properties
    allowed |= BUSINESS_FIELDS
    allowed |= {'quantity', 'datum', 'nominal', 'upperTolerance', 'lowerTolerance',
                'shape', 'geometry', 'representation', 'requirementText', 'identifier'}
    properties = {**properties, **search_properties(properties)}
    result = {}
    for key in sorted(allowed):
        value = properties.get(key)
        if isinstance(value, (str, int, float, bool)):
            result[key] = str(value)[:1000]
        elif isinstance(value, list):
            result[key] = [str(item)[:250] for item in value[:8] if isinstance(item, (str, int, float, bool))]
    return result


def select_context_evidence(nodes, root_id, query, limit):
    """Keep the pinned root, then rank allowed evidence by the current question.

    Storage allocation order must not select batch names instead of requested
    findings or alternatives. Ranking does not change scope or infer relevance.
    """
    terms = {word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) >= 3}
    def rank(node):
        properties = node.get('properties') or {}
        label = str(properties.get('label') or properties.get('name') or '')
        allowed = descriptive_properties(properties)
        label_terms = set(re.findall(r"[a-z0-9]+", label.lower()))
        detail_terms = set(re.findall(r"[a-z0-9]+", json.dumps(allowed, sort_keys=True).lower()))
        score = 3 * len(terms & label_terms) + len(terms & detail_terms)
        return (node.get('elementId') != root_id, -score, label.casefold(), str(node.get('elementId') or ''))
    return sorted((node for node in nodes if is_business_result(node)), key=rank)[:limit]


def is_business_result(node):
    """Reject vocabulary and infrastructure rows, including schema-typed resources."""
    props = node.get('properties') or {}
    excluded = {'class', 'ontologyclass', 'objectproperty', 'datatypeproperty',
                'annotationproperty', 'restriction', 'property', 'datatype', 'expression',
                'axiom', 'ontology', 'ontologypublication', 'retainedontologyidentity',
                'stagedontologyresource', 'graphchunk', 'datasheetchunk'}
    kinds = {str(props.get('kind') or '').casefold()}
    kinds.update(str(value).casefold() for value in node.get('labels') or [])
    schema_types = {
        'http://www.w3.org/2002/07/owl#' + name for name in
        ('Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty', 'Restriction', 'Ontology')
    } | {'http://www.w3.org/2000/01/rdf-schema#Class',
         'http://www.w3.org/2000/01/rdf-schema#Datatype',
         'http://www.w3.org/1999/02/22-rdf-syntax-ns#Property'}
    return not (kinds & excluded or set(props.get('rdf_types') or []) & schema_types)


def unresolved_identity(subject, source):
    from .business_answers import cell
    return {'status':'unresolved_identity', 'answerable':False,
            'response':('I could not identify “' + cell(subject) +
                '” in the retrieved business records. Check the part number or revision, or select the intended record.'),
            'evidence':[], 'sources':[source],
            'retrieval':{'answer_scope':'business_identity','identity_resolution':'unresolved',
                         'context_invalidated':True,'graph_status':'available','semantic_entailment_verified':False},
            'generation':{'enabled':False,'status':'not_requested'}}


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

    async def ask(self, message: str, *, headers: dict | None = None, ontology_id: str = '', ontology_prefix: str = '', page: str = '', node_id: str = '', run_id: str = '', product_id: str = '', product_version: str = '', reconciliation_id: str = '', on_token=None) -> dict[str, Any]:
        import hashlib
        from datetime import datetime, timezone
        query = " ".join(str(message or "").split())
        if not query:
            raise ValueError("message is required")
        from .answerability import assess
        if headers is None:
            headers = {"Authorization": f"Bearer {os.environ['GRAPH_READ_TOKEN']}"} if os.getenv('GRAPH_READ_TOKEN') else {}
        if run_id or product_id or reconciliation_id:
            from .selected_record import answer
            try:
                selected = await answer({'run_id': run_id, 'product_id': product_id, 'product_version': product_version,'reconciliation_id':reconciliation_id}, headers)
            except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
                selected = {'status': 'unavailable', 'answerable': False,
                    'response': 'The selected record could not be verified. Refresh its owning service and access before retrying; no other record was substituted.',
                    'evidence': [], 'sources': [], 'generation': {'enabled': False, 'status': 'not_requested'}}
            coverage = assess(query, selected.get('evidence', []))
            if selected.get('answerable') and not coverage['answerable']:
                selected.update(status=coverage['status'], answerable=False)
                selected['response'] += '\n\n' + coverage['response']
                selected.setdefault('retrieval', {})['answerability'] = {key: coverage[key] for key in ('status', 'answerable')}
            if on_token: await on_token(selected['response'])
            return selected
        if page == 'modeling' and node_id and ontology_id and re.search(r'\brequirement\s+(?:value|text|number|details?|description)\b', query, re.I):
            from .companion_context import selected_model_answer
            try:
                selected = await selected_model_answer(node_id, headers=headers, ontology_id=ontology_id)
            except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
                selected = {'status': 'unavailable', 'answerable': False,
                    'response': 'The selected model requirement could not be verified. Refresh the source model and retry; no other record was substituted.',
                    'evidence': [], 'sources': [], 'generation': {'enabled': False, 'status': 'not_requested'}}
            if on_token: await on_token(selected['response'])
            return selected
        from .companion_context import semantic_context
        try:
            semantic = await semantic_context(query, headers=headers, ontology_id=ontology_id)
        except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
            semantic = {'status': 'unavailable', 'answerable': False,
                'response': 'Semantic evidence could not be checked. Verify read access and ontology-service readiness; no consistency conclusion was generated.',
                'evidence': [], 'sources': [], 'generation': {'enabled': False, 'status': 'not_requested'}}
        if semantic is not None:
            coverage = assess(query, semantic.get('evidence', []))
            if semantic.get('answerable') and not coverage['answerable']:
                semantic.update(status=coverage['status'], answerable=False)
                semantic['response'] += '\n\n' + coverage['response']
            if on_token: await on_token(semantic['response'])
            return semantic
        calculation = assess(query, [])
        if calculation['status'] == 'unsupported_calculation':
            if on_token:
                await on_token(calculation['response'])
            return {**calculation, 'evidence': [], 'sources': [],
                    'retrieval': {'answer_scope': 'approved_analysis_required', 'calculation_executed': False},
                    'generation': {'enabled': False, 'status': 'not_requested'}}
        from backend.depo_platform.plm_questions import intent
        business_intent=intent(query)
        from backend.depo_platform.plm_questions import property_subject
        explicit_subject = property_subject(query) if not business_intent and not node_id else ''
        search_query = explicit_subject or query
        from .companion_context import mapping_context
        context = {'evidence': [], 'status': 'unavailable'}
        model_support = None
        if ontology_id:
            from backend.depo_platform.semantic_support import read_support
            model_support = await asyncio.to_thread(read_support, ontology_id, headers)
        try:
            context = await mapping_context(query, headers=headers, ontology_id=ontology_id, ontology_prefix=ontology_prefix)
        except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
            logging.getLogger(__name__).warning('Companion retained mapping retrieval unavailable')
        page_result={'evidence':[],'status':'not_requested'}
        if page and not business_intent and not node_id:
            from .companion_context import page_context
            try:
                page_result=await page_context(query,page=page,headers=headers,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
            except (httpx.HTTPError,TimeoutError,ValueError,RuntimeError):
                page_result={'evidence':[],'status':'unavailable'}
                logging.getLogger(__name__).warning('Companion page evidence unavailable: page=%s',page)
        context['evidence']+=page_result['evidence']
        if business_intent:
            try:
                from .companion_context import plm_context
                context['evidence'].append(await plm_context(query,headers=headers,ontology_id=ontology_id,ontology_prefix=ontology_prefix,**({'node_id':node_id} if node_id else {})))
            except (httpx.HTTPError,TimeoutError,ValueError,RuntimeError):
                logging.getLogger(__name__).warning('Companion typed PLM read unavailable')
        document_result={'status':'unavailable','evidence':[]}
        try:
            from .companion_context import document_context
            document_result=await document_context(query,headers=headers,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
            context['evidence']+=document_result['evidence']
        except (httpx.HTTPError,TimeoutError,ValueError,RuntimeError):
            logging.getLogger(__name__).warning('Companion indexed excerpt retrieval unavailable')
        endpoint = f"{self._graph_root()}/graph/search"
        typed_answer=next((item for item in context['evidence'] if item.get('evidence_type')=='business_answer'),None)
        if business_intent and typed_answer is None:
            text = ('I could not verify the requested business associations because the business-instance evidence service could not be checked. '
                    'Check graph-service readiness and API access, then retry this question. Schema definitions and matching words are not evidence that a product has an associated requirement or PMI.')
            if on_token:
                await on_token(text)
            return {'status':'unavailable', 'answerable':False, 'response':text, 'evidence':[], 'sources':[],
                    'retrieval':{'answer_scope':'business_instance_associations', 'business_answer_status':'unavailable',
                                 'semantic_entailment_verified':False},
                    'generation':{'enabled':False,'status':'not_requested'}}
        if typed_answer and typed_answer.get('intent') == 'product_assembly' and not typed_answer.get('rows'):
            from backend.depo_platform.plm_questions import business_subject
            named = business_subject(query, node_id)
            if named:
                return unresolved_identity(named, self._graph_root() + '/graph/business-answer')
        include_record_context = bool(node_id and typed_answer and typed_answer.get('intent') == 'associated_requirements')
        graph_status = 'not_requested' if typed_answer and not include_record_context else 'available'
        resolved_context = None
        try:
            if typed_answer and not include_record_context:
                graph={'nodes':[],'relationships':[],'view':{'truncated':bool((typed_answer.get('coverage') or {}).get('has_more'))}}
            elif node_id:
                from .companion_context import business_context
                resolved_context, endpoint = await business_context(node_id,headers=headers,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
                graph = resolved_context
            else:
                from backend.depo_platform.network import bounded_timeout_seconds
                timeout = bounded_timeout_seconds("COMPANION_RETRIEVAL_TIMEOUT_SECONDS", default=15, maximum=120)
                async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                    from backend.depo_platform.network import gateway_subscription_headers
                    headers = {**headers, **gateway_subscription_headers(endpoint)}
                    from .response_limits import read_bounded_response
                    async with client.stream('GET', endpoint, params={"query": search_query, "limit": self.max_nodes, "ontology_id": ontology_id, "ontology_prefix": ontology_prefix, "business_only": True}, headers=headers) as response:
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
        if ontology_id and any(ontology_id not in (node['properties'].get('ontology_id'),node['properties'].get('source_ontology')) for node in nodes):
            raise RuntimeError('Graph retrieval returned evidence outside the selected ontology scope')
        if ontology_prefix and any(ontology_prefix not in (node['properties'].get('prefix'),node['properties'].get('ontology_prefix')) for node in nodes):
            raise RuntimeError('Graph retrieval returned evidence outside the selected prefix scope')
        if any(not isinstance(edge.get('start'), str) or not isinstance(edge.get('end'), str)
               or edge['start'] not in identities or edge['end'] not in identities for edge in relationships):
            raise RuntimeError('Graph retrieval returned a relationship outside its evidence resources')
        query_tokens = self._tokens(search_query)
        # Do not turn a legacy/unfiltered search response into a business fact.
        nodes = [node for node in nodes if is_business_result(node)]
        if explicit_subject:
            subject_tokens = self._tokens(explicit_subject)
            nodes = [node for node in nodes if subject_tokens and subject_tokens <= self._tokens(str(node['properties'].get('name') or node['properties'].get('label') or ''))]
            exact_nodes = [node for node in nodes if self._tokens(str(node['properties'].get('name') or node['properties'].get('label') or '')) == subject_tokens]
            if exact_nodes:
                nodes = exact_nodes
        if explicit_subject and not nodes and graph_status == 'available':
            return unresolved_identity(explicit_subject, endpoint)
        business_ids = {node['elementId'] for node in nodes}
        relationships = [edge for edge in relationships if edge.get('start') in business_ids and edge.get('end') in business_ids]
        scored: list[tuple[int, dict[str, Any]]] = []
        for node in nodes:
            properties = dict(node.get("properties") or {})
            text = " ".join(str(properties.get(key) or "") for key in ("label", "iri", "kind", "ontology_id"))
            score = 1 if node_id else int(properties.get("search_score") or len(query_tokens & self._tokens(text)))
            if score:
                scored.append((score, node))
        scored.sort(key=lambda item: (-item[0], str((item[1].get("properties") or {}).get("label") or item[1].get("elementId"))))
        selected = [node for _, node in scored[: min(8, self.max_evidence)]]
        business_status='not_requested'
        inclusion={}
        context_coverage={}
        if selected and (page in {'graph','whereused','modeling','requirements','qif'} or node_id):
            exact=[node for node in selected if str(node['properties'].get('label') or '').casefold()==query.casefold()]
            roots = [node for node in nodes if node['elementId'] == node_id] if node_id else ((exact if len(exact)==1 else selected if len(nodes)==1 else []) if not (graph.get('view') or {}).get('truncated') else [])
            business_status='ambiguous' if not roots else 'unavailable'
            if roots:
                try:
                    from .companion_context import business_context
                    if resolved_context is not None:
                        connected,context_endpoint=resolved_context,endpoint
                    else:
                        connected,context_endpoint=await business_context(roots[0]['elementId'],headers=headers,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
                    root_id=roots[0]['elementId']
                    selected=select_context_evidence(connected['nodes'], root_id, query, max(1,min(6,self.max_evidence//2)))
                    relationships=connected['relationships']
                    inclusion=connected.get('inclusion') or {}
                    context_coverage={'nodes_examined':len(connected['nodes']),'relationships_examined':len(relationships),
                                      'truncated':bool((connected.get('view') or {}).get('truncated')) or len(connected['nodes'])>len(selected)}
                    endpoint=context_endpoint
                    business_status='available'
                except (httpx.HTTPError,TimeoutError,ValueError,RuntimeError):
                    logging.getLogger(__name__).warning('Companion business context unavailable')
        selected = [node for node in selected if is_business_result(node)]
        selected_ids = {str(node.get("elementId")) for node in selected}
        edge_budget = max(0, self.max_evidence - len(selected))
        selected_edges = [edge for edge in relationships if str(edge.get("start")) in selected_ids and str(edge.get("end")) in selected_ids][:edge_budget]
        from backend.graph_service.engineering_comparison import kind as declared_business_kind
        evidence = [
            {
                "evidence_type": "graph_resource", "resource_id": str(node.get("elementId") or ""),
                "label": str((node.get("properties") or {}).get("label") or node.get("elementId") or ""),
                "kind": (declared_business_kind(node) if declared_business_kind(node) != 'unclassified' else
                         str((node.get("properties") or {}).get("kind") or (node.get("labels") or ["resource"])[0])),
                "ontology_id": (node.get("properties") or {}).get("ontology_id") or (node.get("properties") or {}).get("source_ontology"), "source": endpoint,
                "properties": descriptive_properties(node.get("properties") or {}),
                "why_included": inclusion.get(node['elementId']),
            }
            for node in selected
        ]
        evidence.extend({
            "evidence_type": "graph_relationship", "resource_id":str(edge.get('elementId') or ''), "source_id": str(edge.get("start") or ""),
            "target_id": str(edge.get("end") or ""), "relationship": str((edge.get('properties') or {}).get('predicate') or edge.get("type") or "RELATED_TO"), "source": endpoint,
            "business_label": edge.get('business_label') or (edge.get('properties') or {}).get('business_label'),
        } for edge in selected_edges)
        from .prompt_security import protect
        evidence = protect(context['evidence'] + evidence)[:26]
        if model_support is not None and evidence:
            evidence.append({'evidence_type': 'semantic_assessment', 'resource_id': 'semantic:' + str(model_support.get('evidence_id') or ontology_id),
                'label': 'Selected model assessment', 'description': model_support['business_summary'],
                'source': 'ontology-service:current-semantic-evidence', 'assessment': model_support})
        selection_truncated = len(scored)>len(selected) or len(relationships)>len(selected_edges)
        retrieval = {"nodes_examined": len(nodes), "relationships_examined": len(relationships), "truncated": bool((graph.get("view") or {}).get("truncated")), 'graph_status': graph_status, 'mapping_history_status': context['status'], 'page_evidence_status': page_result['status'], 'page':page, 'selection_truncated': selection_truncated, 'selected_resources': len(selected), 'selected_relationships': len(selected_edges), 'answer_scope': 'bounded_retrieval', 'semantic_entailment_verified': False, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'evidence_sha256': hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
        # Retain the actual evidence baseline separately from the user's search scope.
        # Historical memory is advisory; subsequent questions must re-read the graph.
        from .companion_memory import evidence_grounding
        grounding_root = node_id or (selected[0]['elementId'] if explicit_subject and len(nodes) == 1 and selected
                                    and not (graph.get('view') or {}).get('truncated') else '')
        retrieval['grounding'] = evidence_grounding(evidence, grounding_root)
        retrieval['page_representation'] = page_result.get('representation', 'not_available')
        retrieval['document_evidence_status'] = document_result['status']
        retrieval['document_retrieval_mode'] = 'lexical_fulltext'
        retrieval['business_context_status'] = business_status
        retrieval['business_context_coverage'] = context_coverage
        retrieval['page_coverage'] = page_result.get('coverage')
        retrieval['source_revision_status'] = 'unverified'
        retrieval['semantic_support'] = model_support
        if not evidence:
            return {
                "status": "no_evidence", "answerable": False,
                "response": ("No matching graph resources were found in the current ontology scope. "
                             + ("No saved mapping reviews matched either. " if context['status'] == 'available' else
                                "Saved mapping history could not be checked; verify ontology service readiness and read access in Admin. " if context['status'] == 'unavailable' else '')
                             + ("Indexed document coverage is unavailable. " if document_result['status'] in {'not_indexed','unavailable'} else "No indexed excerpts matched this bounded search. ")
                             + "Select the relevant business scope and verify its graph publication. Try a specific product, requirement or process name. The Companion cannot infer facts from data it cannot retrieve."),
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
        excerpts=[item for item in evidence if item['evidence_type'] in {'document_excerpt','graph_excerpt'}]
        if excerpts:
            from .business_answers import business_text
            response_text+=('\n\n' if response_text else '')+'Retrieved excerpts (source freshness is unverified):\n'+'\n'.join(business_text(item['description'])[:1000]+f" [evidence:{item['resource_id']}]" for item in excerpts[:3])
        business_items=[item for item in evidence if item['evidence_type']=='business_answer']
        answerability = assess(query, evidence)
        retrieval['answerability'] = {key: answerability[key] for key in ('status', 'answerable')}
        if business_items:
            from .business_answers import render
            response_text=render(business_items)
        if labels and (not business_items or include_record_context):
            from .business_answers import cell
            response_text += ("\n\n" if response_text else '') + 'Retrieved business records:\n\n| Name | Description / value | Evidence |\n|---|---|---|'
            missing_record_details = False
            for item in evidence:
                if item['evidence_type'] != 'graph_resource': continue
                props = item.get('properties') or {}
                from .business_answers import instance_details
                details = instance_details(props)
                missing_record_details = missing_record_details or not details
                details = details or 'Property read incomplete'
                response_text += f"\n| {cell(item['label'])} | {details} | [evidence:{item['resource_id']}] |"
            if missing_record_details:
                response_text += '\n\nProperty values could not be established for the marked records from this bounded read. The source has not been checked for missing assertions; inspect the cited instance before drawing a conclusion.'
            from .business_answers import render_instance_connections
            connection_text = render_instance_connections(evidence)
            if connection_text:
                response_text += '\n\n' + connection_text
        if retrieval['truncated'] or selection_truncated or any((item.get('coverage') or {}).get('has_more') for item in business_items): response_text += '\n\nThis answer uses a limited evidence selection; it does not establish whole-graph counts, completeness or absence of other matches.'
        if page_result.get('representation') == 'postgres_business_context':
            response_text += '\n\nBusiness-context evidence comes from the PostgreSQL-backed Semantica context graph; synchronization with Neo4j is not established.'
        if page_result['status']=='unavailable': response_text+='\n\nThe current page service could not be checked; this answer does not establish its current state.'
        if graph_status == 'unavailable': response_text += '\n\nGraph retrieval is unavailable; this answer uses the evidence that could be retrieved.'
        if context['status'] == 'unavailable': response_text += '\n\nSaved mapping history could not be checked. Verify ontology service readiness and read access in Admin.'
        if document_result['status'] in {'unavailable','not_indexed'}:
            response_text += '\n\nIndexed document evidence could not be checked; this answer does not establish document coverage.'
        if relation_types and not business_items:
            response_text += '\n\nSupporting link records are available in the evidence.'
        if business_status=='available':
            response_text += '\n\nConnected objects are included through recorded graph paths. Source references do not by themselves establish business impact or semantic equivalence.'
        elif business_status=='ambiguous':
            response_text += '\n\nSeveral business objects may match. Select a specific graph node and use Investigate with agent to preserve its identity and retrieve its context.'
        if not answerability['answerable'] and answerability['response']:
            response_text += '\n\n' + answerability['response']
        generation = {'enabled': False, 'status': 'disabled', 'action': 'This is a retrieval answer. Enable COMPANION_LLM_ENABLED=true with a configured provider for cited model summaries.'}
        if os.getenv('COMPANION_LLM_ENABLED','false').lower()=='true' and not answerability['answerable']:
            generation={'enabled':True,'status':'not_requested','action':'Business evidence is insufficient or its ownership is unverified; no model interpretation was requested.'}
        if os.getenv('COMPANION_LLM_ENABLED', 'false').lower() == 'true' and answerability['answerable'] and (not business_items or any(item.get('rows') for item in business_items)):
            prompt_details = {}
            try:
                from .local_llm import summarize
                summary = await summarize(query, evidence, prompt_details=prompt_details)
                # The model may explain typed facts; it must not replace their
                # deterministic table or erase recorded uncertainty/coverage.
                response_text = response_text + '\n\nModel interpretation (not independently verified):\n\n' + summary if business_items or labels else summary
                generation = {'enabled': True, 'status': 'completed', 'provider': os.getenv('USE_LLM', 'ollama').strip().lower(), 'prompt_details': prompt_details, 'grounding': 'citation-identifiers-checked', 'semantic_entailment_verified': False}
            except Exception as failure:
                from .local_llm import failure_status, failure_action
                status = failure_status(failure)
                logging.getLogger(__name__).warning('Companion generation failed: stage=generation status=%s error_type=%s', status, type(failure).__name__)
                generation = {'enabled': True, 'status': status, 'prompt_details': prompt_details, 'provider': os.getenv('USE_LLM', 'ollama').strip().lower(), 'action': failure_action(failure, os.getenv('USE_LLM', 'ollama').strip().lower())}
                response_text += ('\n\nThe evidence exceeds the configured model context. Narrow the question or selected scope; retrieved business evidence remains available.'
                                  if status == 'context_budget_exceeded' else '\n\nThe model reached its output limit; no partial summary was shown. Retrieved evidence remains available.' if status == 'output_incomplete' else '\n\nThe configured language model is unavailable; the retrieved evidence above remains available.')
        if model_support is not None:
            response_text += '\n\nModel evidence: ' + str(model_support.get('status', 'unknown')) + '. ' + model_support['business_summary'] + ' [evidence:semantic:' + str(model_support.get('evidence_id') or ontology_id) + ']'
        if on_token:
            await on_token(response_text)
        return {
            "status": "grounded" if answerability['answerable'] else answerability['status'], "answerable": answerability['answerable'], "response": response_text,
            "evidence": evidence, "sources": sorted({item['source'] for item in evidence}), "retrieval": retrieval, 'generation': generation,
        }


companion = KnowledgeCompanion()
