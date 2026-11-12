"""Reporting replica transactions. Checkpoints and derived rows share one commit."""
import hashlib,json,re,uuid
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from urllib.parse import urlsplit
from psycopg.types.json import Jsonb
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.execution_guard import ensure_execution_allowed


def registry():return PostgresRegistry('reporting_replica')
def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def resource_key(uri):
    parsed=urlsplit(uri)
    return hashlib.sha256((parsed.path+('?' + parsed.query if parsed.query else '')).encode()).hexdigest()


def validate_definition(value):
    if not isinstance(value,dict) or set(value)-{'ontology_ids','resource_types','max_lag_seconds'}:
        raise ValueError('Select ontology versions, optional record types and a freshness limit')
    ids=value.get('ontology_ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',i) for i in ids):
        raise ValueError('Select 1–20 exact registered ontology identities')
    kinds=value.get('resource_types',[])
    if not isinstance(kinds,list) or len(kinds)>20 or any(not isinstance(i,str) or len(i)>800 or not i.startswith(('urn:','https://','http://')) for i in kinds):
        raise ValueError('Select up to 20 declared RDF type IRIs')
    lag=value.get('max_lag_seconds',300)
    if type(lag) is not int or not 60<=lag<=86400:raise ValueError('Freshness limit must be 60–86400 seconds')
    return {'ontology_ids':sorted(set(ids)),'resource_types':sorted(set(kinds)),'max_lag_seconds':lag}


def create(name,definition,actor):
    definition=validate_definition(definition)
    if not isinstance(name,str) or not 1<=len(name.strip())<=200:raise ValueError('Reporting dataset name is required')
    identifier=digest({'name':name.strip(),'definition':definition})
    with registry()._connect() as db,db.transaction(),db.cursor() as c:
        c.execute("INSERT INTO depo_reporting_feeds(feed_id,name,definition,status,created_by) VALUES(%s,%s,%s,'draft',%s) ON CONFLICT DO NOTHING",(identifier,name.strip(),Jsonb(definition),actor))
    return identifier


def approve(identifier,actor):
    with registry()._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SELECT definition FROM depo_reporting_feeds WHERE feed_id=%s FOR UPDATE',(identifier,));row=c.fetchone()
        if not row:raise ValueError('Reporting dataset not found')
        definition=validate_definition(row[0])
        # The approved selection is explicit; changing it creates a different identity.
        c.execute("UPDATE depo_reporting_feeds SET status='approved',approved_by=COALESCE(approved_by,%s),updated_at=now() WHERE feed_id=%s",(actor,identifier))


def get(identifier,cursor=None):
    if not isinstance(identifier,str) or not re.fullmatch("[0-9a-f]{64}",identifier):raise ValueError("Select a retained reporting dataset")
    if cursor is None:
        with registry()._connect() as db,db.cursor() as c:return get(identifier,c)
    cursor.execute('SELECT feed_id,name,definition,status,created_by,approved_by,state FROM depo_reporting_feeds WHERE feed_id=%s',(identifier,))
    row=cursor.fetchone()
    if not row:raise ValueError('Reporting dataset not found')
    return dict(zip(('feed_id','name','definition','status','created_by','approved_by','state'),row))


def list_feeds():
    with registry()._connect() as db,db.cursor() as c:
        c.execute('SELECT feed_id FROM depo_reporting_feeds ORDER BY updated_at DESC,feed_id LIMIT 101')
        ids=[row[0] for row in c.fetchall()]
    return {'feeds':[with_freshness(get(i)) for i in ids[:100]],'limited':len(ids)>100}


def with_freshness(feed):
    state=feed['state'];last=state.get('last_assessed_at');age=None
    if last:age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds())
    freshness='refresh_failed' if state.get('last_error') else 'not_initialized' if not state.get('active_generation') else 'refreshing' if state.get('phase')=='base' else 'stale' if age is None or age>feed['definition']['max_lag_seconds'] else state.get('freshness','unknown')
    return {**feed,'freshness':freshness,'age_seconds':round(age,1) if age is not None else None,
            'coverage':'Tracked feed and selected exact ontology IDs; publisher coverage is partial, not a whole-source completeness claim.'}


def normalise(uri,payload,definition):
    if not isinstance(payload,dict) or not isinstance(payload.get('properties'),dict):raise ValueError('OSLC resource has no property object')
    props=payload['properties'];ontology=str(props.get('ontology_id') or '')
    rawtypes=[payload.get('rdf:type',[]),props.get('rdf_types',[]),props.get('types',[])]
    types=sorted({v for values in rawtypes for v in (values if isinstance(values,list) else [values]) if isinstance(v,str) and v})
    if ontology not in definition['ontology_ids'] or definition['resource_types'] and not set(types)&set(definition['resource_types']):return None
    if len(uri.encode())>4000 or len(types)>200:raise ValueError('OSLC resource identity/type bounds exceeded')
    values={**props,**(payload.get('domainProperties') or {})}
    if len(values)>500:raise ValueError('OSLC resource exceeds 500 reporting properties')
    if len(json.dumps(payload).encode())>1024*1024:raise ValueError('OSLC reporting resource exceeds 1 MiB')
    facts=[]
    for prop,value in values.items():
        if not isinstance(prop,str) or len(prop)>1000:raise ValueError('Invalid reporting property identity')
        items=value if isinstance(value,list) else [value]
        if len(items)>1000:raise ValueError('Reporting property has too many values')
        for index,item in enumerate(items):
            numeric=None
            if isinstance(item,(int,float)) and not isinstance(item,bool):
                try:
                    number=Decimal(str(item))
                    if number.is_finite() and len(number.as_tuple().digits)<=100 and abs(number.adjusted())<=100:numeric=number
                except InvalidOperation:pass
            facts.append((digest(prop),prop,index,item,numeric))
    links=[]
    for item in payload.get('outgoingLinks',[]):
        predicate,target=item.get('predicate'),item.get('targetUri')
        if predicate and target:links.append((digest(predicate),predicate,resource_key(target),target))
    if len(links)>10000:raise ValueError('Reporting resource has too many outgoing links')
    return {'key':resource_key(uri),'uri':uri,'iri':str(props.get('uri') or props.get('rdf_uri') or uri),
            'ontology_id':ontology,'name':str(payload.get('title') or props.get('name') or uri),
            'description':str(props.get('description') or props.get('comment') or ''),
            'types':types,'payload':payload,'digest':digest(payload),'values':facts,'links':links}


def commit(identifier,expected,state,changes,*,promote=False):
    """A retry cannot advance its cursor without the exact corresponding rows."""
    with registry()._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SELECT state,status FROM depo_reporting_feeds WHERE feed_id=%s FOR UPDATE',(identifier,));row=c.fetchone()
        if not row or row[1]!='approved':raise ValueError('Reporting selection is not approved')
        if row[0]!=expected:raise RuntimeError('Reporting checkpoint changed; refresh and retry')
        generation=state.get('building_generation') or state.get('active_generation')
        for uri,resource in changes:
            ensure_execution_allowed();key=resource_key(uri)
            c.execute('DELETE FROM depo_reporting_resources WHERE feed_id=%s AND generation=%s AND resource_key=%s',(identifier,generation,key))
            c.execute('UPDATE depo_reporting_links SET target_deleted=%s WHERE feed_id=%s AND generation=%s AND target_key=%s',(resource is None,identifier,generation,key))
            if resource is None:continue
            c.execute('INSERT INTO depo_reporting_resources(feed_id,generation,resource_key,resource_uri,source_iri,ontology_id,name,description,types,payload,digest) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (identifier,generation,key,uri,resource['iri'],resource['ontology_id'],resource['name'],resource['description'],resource['types'],Jsonb(resource['payload']),resource['digest']))
            if resource['values']:c.executemany('INSERT INTO depo_reporting_values VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',[(identifier,generation,key,*v[:3],Jsonb(v[3]),v[4]) for v in resource['values']])
            if resource['links']:c.executemany('INSERT INTO depo_reporting_links(feed_id,generation,resource_key,predicate_key,predicate_iri,target_key,target_uri) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',[(identifier,generation,key,*link) for link in resource['links']])
        if promote:
            state={**state,'previous_generation':expected.get('active_generation'),'active_generation':state['building_generation'],'building_generation':None}
            keep=[g for g in (state['active_generation'],state.get('previous_generation')) if g]
            c.execute('DELETE FROM depo_reporting_resources WHERE feed_id=%s AND NOT(generation=ANY(%s))',(identifier,keep))
        ensure_execution_allowed()
        c.execute('UPDATE depo_reporting_feeds SET state=%s,updated_at=now() WHERE feed_id=%s',(Jsonb(state),identifier))
    return state


def report(identifier,limit=50):
    with registry()._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        feed=with_freshness(get(identifier,c));generation=feed['state'].get('active_generation')
        args=(identifier,generation)
        c.execute('SELECT count(*) FROM depo_reporting_resources WHERE feed_id=%s AND generation=%s',args);total=c.fetchone()[0]
        c.execute('SELECT kind,count(*) FROM depo_reporting_resources r CROSS JOIN LATERAL unnest(r.types) kind WHERE feed_id=%s AND generation=%s GROUP BY kind ORDER BY count(*) DESC,kind LIMIT 50',args);types=[{'type':k,'records':n} for k,n in c.fetchall()]
        c.execute('SELECT name,description,source_iri,resource_uri,ontology_id,types FROM depo_reporting_resources WHERE feed_id=%s AND generation=%s ORDER BY name,resource_key LIMIT %s',(*args,limit));rows=[dict(zip(('name','description','source_iri','resource_uri','ontology_id','types'),row)) for row in c.fetchall()]
        c.execute('SELECT count(*) FROM depo_reporting_links WHERE feed_id=%s AND generation=%s AND NOT target_deleted',args);links=c.fetchone()[0]
    return {'feed':feed,'resources':rows,'total_resources':total,'types':types,'recorded_links':links,
            'metrics_scope':'Observed resource/type/link counts, not approved engineering KPI formulas or unit-normalized measures.',
            'database':'PostgreSQL reporting replica','read_from_source_graph':False}


def record_failure(identifier,error_type,started):
    # Do not overwrite evidence of a later successful refresh.
    with registry()._connect() as db,db.transaction(),db.cursor() as c:
        c.execute("UPDATE depo_reporting_feeds SET state=state || %s,updated_at=now() WHERE feed_id=%s AND COALESCE(state->>'last_assessed_at','') < %s",
            (Jsonb({'last_error':{'type':error_type,'at':now()}}),identifier,started))
