"""Shared adapter to the existing Semantica/PostgreSQL policy service.

A policy-store or evidence-write failure is a hold, never a policy pass.
"""
from __future__ import annotations
import math
import logging
from backend.depo_platform.peer_http import peer_response
from backend.depo_platform.network import service_bearer_headers, bounded_timeout_seconds
from backend.depo_platform.service_urls import service_url


def unavailable_assessment(operation, exc):
    logging.getLogger(__name__).warning("Shared decision policy unavailable (%s)", type(exc).__name__)
    return {"status": "unavailable", "compliant": None, "blocking": True, "checks": [],
            "operation": operation, "message": "Decision policy assessment unavailable; retry after checking the policy service and PostgreSQL."}


def assess_decisions(operation, decisions):
    try:
        base = service_url('ONTOLOGY_SERVICE_URL', 'http://127.0.0.1:8011/api/v1')
        if not base.endswith('/api/v1'):
            base += '/api/v1'
        endpoint = base + '/ontologies/policies/evaluate'
        response = peer_response('POST', endpoint,
            headers=service_bearer_headers('ONTOLOGY_APPROVAL_TOKEN', service_name='ontology decision policy', endpoint=endpoint),
            budget=bounded_timeout_seconds('DECISION_POLICY_TIMEOUT_SECONDS', default=30, maximum=120),
            json={'operation': operation, 'decisions': decisions})
        response.raise_for_status()
        report = response.json()
        from backend.depo_platform.bridge_contract import digest
        if (not isinstance(report, dict) or report.get('operation') != operation
                or report.get('decision_digest') != digest(decisions)
                or not isinstance(report.get('assessment_id'), str)
                or not report['assessment_id'].startswith('decision-policy-')
                or report.get('status') not in {'not_configured', 'passed', 'blocked'}
                or type(report.get('blocking')) is not bool
                or not isinstance(report.get('checks'), list)
                or not isinstance(report.get('blocked_decision_indices'), list)
                or any(type(i) is not int or not 0 <= i < len(decisions) for i in report['blocked_decision_indices'])
                or report['blocking'] != bool(report['blocked_decision_indices'])
                or any(not isinstance(c, dict) or type(c.get('decision_index')) is not int
                       or not 0 <= c['decision_index'] < len(decisions) or type(c.get('compliant')) is not bool for c in report['checks'])
                or report['blocking'] != (report['status'] == 'blocked')
                or (report['status'] == 'not_configured' and (report.get('compliant') is not None or report['checks']))
                or (report['status'] != 'not_configured' and report.get('compliant') is not (not report['blocking']))):
            raise ValueError('Invalid or mismatched decision policy evidence')
        return report
    except Exception as exc:
        return unavailable_assessment(operation, exc)


def decision(confidence=None, **metadata):
    valid = type(confidence) in (int, float) and math.isfinite(confidence) and 0 <= confidence <= 1
    return {**metadata, "confidence": confidence if valid else 0,
            "confidence_basis": "matching_score_not_probability" if valid else "not_established",
            "outcome": metadata.get("outcome", "flagged"), "decision_maker": metadata.get("decision_maker", "ontology-steward"),
            "reasoning": metadata.get("reasoning", "Candidate evidence for review; does not authorize publication.")}


def assess_recommendation(result, kind, scope):
    from backend.depo_platform.bridge_contract import digest
    allowed_scope = {key: value for key, value in (scope or {}).items()
                     if key in {'ontology_id', 'prefix', 'ontology_prefix', 'node_id', 'element_id', 'import_id'}
                     and isinstance(value, str) and len(value) <= 500} if isinstance(scope, dict) else {}
    report = assess_decisions("recommendations", [decision(kind=kind, result_digest=digest(result), scope=allowed_scope,
        decision_maker="recommendation-service", reasoning="Graph-derived advisory result; impact and similarity are not calibrated confidence.")])
    return {**result, "decision_policy": report, "advisory_only": True}


def recommendation_policy_text(result):
    status = result['decision_policy']['status']
    return {"not_configured": "No shared decision policy is configured; this is graph-derived advice, not approval.",
            "passed": "Configured decision policies passed; this advice does not authorize changes.",
            "blocked": "Configured decision policy holds this advice. Review the policy findings before acting.",
            "unavailable": "Decision policy evidence is unavailable. Treat this advice as unverified."}.get(status,
            "Decision policy evidence is unverified.")


def policy_blocks(report):
    """Interpret explicit absence separately from failure; support rolling-upgrade peers."""
    if not isinstance(report, dict):
        return True
    checks = report.get('checks', [])
    if not isinstance(checks, list) or any(not isinstance(c, dict) or c.get('compliant') is not True for c in checks):
        return True
    if 'status' not in report:
        # Older peers return compliance only; never coerce truthy strings.
        return report.get('compliant') is not True
    if report.get('blocking') is not False:
        return True
    if report['status'] == 'not_configured':
        return report.get('compliant') is not None or bool(checks)
    return report['status'] != 'passed' or report.get('compliant') is not True or not checks
