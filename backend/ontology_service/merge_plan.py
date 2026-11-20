"""Versioned identity of the retained native merge instructions (not approval)."""
import hashlib
import json

PLAN_SCHEMA = 'nexus.native-merge-plan.v1'


def merge_plan_digest(record):
    plan = {'schema': PLAN_SCHEMA, 'preview_id': record['preview_id'],
        'sources': [{'ontology_id': item['ontology_id'], 'artifact_sha256': item['artifact_sha256']}
                    for item in record['sources']],
        'graph_sha256': hashlib.sha256(record['turtle'].encode('utf-8')).hexdigest(),
        'output': {field: record.get(field) for field in ('ontology_name', 'prefix', 'description')},
        'mapping_evidence': record.get('mapping_evidence'), 'changes': record.get('changes'),
        'recommended_version_bump': record.get('recommended_version_bump'),
        'governance_policy_sha256': record.get('governance_policy_sha256')}
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def valid_merge_order(change, preview_id, current_plan_digest=None):
    """Shared native/projection scope check; summary reads do not imply freshness."""
    import re
    if not isinstance(change, dict) or not isinstance(preview_id,str) or not preview_id:
        return False
    order = change.get('order')
    plan = change.get('plan_digest')
    from backend.depo_platform.approval_matrix import order_valid as matrix_order_valid
    return (matrix_order_valid(change) and change.get('request_id') == preview_id
        and change.get('state') in ('authorized','executing','executed','needs_recovery')
        and isinstance(plan,str) and re.fullmatch('[0-9a-f]{64}',plan) is not None
        and (current_plan_digest is None or plan == current_plan_digest)
        and isinstance(order,dict) and order.get('order_id') == preview_id
        and order.get('plan_digest') == plan
        and order.get('operation') == 'create_merged_draft' and order.get('publish') is False
        and isinstance(order.get('authorized_by'),str) and bool(order['authorized_by'].strip()))
