"""Configurable business numbering with immutable UUID identities in PostgreSQL."""
from contextlib import contextmanager
from time import monotonic, sleep
from datetime import datetime, timezone
from uuid import uuid4, UUID
from backend.mesh_store import PostgresRegistry

registry = PostgresRegistry('resource_identity_v1')
configuration = PostgresRegistry('resource_numbering_config_v1')
KINDS = {'CR':'Change request','CO':'Change order','WF':'Workflow','DS':'Data source','FILE':'Ingested file','RUN':'Processing run'}


@contextmanager
def _identity_lock(target, key):
    # Concurrent submissions wait briefly for the same sequence, without
    # holding a database transaction open or allowing unbounded blocking.
    deadline = monotonic() + 5
    while True:
        with target.advisory_lock(key) as acquired:
            if acquired:
                yield
                return
        if monotonic() >= deadline:
            raise RuntimeError('Object numbering is busy; retry the same action')
        sleep(0.02)


def scheme(kind, *, store=None):
    if kind not in KINDS: raise ValueError('Unsupported object type')
    target=store if store is not None else configuration
    return target.get('scheme:'+kind) or {'kind':kind,'prefix':kind,'include_year':True,'digits':6,'revision':0}


def _number(settings, year, value):
    return settings['prefix'] + ('-'+str(year) if settings['include_year'] else '') + '-' + str(value).zfill(settings['digits'])


def identify(kind, source, identifier, *, name='', links=None, store=None):
    if kind not in KINDS or not isinstance(identifier,str) or not identifier:
        raise ValueError('An object type and retained identity are required')
    target=store if store is not None else registry
    key='id:'+kind+':'+source+':'+identifier
    with _identity_lock(target, 'identity:'+kind):
        current=target.get(key)
        if current: return current
        settings=scheme(kind,store=store);year=datetime.now(timezone.utc).year
        counter='counter:'+kind+(':'+str(year) if settings['include_year'] else '')
        value=int((target.get(counter) or {}).get('value',0))+1
        number=_number(settings,year,value)
        object_id=str(uuid4())
        if kind in {'RUN','FILE'}:
            try: object_id=str(UUID(identifier))
            except ValueError: pass
        record={'object_id':object_id,'number':number,'kind':kind,'source':source,
                'identifier':identifier,'name':str(name)[:240],'created_at':datetime.now(timezone.utc).isoformat(),
                'links':{key:str(value)[:500] for key,value in (links or {}).items() if key in {'artifact_id','content_sha256','workflow_id','run_id','parent_file_id'} and value}}
        target.put_many({counter:{'value':value},key:record,'number:'+number:{'identity_key':key},'uuid:'+object_id:{'identity_key':key}})
        return record


def allocate(kind,source,identifier,*,store=None):
    return identify(kind,source,identifier,store=store)['number']


def ensure(change,source,identifier,*,store=None):
    if not isinstance(change,dict):return
    if not change.get('request_number'):
        identity=identify('CR',source,identifier,store=store)
        change.update(request_number=identity['number'],request_uuid=identity['object_id'])
    order=change.get('order')
    if isinstance(order,dict) and order.get('authorized_by') and not order.get('order_number'):
        identity=identify('CO',source,identifier,store=store)
        order.update(order_number=identity['number'],order_uuid=identity['object_id'])


def list_schemes():
    result=[];year=datetime.now(timezone.utc).year
    for kind,label in KINDS.items():
        settings=scheme(kind)
        counter='counter:'+kind+(':'+str(year) if settings['include_year'] else '')
        value=int((registry.get(counter) or {}).get('value',0))+1
        result.append({**settings,'label':label,'next_preview':_number(settings,year,value)})
    return result


def update_scheme(kind,values,actor):
    import re
    if kind not in KINDS or not isinstance(actor,str) or not actor.strip():raise ValueError('A verified administrator and object type are required')
    prefix=values.get('prefix');digits=values.get('digits');include_year=values.get('include_year')
    if not isinstance(prefix,str) or not re.fullmatch('[A-Z][A-Z0-9]{0,11}',prefix):raise ValueError('Prefix must be 1–12 uppercase letters or digits, starting with a letter')
    if type(digits) is not int or not 4<=digits<=10 or type(include_year) is not bool:raise ValueError('Use 4–10 sequence digits and a year setting')
    with configuration.advisory_lock('numbering-schemes') as acquired:
        if not acquired:raise RuntimeError('Numbering settings are busy')
        with registry.advisory_lock('identity:'+kind) as locked:
            if not locked:raise RuntimeError('Object numbering is busy')
            owner=configuration.get('prefix:'+prefix)
            if owner and owner.get('kind')!=kind:raise ValueError('This prefix belongs to another object type')
            if any(other!=kind and scheme(other)['prefix']==prefix for other in KINDS):raise ValueError('Use a distinct prefix for each object type')
            previous=scheme(kind)
            if values.get('expected_revision') != previous['revision']:raise ValueError('Numbering settings changed; refresh before saving')
            result={'kind':kind,'prefix':prefix,'digits':digits,'include_year':include_year,
                    'revision':previous['revision']+1,'updated_by':actor,'updated_at':datetime.now(timezone.utc).isoformat()}
            configuration.put_many({'scheme:'+kind:result,'prefix:'+prefix:{'kind':kind},'prefix:'+previous['prefix']:{'kind':kind}})
            return result


def resolve_object(object_id):
    pointer=registry.get('uuid:'+object_id)
    return registry.get(pointer['identity_key']) if pointer else None


def file_reference(identity):
    return {'file_id':identity['object_id'],'file_number':identity['number'],
            'filename':identity['name'],**identity.get('links',{})}
