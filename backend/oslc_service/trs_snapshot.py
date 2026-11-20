"""Stream graph membership into bounded durable pages; publish metadata last."""
import os
import uuid
from datetime import datetime, timezone, timedelta
from neo4j import Query, READ_ACCESS
from backend.core.db_config import get_config, get_driver
from .identity import resource_uri
from urllib.parse import quote
from backend.mesh_store import PostgresRegistry

CHUNK_SIZE = 1000


def merge_resources(service):
    """Recover retained proposal membership independently of the pruned changelog."""
    if not isinstance(service._store,PostgresRegistry):return
    with service._store._connect() as db, db.transaction(), db.cursor(name='trs_merge_members') as cursor:
        cursor.itersize=CHUNK_SIZE
        cursor.execute("SELECT key FROM depo_registry WHERE namespace=%s AND value->>'preview_id'=key ORDER BY key",('ontology_merge_previews',))
        for row in cursor:
            yield {'resource_uri':service._external_resource_uri('/oslc/change-control/records/merges/'+quote(row[0],safe='')),
                   'title':'Retained merge proposal'}


def lifecycle_resources(service):
    if not isinstance(service._store,PostgresRegistry):return
    from .change_control import SOURCES
    selected={source:namespace for source,(namespace,*_) in SOURCES.items() if source in {'bridges','publications','pipeline','product_changes','releases'}}
    with service._store._connect() as db,db.transaction(),db.cursor(name='trs_lifecycle_members') as cursor:
        cursor.itersize=CHUNK_SIZE
        cursor.execute("""SELECT namespace,key,value->>'request_id' AS request_id,value->>'run_id' AS run_id,
            value->>'job_id' AS job_id,value->>'ontology_id' AS ontology_id,value->>'kind' AS kind
            FROM depo_registry WHERE namespace=ANY(%s) AND
              (value->'change_request' IS NOT NULL AND value->'change_request'!='null'::jsonb OR value->>'kind'='release-change')
            ORDER BY namespace,key""",(list(selected.values()),))
        reverse={namespace:source for source,namespace in selected.items()}
        for row in cursor:
            source=reverse[row[0]]
            identifier=row[2] if source in {'releases','product_changes'} else row[3] if source=='pipeline' else row[4] if source=='bridges' else row[5]
            if identifier:yield {'resource_uri':service._external_resource_uri('/oslc/change-control/records/'+source+'/'+quote(identifier,safe='')),'title':'Retained release lifecycle record'}
    with service._store._connect() as db,db.transaction(),db.cursor(name='trs_release_baselines') as cursor:
        cursor.itersize=CHUNK_SIZE
        cursor.execute("SELECT key,value->>'configuration_id' FROM depo_registry WHERE namespace=%s AND value->>'kind'='release-baseline' ORDER BY key",('release_changes',))
        for row in cursor:
            if row[1]:yield {'resource_uri':service._external_resource_uri('/oslc/change-control/configurations/'+quote(row[1],safe='')),'title':'Frozen release configuration'}


def build_snapshot(service, limit):
    state = service._load()
    snapshot_id = str(uuid.uuid4())
    ttl=int(os.getenv('OSLC_TRS_SNAPSHOT_TTL_SECONDS','3600'))
    if not 60<=ttl<=86400:raise RuntimeError('TRS snapshot lifetime must be 60–86400 seconds')
    expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
    maximum = int(os.getenv('OSLC_TRS_MAX_SNAPSHOT_RESOURCES', '1000000'))
    if not 1 <= maximum <= 2000000:
        raise RuntimeError('OSLC_TRS_MAX_SNAPSHOT_RESOURCES must be 1â€“2000000')
    latest = {}
    for event in reversed(state.get('events') or []):
        latest.setdefault(event['resource_uri'], event)
    deleted = {service._external_resource_uri(path) for path, event in latest.items() if event['event_type'] == 'Deletion'}
    count, page, page_index, seen = 0, [], 0, set()

    def append(member, *, authoritative=False):
        nonlocal count, page, page_index
        uri = member['resource_uri']
        if (uri in deleted and not authoritative) or uri in seen:return
        seen.add(uri); count += 1
        if count > maximum:raise RuntimeError('TRS snapshot capacity exceeded; inspect OSLC_TRS_MAX_SNAPSHOT_RESOURCES')
        page.append(member)
        if len(page) == CHUNK_SIZE:
            service._store.put(f'base:{snapshot_id}:chunk:{page_index}', {'members':page,'expires_at':expires})
            page_index += 1; page = []

    config = get_config()
    query = """MATCH (n)
        WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR n:StagedOntologyResource OR n:OntologyPublication)
        RETURN elementId(n) AS element_id, coalesce(n.uri,n.rdf_uri) AS uri,
               n.ontology_id AS ontology_id,
               coalesce(n.name,n.title,n.label,n.id,elementId(n)) AS title
        ORDER BY elementId(n)"""
    # Stream one result cursor instead of loading the full graph into a Python list.
    with get_driver().session(database=config.database, default_access_mode=READ_ACCESS, fetch_size=CHUNK_SIZE) as session:
        for row in session.run(Query(query, timeout=float(config.query_timeout))):
            append({'resource_uri':resource_uri(service.base_url(),dict(row),row['element_id']), 'title':row['title']})
    for member in merge_resources(service):append(member,authoritative=True)
    for member in lifecycle_resources(service):append(member,authoritative=True)
    for event in latest.values():
        # Native registry membership above is authoritative, including after deletion.
        if event['resource_uri'].startswith(('/oslc/change-control/records/','/oslc/change-control/configurations/')):continue
        if event['event_type'] != 'Deletion':
            uri=service._external_resource_uri(event['resource_uri'])
            if uri != service.base_resource_uri():append({'resource_uri':uri,'title':event.get('title') or uri})
    if page:service._store.put(f'base:{snapshot_id}:chunk:{page_index}', {'members':page,'expires_at':expires})
    events=state.get('events') or []
    snapshot={'stream_id':state.get('stream_id'),'chunked':True,'chunk_size':CHUNK_SIZE,'total_count':count,'cutoff_order':state.get('counter',0),
              'cutoff_event':events[-1].get('event_id') if events else None,'expires_at':expires}
    # Until this receipt exists, interrupted chunks are invisible and expire normally.
    service._store.put('base:'+snapshot_id,snapshot)
    return read_page(service,snapshot_id,snapshot,0,max(1,min(1000,int(limit))))


def read_page(service, identifier, snapshot, offset, limit):
    members=[]; total=snapshot['total_count'];position=offset
    while position < min(total,offset+limit):
        index,within=divmod(position,snapshot['chunk_size'])
        chunk=service._store.get(f'base:{identifier}:chunk:{index}')
        if not chunk:raise RuntimeError('TRS snapshot page missing; restart from /oslc/trs/base')
        selected=chunk['members'][within:within+min(limit-len(members),total-position)]
        if not selected:raise RuntimeError('TRS snapshot page is incomplete; rebase required')
        members.extend(selected);position+=len(selected)
    uri=f'{service.base_resource_uri()}?snapshot_id={identifier}&offset={offset}&limit={limit}'
    return {'uri':uri,'type':'trs:Base','members':members,'count':len(members),'total_count':total,
            'snapshot_id':identifier,'stream_id':snapshot.get('stream_id'),'cutoff_order':snapshot['cutoff_order'],'cutoff_event':snapshot.get('cutoff_event'),
            'truncated':position<total,'nextPage':f'{service.base_resource_uri()}?snapshot_id={identifier}&offset={position}&limit={limit}' if position<total else None}
