"""Business interpretation of scoped reasoning evidence; never approval or inferred facts."""
from urllib.parse import quote
import re


def assessment(evidence):
    if not isinstance(evidence, dict): evidence = {'status': 'unknown', 'reason': 'invalid_semantic_contract'}
    foundation = evidence.get('foundation') if isinstance(evidence.get('foundation'), dict) else {}
    status = evidence.get('status', 'unknown')
    verified = (evidence.get('consistency_verified') is True and
                evidence.get('deductive_reasoner_executed') is True and status in {'consistent', 'inconsistent'} and
                bool(re.fullmatch(r'[0-9a-f]{64}', str(evidence.get('artifact_sha256', '')))) and
                bool(re.fullmatch(r'[0-9a-f]{64}', str(foundation.get('bundle_sha256', '')))))
    coherent = verified and status == 'consistent' and evidence.get('modeling_coherent') is True
    conflict = verified and (status == 'inconsistent' or evidence.get('modeling_coherent') is False)
    disposition = 'ready_for_review' if coherent else 'conflict' if conflict else 'unverified'
    explanation = ('The selected model has no detected logical contradiction or unsatisfiable named classes. '
                   'Review recorded product relationships and engineering constraints before acting.' if coherent else
                   'Logical contradictions or unsatisfiable classes need correction before relying on this model for decisions.' if disposition == 'conflict' else
                   'Logical consistency has not been established for this model. Review missing imports or run its consistency check.')
    keys = ('ontology_id', 'artifact_sha256', 'evidence_id', 'checked_at', 'status', 'reason',
            'consistency_verified', 'deductive_reasoner_executed', 'modeling_coherent',
            'unsatisfiable_class_count', 'foundation')
    return {**{key: evidence[key] for key in keys if key in evidence}, 'disposition': disposition,
            'consistency_verified': verified,
            'target_checks': {key: value for key, value in (evidence.get('target_checks') or {}).items()
                              if isinstance(key, str) and value in {'satisfiable', 'unsatisfiable', 'unknown'}} if isinstance(evidence.get('target_checks'), dict) else {},
            'unsatisfiable_classes_complete': evidence.get('unsatisfiable_classes_complete') is not False and (
                type(evidence.get('unsatisfiable_class_count')) is int and isinstance(evidence.get('unsatisfiable_classes'), list)
                and evidence['unsatisfiable_class_count'] == len(evidence['unsatisfiable_classes']) <= 200),
            'unsatisfiable_classes': [value for value in evidence.get('unsatisfiable_classes', [])[:200] if isinstance(value, str)] if isinstance(evidence.get('unsatisfiable_classes'), list) else [],
            'business_summary': explanation, 'advisory_only': True,
            'instance_conformance_established': False, 'publication_authorized': False,
            'graph_projection_verified': False,
            'next_action': 'Review source relationships and domain constraints' if coherent else
                           'Correct the model and rerun validation' if disposition == 'conflict' else
                           'Resolve imports and check the selected ontology'}


def target_conflict(report, candidate):
    """Hold established contradictions relevant to a proposed classification."""
    if report.get('consistency_verified') is not True: return False
    if report.get('status') == 'inconsistent': return True
    target = candidate.get('target_ontology_iri')
    if target in set(report.get('unsatisfiable_classes') or []): return True
    if target in (report.get('target_checks') or {}):
        return report['target_checks'][target] != 'satisfiable'
    # Absence from a sample is not proof that the selected class is satisfiable.
    # Existing complete small reports remain compatible during a rolling upgrade.
    if candidate.get('target_ontology_type') == 'Class' and report.get('modeling_coherent') is False:
        return report.get('unsatisfiable_classes_complete') is not True
    return False


def read_support(ontology_id, headers=None):
    """Bounded owning-service read. No reasoner execution or write replay."""
    if not ontology_id:
        return assessment({'status': 'not_selected'})
    if not any(k.lower() == 'authorization' and v for k, v in (headers or {}).items()):
        return assessment({'ontology_id': ontology_id, 'status': 'unknown', 'reason': 'semantic_read_access_required'})
    import httpx
    from backend.depo_platform.service_urls import service_url
    from backend.depo_platform.network import gateway_subscription_headers
    root = service_url('ONTOLOGY_SERVICE_URL', 'http://127.0.0.1:8011').rstrip('/')
    if not root.endswith('/api/v1'): root += '/api/v1'
    endpoint = root + '/ontologies/' + quote(str(ontology_id), safe='') + '/semantic-evidence'
    auth = {k: v for k, v in (headers or {}).items() if k.lower() == 'authorization'}
    auth.update(gateway_subscription_headers(endpoint))
    try:
        from backend.depo_platform.peer_http import peer_response
        response = peer_response('GET', endpoint, headers=auth, budget=5, response_limit=262144)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or body.get('ontology_id') != ontology_id:
            raise ValueError('Semantic evidence scope mismatch')
        # Recompute the business interpretation; do not trust upstream advice as authority.
        return assessment(body)
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, RuntimeError):
        return assessment({'ontology_id': ontology_id, 'status': 'unknown', 'reason': 'semantic_evidence_unavailable'})
