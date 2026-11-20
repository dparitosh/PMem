"""A bounded dossier over native evidence, never a second approval authority."""
import hashlib
import json
import re
from urllib.parse import quote
from backend.ontology_service.merge_plan import PLAN_SCHEMA, merge_plan_digest, valid_merge_order


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def build_dossier(kind, record, summary, uri):
    if kind=='releases':
        from .release_changes import dossier
        return dossier(record,uri)
    if kind=='publications' and record.get('change_request'):return ontology_publication_dossier(record,summary,uri)
    if kind=='product_changes':return product_dossier(record,summary,uri)
    if kind=='workflow_changes':return workflow_definition_dossier(record,summary,uri)
    if kind=='import_changes':return import_load_dossier(record,summary,uri)
    if kind=='pipeline' and record.get('change_request'):return pipeline_dossier(record,summary,uri)
    if kind=='bridges' and record.get('change_request'):
        return mapping_dossier(record,summary,uri)
    members = []
    complete = False
    plan_digest = None
    native_result_linked = False
    if kind == 'merges':
        sources = record.get('sources')
        expected = record.get('source_ontology_ids')
        if isinstance(sources, list) and 2 <= len(sources) <= 16:
            for source in sources:
                if (isinstance(source, dict) and isinstance(source.get('ontology_id'), str)
                    and 0 < len(source['ontology_id']) <= 300
                    and isinstance(source.get('artifact_sha256'), str)
                    and re.fullmatch('[0-9a-f]{64}', source['artifact_sha256'])):
                    members.append({'identifier': source['ontology_id'],
                        'artifact_sha256': source['artifact_sha256'],
                        'title': str(source.get('ontology_name') or source['ontology_id'])[:240],
                        'workspace': '#/ontology?target=' + quote(source['ontology_id'], safe='')})
            ids = [member['identifier'] for member in members]
            complete = (len(members) == len(sources) and len(ids) == len(set(ids))
                and isinstance(expected, list) and ids == expected)
        turtle = record.get('turtle')
        policy = record.get('governance_policy_sha256')
        if complete and record.get('preview_id') == summary['identifier'] and isinstance(turtle, str) and turtle and isinstance(policy, str) and re.fullmatch('[0-9a-f]{64}', policy):
            plan_digest = merge_plan_digest(record)
        applied = record.get('applied_result')
        ontology = applied.get('ontology') if isinstance(applied, dict) else None
        provenance = ontology.get('provenance') if isinstance(ontology, dict) else None
        native_result_linked = (bool(plan_digest) and isinstance(provenance, dict)
            and applied.get('preview_id') == summary['identifier']
            and provenance.get('preview_id') == summary['identifier']
            and provenance.get('source_ontology_ids') == expected
            and provenance.get('approved_by') == summary.get('authorization_actor')
            and bool(summary.get('authorization_actor')))
    change = record.get('change_request') if kind == 'merges' else None
    change = change if isinstance(change, dict) else {}
    order = change.get('order') or {}
    bound_order = bool(plan_digest) and valid_merge_order(change, summary['identifier'], plan_digest)
    baseline_digest = digest(members) if complete else None
    return {'identifier': summary['record_key'], 'uri': uri + '#dossier',
        'type': 'urn:depo:change-control:NativeChangeDossier', 'read_only': True,
        'request': {'identifier':summary['identifier'], 'uri': uri + '#request-summary', 'type': 'urn:depo:change-control:NativeRequestSummary',
            'resource_type': 'oslc_cm:ChangeRequest' if kind == 'merges' else 'urn:depo:change-control:EvidenceRecord',
            'state': str(change.get('state')) if change else 'Retained proposal; review in owning workflow' if kind == 'merges' else 'Retained evidence; not a change request',
            'owner_service': summary['owner_service'], 'workspace': summary['workspace']},
        'baseline': {'uri': uri + '#baseline', 'type': 'urn:depo:change-control:RecordedBaseline',
            'status': 'Exact retained source snapshot' if complete else 'Incomplete or not recorded',
            'members': members, 'snapshot_digest': baseline_digest,
            'currentness': 'Not revalidated; native service must check current source artifacts before execution',
            'configuration_conformance': 'Recorded snapshot; not a claim of full OSLC Configuration Management conformance'},
        'release': {'type': 'urn:depo:change-control:NativeExecutionSummary',
            'state': 'Native merge result linked' if native_result_linked else summary['review_state'],
            'plan_schema': PLAN_SCHEMA if plan_digest else None, 'plan_digest': plan_digest, 'authorization_actor': summary.get('authorization_actor'),
            'execution_state': summary['execution_state'], 'delivery_state': summary['delivery_state'],
            'native_result_linked': native_result_linked,
            'order': {key:order.get(key) for key in ('order_id','plan_digest','authorized_by','operation','publish')} if bound_order else None,
            'authority': 'Only the owning service can authorize and execute; this dossier grants no write permission'},
        'policy_assessment': summary['policy_assessment'],
        'publication_receipt_retained': summary['receipt_retained']}


def mapping_dossier(record,summary,uri):
    from backend.agentic_service.bridge_change import retained_plan,valid_order,PLAN_SCHEMA as schema
    change=record['change_request'];plan=retained_plan(record)
    order=change.get('order') or {}
    bound=bool(plan) and valid_order(change,record.get('preview_id'),summary['identifier'],plan)
    snapshot=record.get('snapshot') or {}
    return {'identifier':summary['record_key'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':summary['identifier'],'type':'urn:depo:change-control:NativeRequestSummary','resource_type':'oslc_cm:ChangeRequest',
            'state':change.get('state'),'owner_service':'agentic','workspace':summary['workspace']},
        'baseline':{'status':'Retained source and ontology fingerprints' if plan else 'Incomplete mapping evidence',
            'members':[],'snapshot_digest':digest(snapshot) if plan else None,
            'currentness':'Not revalidated; native publication checks the current source and ontology snapshot',
            'configuration_conformance':'Recorded mapping snapshot; not full configuration-management conformance'},
        'release':{'type':'urn:depo:change-control:NativeExecutionSummary','plan_schema':schema,'plan_digest':plan,
            'operation_identifier':summary['identifier'],'state':summary['review_state'],
            'execution_state':summary['execution_state'],'delivery_state':summary['delivery_state'],
            'authorization_actor':summary.get('authorization_actor'),
            'order':{key:order.get(key) for key in ('order_id','request_id','plan_digest','authorized_by','operation','publish')} if bound else None,
            'authority':'Native mapping policy, source validation and graph receipt remain authoritative'},
        'mapping_scope':{'candidate_ids':change.get('candidate_ids',[]),'preview_digest':record.get('preview_digest'),
            'ontology_id':record.get('ontology_id'),'import_task_id':record.get('import_task_id')},
        'publication_receipt_retained':summary['receipt_retained'],'policy_assessment':summary['policy_assessment']}


def product_dossier(record,summary,uri):
    from backend.data_product_service.product_change import valid_order,PLAN_SCHEMA as schema
    change=record.get('change_request') or {};order=change.get('order') or {}
    return {'identifier':summary['record_key'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':summary['identifier'],'type':'urn:depo:change-control:NativeRequestSummary',
            'resource_type':'oslc_cm:ChangeRequest','state':change.get('state'),'owner_service':'dataProducts'},
        'baseline':{'status':'Retained artifact checksums and product release contract','members':[],
            'snapshot_digest':record.get('plan_digest'),'currentness':'Native publication validates current artifacts, lineage and approved semantic releases',
            'configuration_conformance':'Exact product contract; not full configuration-management conformance'},
        'release':{'type':'urn:depo:change-control:NativeExecutionSummary','state':summary['review_state'],
            'plan_schema':schema,'plan_digest':record.get('plan_digest'),'operation_identifier':summary['identifier'],
            'authorization_actor':summary.get('authorization_actor'),'execution_state':summary['execution_state'],'delivery_state':summary['delivery_state'],
            'order':{key:order.get(key) for key in ('order_id','plan_digest','operation','publish','authorized_by')} if valid_order(record) else None,
            'authority':'Native immutable packaging, approved release and catalog delivery checks remain authoritative'},
        'publication_receipt_retained':summary['receipt_retained'],'policy_assessment':summary['policy_assessment']}


def pipeline_dossier(record,summary,uri):
    from backend.data_pipeline_service.publication_change import valid_order,PLAN_SCHEMA as schema
    change=record['change_request'];plan=change.get('plan') or {};order=change.get('order') or {}
    return {'identifier':summary['record_key'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':summary['identifier'],'type':'urn:depo:change-control:NativeRequestSummary','resource_type':'oslc_cm:ChangeRequest','state':change.get('state'),'owner_service':'dataPipeline'},
        'baseline':{'status':'Retained accepted partition and publication destination','members':[],
            'snapshot_digest':change.get('plan_digest'),'currentness':'Native execution revalidates partition bytes and approved semantic release',
            'configuration_conformance':'Exact run snapshot; not full configuration-management conformance'},
        'release':{'type':'urn:depo:change-control:NativeExecutionSummary','state':summary['review_state'],
            'plan_schema':schema,'plan_digest':change.get('plan_digest'),'operation_identifier':summary['identifier'],
            'authorization_actor':summary.get('authorization_actor'),'execution_state':summary['execution_state'],'delivery_state':summary['delivery_state'],
            'order':{key:order.get(key) for key in ('order_id','plan_digest','operation','publish','authorized_by')} if valid_order(record) else None,
            'authority':'Canonical semantic publication and current graph receipt remain authoritative'},
        'publication_receipt_retained':summary['receipt_retained'],'policy_assessment':summary['policy_assessment']}


def ontology_publication_dossier(record,summary,uri):
    from backend.ontology_service.publication_change import valid_order,PLAN_SCHEMA as schema
    change=record['change_request'];order=change.get('order') or {}
    return {'identifier':summary['record_key'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':summary['identifier'],'type':'urn:depo:change-control:NativeRequestSummary','resource_type':'oslc_cm:ChangeRequest','state':change.get('state'),'owner_service':'ontology'},
        'baseline':{'status':'Retained ontology artifact and declared release','members':[],
            'snapshot_digest':change.get('plan_digest'),'currentness':'Native worker validates current artifact and lifecycle before graph dispatch',
            'configuration_conformance':'Exact ontology release snapshot; not full configuration-management conformance'},
        'release':{'type':'urn:depo:change-control:NativeExecutionSummary','state':summary['review_state'],
            'plan_schema':schema,'plan_digest':change.get('plan_digest'),'operation_identifier':summary['identifier'],
            'authorization_actor':summary.get('authorization_actor'),'execution_state':summary['execution_state'],'delivery_state':summary['delivery_state'],
            'order':{key:order.get(key) for key in ('order_id','plan_digest','operation','publish','authorized_by')} if valid_order(record) else None,
            'authority':'Native ontology lifecycle, publication worker and current graph receipt remain authoritative'},
        'publication_receipt_retained':summary['receipt_retained'],'policy_assessment':summary['policy_assessment']}


def workflow_definition_dossier(record,summary,uri):
    from backend.data_pipeline_service.definition_changes import valid_order,SCHEMA
    change=record['change_request'];plan=change.get('plan') or {};order=change.get('order') or {}
    return {'identifier':summary['record_key'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':summary['identifier'],'resource_type':'oslc_cm:ChangeRequest','state':change.get('state'),'owner_service':'dataPipeline'},
        'baseline':{'status':'Retained workflow definition and schedule parameters','members':[],
            'snapshot_digest':plan.get('definition_sha256'),'currentness':'Execution compares the exact definition and retained input before an atomic update',
            'configuration_conformance':'Workflow maintenance baseline; no data release or full configuration conformance implied'},
        'release':{'state':summary['review_state'],'plan_schema':SCHEMA,'plan_digest':change.get('plan_digest'),
            'operation_identifier':summary['identifier'],'authorization_actor':summary.get('authorization_actor'),
            'execution_state':summary['execution_state'],'delivery_state':summary['delivery_state'],
            'order':{key:order.get(key) for key in ('order_id','plan_digest','operation','authorized_by')} if valid_order(record) else None,
            'authority':'The owning pipeline service revalidates and atomically applies only the authorized workflow change'},
        'publication_receipt_retained':False,'maintenance_receipt_retained':bool(record.get('receipt')),
        'policy_assessment':summary['policy_assessment']}


def import_load_dossier(record,summary,uri):
    from backend.ingestion_service.import_change import valid,SCHEMA
    change=record['change_request'];plan=change['plan'];order=change.get('order') or {}
    return {'identifier':summary['record_key'],'uri':uri+'#dossier','type':'urn:depo:change-control:NativeChangeDossier','read_only':True,
        'request':{'identifier':summary['identifier'],'resource_type':'oslc_cm:ChangeRequest','state':change['state'],'owner_service':'ingestion'},
        'baseline':{'status':'Retained engineering rows and mapping configuration','members':[],
            'snapshot_digest':plan.get('rows_sha256'),'currentness':'Native dispatch validates rows, source metadata and load configuration',
            'configuration_conformance':'Exact import load baseline; not full configuration-management conformance'},
        'release':{'state':summary['review_state'],'plan_schema':SCHEMA,'plan_digest':change['plan_digest'],
            'operation_identifier':summary['identifier'],'authorization_actor':summary.get('authorization_actor'),
            'execution_state':summary['execution_state'],'delivery_state':summary['delivery_state'],
            'order':{key:order.get(key) for key in ('order_id','plan_digest','operation','authorized_by')} if valid(record) else None,
            'authority':'Native importer receipt; uncertain or partial loads require reconciliation and are never automatically retried'},
        'publication_receipt_retained':bool(record.get('receipt')),'policy_assessment':summary['policy_assessment']}
