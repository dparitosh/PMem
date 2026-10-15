"""Rebuild analytics evidence from a committed receipt without loading XML."""
import json

from backend.artifact_store import ArtifactStore
from backend.depo_platform.execution_guard import ensure_execution_allowed


def run_result(result, manifest):
    if (manifest.get('output_manifest') or {}).get('evidence_status') == 'pending':
        result = {**result, 'evidence_status': 'pending', 'recovery_action': 'rebuild_evidence',
                  'partition_artifacts': {}, 'data_product_draft': None}
    return {**result, 'run_manifest': manifest}


def build_analytics_evidence(payload, receipt):
    if not isinstance(receipt, dict) or receipt.get('status') != 'completed' or not all(
            receipt.get(key) for key in ('schema', 'schema_digest', 'xml_digest')):
        raise ValueError('A committed analytics load receipt is required')
    result = {**receipt, 'ods_receipt': receipt, 'load_status': 'completed'}
    try:
        artifact = ArtifactStore().ingest_bytes(json.dumps(receipt, sort_keys=True).encode('utf-8'),
            filename='xml-analytics-load-receipt.json', kind='analytics-load-receipt', media_type='application/json')
    except Exception:
        # Memory/disk failures cannot roll back an already committed ODS load.
        # A lost execution lease must still propagate to the owner fence.
        ensure_execution_allowed()
        return {**result, 'evidence_status': 'pending', 'recovery_action': 'rebuild_evidence',
                'partition_artifacts': {}}
    return {**result, 'evidence_status': 'available',
        'partition_artifacts': {'accepted': artifact['artifact_id']},
        'data_product_draft': {'contract': 'postgres-xml-analytics-product-v1', 'product_kind': 'pipeline-evidence',
            'name': receipt['schema'] + ' XML analytics', 'domain': 'data-processing',
            'quality_status': 'schema-instance-validated', 'analytics_readiness': receipt['analytics_readiness'],
            'sources': [{'schema': receipt['schema'], 'schema_digest': receipt['schema_digest'], 'xml_digest': receipt['xml_digest']}],
            'artifacts': [{'artifact_id': value} for value in [payload['schema_artifact_id'], payload['xml_artifact_id'], artifact['artifact_id'], *(payload.get('schema_dependencies') or {}).values()]],
            'publication_requirements': ['Approved semantic release', 'Data-product steward approval']}}
