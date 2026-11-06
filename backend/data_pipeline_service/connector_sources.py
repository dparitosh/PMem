"""Profile-bound acquisition. Browser input can select aliases, never SDK options.

Profiles are operator configuration; credentials are server environment references.
Source bytes and tool output are untrusted data, never executable instructions.
"""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from backend.mesh_store import PostgresRegistry
from backend.artifact_store import ArtifactStore
from backend.depo_platform.semantica_ingestors import INGESTORS

KINDS = tuple(k for k in INGESTORS if k not in {'File','XML','Ontology','REST'})
store = PostgresRegistry('connector_sources')
submissions = PostgresRegistry('connector_submissions')
MAX_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 1000
TIMEOUT = 45
ID = re.compile(r'[a-z][a-z0-9-]{2,62}$')


def profiles():
    try:
        raw = json.loads(os.getenv('DEPO_CONNECTOR_PROFILES', '{}'))
    except ValueError:
        raise ValueError('DEPO_CONNECTOR_PROFILES must be a JSON object') from None
    if not isinstance(raw, dict) or len(raw)>64:
        raise ValueError('Configure at most 64 connector profiles')
    for key, value in raw.items():
        if not ID.fullmatch(key) or not isinstance(value,dict) or set(value)-{'name','kind','resources','connection_ref'}:
            raise ValueError('Invalid connector profile fields')
        if value.get('kind') not in KINDS or not isinstance(value.get('name'),str) or not 1<=len(value['name'])<=200:
            raise ValueError('Configure a reviewed connector kind and name')
        resources=value.get('resources')
        if not isinstance(resources,dict) or not 1<=len(resources)<=100 or any(not ID.fullmatch(k) or not isinstance(v,str) or not 1<=len(v)<=2000 for k,v in resources.items()):
            raise ValueError('Connector resources must map safe aliases to server-owned locations')
        if not isinstance(value.get('connection_ref'),str) or not re.fullmatch(r'DEPO_CONNECTOR_SECRET_[A-Z0-9_]{1,64}',value['connection_ref']):
            raise ValueError('Configure a dedicated DEPO_CONNECTOR_SECRET_ reference')
    return raw


def profile_digest(profile):
    return hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def public_profiles():
    return [{'profile_id':key,'name':p['name'],'kind':p['kind'],'resources':list(p['resources']),
             'configured':bool(os.getenv(p['connection_ref']))} for key,p in profiles().items()]


def register(payload,actor):
    if set(payload)-{'source_id','name','profile_id','resource','approved_by','approval_token'}:
        raise ValueError('Connector registration accepts only named profile and resource references')
    if not isinstance(payload.get('source_id'),str) or not ID.fullmatch(payload['source_id']):
        raise ValueError('Choose a 3–63 character lowercase source identifier')
    if not isinstance(payload.get('name'),str) or not 1<=len(payload['name'].strip())<=200:
        raise ValueError('Source name is required')
    profile=profiles().get(payload.get('profile_id'))
    if not profile or payload.get('resource') not in profile['resources']:
        raise ValueError('Select an operator-configured source profile and resource')
    from .job_definitions import now
    record=({key:payload[key] for key in ('source_id','name','profile_id','resource')} |
        {'kind':profile['kind'],'profile_digest':profile_digest(profile),'created_by':actor,'created_at':now()})
    try:return store.create(payload['source_id'],record)
    except FileExistsError:
        existing=store.get(payload['source_id'])
        if existing and all(existing.get(k)==v for k,v in record.items() if k!='created_at'):return existing
        raise


def resolved(source):
    profile=profiles().get(source['profile_id'])
    if not profile or source.get('profile_digest')!=profile_digest(profile):
        raise ValueError('Source profile changed; register and review a new source version')
    secret=os.getenv(profile['connection_ref'])
    if not secret:
        raise ValueError('Source connection is not configured in the server environment')
    try: settings=json.loads(secret)
    except ValueError: raise ValueError('Source connection must contain a server JSON configuration') from None
    if not isinstance(settings,dict): raise ValueError('Source connection must be a JSON object')
    return profile['kind'],profile['resources'][source['resource']],settings


def acquire(source):
    # Parent does not resolve secrets or load external SDKs. The existing semantic
    # child runtime owns acquisition; the durable pipeline worker owns persistence.
    from .rest_sources import _worker_command
    from backend.depo_platform.operations import current_operation,remaining_seconds
    context=current_operation();budget=min(TIMEOUT,remaining_seconds(context.deadline_at)) if context else TIMEOUT
    command=_worker_command();command[-1]='backend.data_pipeline_service.connector_worker'
    try:
        result=subprocess.run(command,input=json.dumps({'source':source,'timeout_seconds':max(1,budget-1)}),capture_output=True,text=True,
            encoding='utf-8',timeout=budget,cwd=str(Path(__file__).resolve().parents[2]),
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:
        raise ValueError('Connector acquisition exceeded its absolute time limit') from None
    messages=[line[12:] for line in result.stdout.splitlines() if line.startswith('DEPO_RESULT:')]
    if result.returncode or not messages: raise ValueError('Connector acquisition failed; check profile, required SDK and source access')
    try: data=json.loads(messages[-1])
    except ValueError: raise ValueError('Connector returned invalid acquisition evidence') from None
    if 'records' not in data or not isinstance(data['records'],list) or len(data['records'])>MAX_RECORDS or len(messages[-1].encode())>MAX_BYTES:
        raise ValueError('Connector output exceeds the reviewed acquisition limits')
    return data


def execute(runner,payload,*,correlation_id):
    source=store.get(payload.get('source_id',''))
    if not source: raise ValueError('Registered connector source was not found')
    data=acquire(source)
    artifact=ArtifactStore().ingest_bytes(json.dumps(data['records'],ensure_ascii=False).encode(),
        filename=source['source_id']+'.json',kind='connector-records',media_type='application/json',
        provenance={'source_id':source['source_id'],'profile_digest':source['profile_digest'],'correlation_id':correlation_id})
    return {'status':'completed','counts':{'records':len(data['records'])},'partition_artifacts':{'source':artifact['artifact_id']},
        'source_id':source['source_id'],'semantic_validation':'not_assessed','publication':'not_attempted'}
