"""Immutable analytics input selections and conservative TRS change assessment.

These are PMem configuration extensions, not a full OSLC Config provider.
TRS notifications never authorize execution or publication.
"""
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse
from psycopg import Error as DatabaseError

from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.execution_guard import ensure_execution_allowed

log = logging.getLogger(__name__)
ROLES = {'source', 'ontology', 'mappings', 'kpi', 'shapes'}


def configuration_store():
    return PostgresRegistry('semantic_configurations')


def now():
    return datetime.now(timezone.utc).isoformat()


def capture_trs_start():
    """Capture before source resolution; earlier changes cannot invalidate a new baseline."""
    from backend.Services.oslc_trs_service import OSLCTRSService
    if not OSLCTRSService.is_enabled():
        return {'state': 'disabled', 'order': None}
    try:
        page = OSLCTRSService.change_log(after=0, limit=1)
        head = page.get('head_order')
        if type(head) is not int or head < 0:
            raise ValueError('TRS head position is unavailable')
        return {'state': 'captured', 'order': head}
    except (DatabaseError, RuntimeError, ValueError, OSError):
        log.warning('Analytics baseline TRS position is unavailable', exc_info=True)
        return {'state': 'unavailable', 'order': None}


def bind_context(payload, header, job_type):
    """Resolve only this deployment's retained contexts; never fetch a supplied URL."""
    if not header:
        return payload
    if job_type not in {'rdf-semantic-materialize', 'semantic-dataset-analysis', 'semantic-source-review'}:
        raise ValueError('This job does not support an analytics configuration context')
    path = urlparse(header).path
    match = re.fullmatch('/oslc/lifecycle/analytics-baselines/([0-9a-f]{64})', path)
    if not match:
        raise ValueError('Choose a retained analytics configuration context')
    from backend.Services.oslc_trs_service import OSLCTRSService
    expected = OSLCTRSService.base_url().rstrip('/') + path
    if header not in {path, expected}:
        raise ValueError('Configuration context must belong to this deployment')
    identifier = match.group(1)
    if payload.get('configuration_id') and payload['configuration_id'] != identifier:
        raise ValueError('Header and request configuration selections disagree')
    get_configuration(identifier)
    return {**payload, 'configuration_id': identifier}


def get_configuration(identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{64}', identifier):
        raise ValueError('Invalid analytics configuration identity')
    record = configuration_store().get(identifier)
    if not record or record.get('kind') != 'analytics-baseline':
        raise ValueError('Analytics configuration baseline not found')
    digest = hashlib.sha256(json.dumps(record.get('selections'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != identifier or record.get('configuration_id') != identifier:
        raise ValueError('Analytics baseline integrity check failed; restore its retained version')
    return record


def freeze_configuration(selections, actor=None):
    """Capture owned immutable artifacts; creation is not a release approval."""
    from .semantic_datasets import resolve_source
    if not isinstance(selections, list) or not 1 <= len(selections) <= 20:
        raise ValueError('A configuration requires 1–20 registered input selections')
    trs_start = capture_trs_start()
    frozen = []
    identities = set()
    for selection in selections:
        if not isinstance(selection, dict) or selection.get('role') not in ROLES:
            raise ValueError('Select a supported configuration input role')
        source_id, artifact = selection.get('source_id'), selection.get('artifact_id')
        if not isinstance(source_id, str) or not isinstance(artifact, str):
            raise ValueError('Each selection requires a registered source and retained artifact')
        identity = (selection['role'], source_id, artifact)
        if identity in identities:
            raise ValueError('Duplicate configuration input')
        identities.add(identity)
        source = resolve_source(source_id, artifact)
        ArtifactStore().resolve(artifact)  # Hash verification at the retention boundary.
        frozen.append({'role': selection['role'], 'source_id': source_id,
                       'artifact_id': artifact, 'source_version': source})
    if sum(item['role'] == 'source' for item in frozen) != 1:
        raise ValueError('A configuration requires exactly one primary source')
    frozen.sort(key=lambda item: (item['role'], item['source_id'], item['artifact_id']))
    identifier = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    store = configuration_store()
    with store.advisory_lock(identifier) as acquired:
        if not acquired:
            raise RuntimeError('This configuration is being prepared; retry to reconcile')
        previous = store.get(identifier)
        if previous:
            return get_configuration(identifier)
        record = {'configuration_id': identifier, 'kind': 'analytics-baseline',
                  'selections': frozen, 'created_at': now(), 'created_by': actor,
                  'configuration_context': '/oslc/lifecycle/analytics-baselines/' + identifier,
                  'approval_status': 'not_granted',
                  'trs_start_order': trs_start['order'], 'trs_start_state': trs_start['state'],
                  'scope': 'Immutable declared selections only; no automatic dependency discovery or full OSLC Config conformance'}
        # Same registry transaction retains the baseline and its pending notification.
        store.put_many({identifier: record, 'event:' + identifier: {
            'kind': 'trs-notification', 'status': 'pending', 'configuration_id': identifier}})
        return record


def preparation_configuration(payload):
    """Replaying a baseline uses its frozen ownership evidence, not today's latest."""
    identifier = payload.get('configuration_id')
    if identifier:
        baseline = get_configuration(identifier)
    else:
        selections = [{'role': 'source', 'source_id': payload.get('source_id'),
                       'artifact_id': payload.get('artifact_id')}]
        dependencies = payload.get('configuration_inputs', [])
        if not isinstance(dependencies, list) or any(not isinstance(item, dict) or item.get('role') == 'source' for item in dependencies):
            raise ValueError('Additional configuration selections must be dependency roles')
        selections.extend(dependencies)
        if payload.get('shape_artifact_id'):
            shape = {'role': 'shapes', 'source_id': payload.get('shape_source_id') or payload.get('source_id'),
                     'artifact_id': payload['shape_artifact_id']}
            if shape not in selections:
                selections.append(shape)
        baseline = freeze_configuration(selections, payload.get('execution_actor'))
    source = next(item for item in baseline['selections'] if item['role'] == 'source')
    if (source['source_id'], source['artifact_id']) != (payload.get('source_id'), payload.get('artifact_id')):
        raise ValueError('Preparation source differs from the selected configuration baseline')
    if identifier and payload.get('configuration_inputs'):
        raise ValueError('A retained baseline cannot be amended; create a new configuration')
    for item in baseline['selections']:
        ArtifactStore().resolve(item['artifact_id'])
    shapes = [item for item in baseline['selections'] if item['role'] == 'shapes']
    if len(shapes) > 1:
        raise ValueError('Select one SHACL rule artifact per preparation')
    if payload.get('shape_artifact_id') and (not shapes or shapes[0]['artifact_id'] != payload['shape_artifact_id']):
        raise ValueError('SHACL rules differ from the configuration baseline')
    if payload.get('shape_source_id') and (not shapes or shapes[0]['source_id'] != payload['shape_source_id']):
        raise ValueError('SHACL source differs from the configuration baseline')
    return baseline, source, shapes[0] if shapes else None


def pin_preparation_input(payload):
    """Resolve once, before retaining an input that queues/retries may replay."""
    baseline, _, _ = preparation_configuration(payload)
    pinned = {**payload, 'configuration_id': baseline['configuration_id']}
    # The immutable baseline owns these declarations after resolution. Sending
    # them again alongside an existing baseline would be an attempted amendment.
    pinned.pop('configuration_inputs', None)
    return pinned


def notify_configuration(identifier):
    """At-least-once TRS delivery; duplicate Creation hints do not replay writes."""
    from backend.Services.oslc_trs_service import OSLCTRSService
    store = configuration_store()
    key = 'event:' + identifier
    pending = store.get(key)
    if pending and pending.get('status') == 'pending':
        result = OSLCTRSService.publish_event('/oslc/lifecycle/analytics-baselines/' + identifier,
                                            'Creation', title='Analytics input baseline',
                                            metadata={'configuration_id': identifier})
        if result.get('status') != 'disabled':
            store.put(key, {**pending, 'status': 'delivered', 'delivered_at': now()})


def source_path(source_id):
    # Match only resources actually exposed by the existing lifecycle service.
    if source_id.startswith('catalog:'):
        return '/oslc/lifecycle/products/' + quote(source_id[len('catalog:'):], safe='')
    return None


def review_dataset(dataset_id, configuration_id=None):
    """One existing worker/schedule per dataset, with a durable TRS checkpoint."""
    from backend.Services.oslc_trs_service import OSLCTRSService
    from .semantic_datasets import resolve_source
    if not isinstance(dataset_id, str) or not re.fullmatch('[0-9a-f]{64}', dataset_id):
        raise ValueError('Select a retained semantic dataset')
    store = PostgresRegistry('semantic_refresh_reviews')
    with store.advisory_lock(dataset_id) as acquired:
        if not acquired:
            raise RuntimeError('This dataset is already being assessed')
        with store._connect() as db, db.cursor() as cursor:
            cursor.execute('SELECT metadata FROM depo_semantic_datasets WHERE dataset_id=%s', (dataset_id,))
            row = cursor.fetchone()
        if not row:
            raise ValueError('Semantic dataset not found')
        receipt = row[0]
        if configuration_id and receipt.get('configuration_id') != configuration_id:
            raise ValueError('Dataset does not belong to the selected configuration')
        if not receipt.get('configuration_id'):
            raise ValueError('This older snapshot needs a configuration baseline before change assessment')
        baseline = get_configuration(receipt['configuration_id'])
        previous = store.get(dataset_id) or {}
        after = previous.get('trs_after', baseline.get('trs_start_order') or 0)
        missing_start = baseline.get('trs_start_state') != 'captured'
        findings = []
        # Always reconcile selected source revisions: TRS publisher coverage is partial.
        for item in baseline['selections']:
            ensure_execution_allowed()
            try:
                current = resolve_source(item['source_id'], item['artifact_id'])
                if current != item['source_version']:
                    findings.append({'role': item['role'], 'source_id': item['source_id'], 'reason': 'registered_revision_changed'})
                ArtifactStore().resolve(item['artifact_id'])
            except (ValueError, OSError, FileNotFoundError):
                findings.append({'role': item['role'], 'source_id': item['source_id'], 'reason': 'source_or_retained_artifact_requires_review'})
        paths = {unquote(source_path(item['source_id'])) for item in baseline['selections'] if source_path(item['source_id'])}
        trs_state = 'unavailable'
        try:
            notify_configuration(baseline['configuration_id'])
            if OSLCTRSService.is_enabled():
                page = OSLCTRSService.change_log(after=after, limit=200)
                trs_state = 'gap_requires_review' if page['rebase_required'] else 'more_events_pending' if len(page['events']) >= 200 else 'page_assessed'
                if page.get('head_order', after) < after:
                    trs_state = 'gap_requires_review'
                for event in page['events']:
                    path = unquote(urlparse(event['resource_uri']).path)
                    if path in paths or path == '/oslc/trs/base':
                        findings.append({'reason': 'tracked_resource_changed', 'event_type': event['event_type'], 'order': event['order']})
                after = page['next_after']
            else:
                trs_state = 'disabled'
        except (RuntimeError, ValueError, OSError):
            log.warning('TRS analytics assessment unavailable for dataset %s', dataset_id, exc_info=True)
        if previous.get('status') == 'refresh_required' and not findings:
            findings = [{'reason':'previous_assessment_requires_refresh','assessed_at':previous.get('assessed_at')}]
        status = 'refresh_required' if findings or previous.get('status') == 'refresh_required' else 'review_required' if missing_start or trs_state != 'page_assessed' or previous.get('trs_gap_unresolved') else 'no_selected_source_change_detected'
        result = {'dataset_id': dataset_id, 'configuration_id': baseline['configuration_id'],
                  'status': status, 'findings': findings, 'trs_state': trs_state, 'trs_after': after,
                  'trs_gap_unresolved': missing_start or trs_state == 'gap_requires_review' or previous.get('trs_gap_unresolved', False),
                  'assessed_at': now(), 'publication_changed': False,
                  'scope': 'Selected source revisions and one TRS page; not a completeness certificate. Existing published versions are retained.'}
        # Checkpoint and findings are one durable record. Lease failure cannot advance it.
        ensure_execution_allowed()
        store.put(dataset_id, result)
        return result


def execute_review(runner, payload, *, correlation_id):
    assessment = review_dataset(payload.get('dataset_id'), payload.get('configuration_id'))
    return {**assessment, 'status': 'completed', 'assessment_status': assessment['status'],
            'job_type': 'semantic-source-review',
            'execution_status': 'completed', 'correlation_id': correlation_id}
