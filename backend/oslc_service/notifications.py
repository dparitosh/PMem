"""Receipt-bound TRS notifications retried by the existing outbox worker."""
from urllib.parse import quote
import hashlib
import logging
from backend.mesh_store import PostgresRegistry

NAMESPACE='oslc_trs_outbox'


def retain_publication(store,ontology_id,record):
    key=hashlib.sha256((ontology_id+':'+record['publication_id']).encode()).hexdigest()
    event={'delivery_id':key,'status':'pending','resource_uri':'/oslc/shapes/'+ontology_id,
           'event_type':'Modification','title':'Published ontology updated',
           'metadata':{'ontology_id':ontology_id,'publication_id':record['publication_id']}}
    # Notification intent and the authoritative PostgreSQL receipt commit together.
    return store.put_with_related(ontology_id,record,related_namespace=NAMESPACE,related_key=key,related_value=event)


def retain_merge_change(store, preview_id, record):
    """Commit native CR state and a coalesced freshness notice atomically."""
    from urllib.parse import quote
    change=record['change_request']
    if isinstance(store, PostgresRegistry):
        from backend.depo_platform.resource_identity import ensure
        ensure(change, 'merges', preview_id)
    key='merge-change:'+hashlib.sha256(preview_id.encode()).hexdigest()
    delivery_id=key+':'+str(change['revision'])+':'+change['plan_digest']
    event={'outbox_key':key,'delivery_id':delivery_id,'status':'pending',
        'resource_uri':'/oslc/change-control/records/merges/'+quote(preview_id,safe=''),
        # The retained proposal resource already exists; only lifecycle state changes.
        'event_type':'Modification','title':'Merge review state updated',
        'metadata':{'preview_id':preview_id,'revision':change['revision'],
                    'plan_digest':change['plan_digest'],'state':change['state']}}
    return store.put_with_related(preview_id,record,related_namespace=NAMESPACE,
        related_key=key,related_value=event)


def retain_native_change(store,key,record,source,identifier):
    """Atomically retain any managed native state and its coalesced TRS notice."""
    from urllib.parse import quote
    change=record['change_request']
    if isinstance(store, PostgresRegistry):
        from backend.depo_platform.resource_identity import ensure
        ensure(change, source, identifier)
    notice='native-change:'+source+':'+hashlib.sha256(identifier.encode()).hexdigest()
    event={'outbox_key':notice,'delivery_id':notice+':'+str(change['revision'])+':'+change['plan_digest'],
        'status':'pending','resource_uri':'/oslc/change-control/records/'+source+'/'+quote(identifier,safe=''),
        'event_type':'Modification','title':'Release operation state updated',
        'metadata':{'source_kind':source,'storage_namespace':store.namespace,'storage_key':key,
            'identifier':identifier,'revision':change['revision'],'plan_digest':change['plan_digest'],'state':change['state']}}
    return store.put_with_related(key,record,related_namespace=NAMESPACE,related_key=notice,related_value=event)


def repair_workflow_change_notices(store, limit):
    """Discover committed definition changes after a crash before TRS enqueue.

    Read native records; only the OSLC-owned outbox is written here.
    """
    if not hasattr(store,'_connect'):return
    with store._connect() as db,db.cursor() as cursor:
        cursor.execute("""SELECT r.key,r.value FROM depo_registry r WHERE r.namespace=%s
          AND NOT EXISTS (SELECT 1 FROM depo_registry n WHERE n.namespace=%s
            AND n.value->'metadata'->>'source_kind'='workflow_changes'
            AND n.value->'metadata'->>'storage_key'=r.key
            AND (n.value->'metadata'->>'revision')::integer >= (r.value->'change_request'->>'revision')::integer)
          ORDER BY r.updated_at,r.key LIMIT %s""",('data_job_definition_changes_v1',NAMESPACE,limit))
        rows=cursor.fetchall()
    for identifier,record in rows:
        change=record['change_request'];notice='native-change:workflow_changes:'+hashlib.sha256(identifier.encode()).hexdigest()
        previous=store.get(notice)
        if previous and (previous.get('metadata') or {}).get('revision',0)>=change['revision']:continue
        event={'outbox_key':notice,'delivery_id':notice+':'+str(change['revision'])+':'+change['plan_digest'],
          'status':'pending','resource_uri':'/oslc/change-control/records/workflow_changes/'+quote(identifier,safe=''),
          'event_type':'Creation' if change['revision']==1 else 'Modification','title':'Workflow maintenance change updated',
          'metadata':{'source_kind':'workflow_changes','storage_namespace':'data_job_definition_changes_v1',
                      'storage_key':identifier,'identifier':identifier,'revision':change['revision'],
                      'plan_digest':change['plan_digest'],'state':change['state']}}
        if previous:store.compare_and_put(notice,previous,event)
        else:
            try:store.create(notice,event)
            except FileExistsError:pass


def native_exists(metadata):
    from .change_control import SOURCES
    source=metadata.get('source_kind')
    if source not in SOURCES:return False
    namespace=SOURCES[source][0]
    if namespace!=metadata.get('storage_namespace'):raise ValueError('Native notification ownership mismatch')
    return PostgresRegistry(namespace).get(metadata['storage_key']) is not None


def merge_exists(identifier):
    """An unavailable store must raise, never look like a deleted resource."""
    return PostgresRegistry('ontology_merge_previews').get(identifier) is not None


def missing_merge_events(store, limit):
    """Bounded indexed anti-join; do not scan every completed delivery in Python."""
    if not hasattr(store,'_connect'):return []  # Explicit in-memory test doubles.
    with store._connect() as db, db.cursor() as cursor:
        cursor.execute("""SELECT o.value FROM depo_registry o
            WHERE o.namespace=%s AND left(o.key,13)='merge-change:'
              AND o.value->>'status'='completed' AND o.value->>'event_type'='Modification'
              AND NOT EXISTS (SELECT 1 FROM depo_registry n
                WHERE n.namespace=%s AND n.key=o.value->'metadata'->>'preview_id')
            ORDER BY o.key LIMIT %s""",(NAMESPACE,'ontology_merge_previews',limit))
        return [row[0] for row in cursor.fetchall()]


def missing_native_events(store,limit):
    if not hasattr(store,'_connect'):return []
    with store._connect() as db,db.cursor() as cursor:
        cursor.execute("""SELECT o.value FROM depo_registry o WHERE o.namespace=%s AND left(o.key,14)='native-change:'
            AND o.value->>'status'='completed' AND o.value->>'event_type'='Modification'
            AND NOT EXISTS (SELECT 1 FROM depo_registry n WHERE n.namespace=o.value->'metadata'->>'storage_namespace'
                AND n.key=o.value->'metadata'->>'storage_key') ORDER BY o.key LIMIT %s""",(NAMESPACE,limit))
        return [row[0] for row in cursor.fetchall()]


def release_notices(limit):
    from backend.Services.oslc_trs_service import OSLCTRSService
    store=PostgresRegistry('release_changes')
    _,events=store.page(limit=limit,field='status',value='pending')
    if hasattr(store,'_connect'):
        with store._connect() as db,db.cursor() as cursor:
            cursor.execute("""SELECT o.value FROM depo_registry o WHERE o.namespace=%s AND o.value->>'kind'='release-notice'
                AND o.value->>'status'='completed' AND o.value->>'event_type' IN ('Creation','Modification')
                AND NOT EXISTS (SELECT 1 FROM depo_registry n WHERE n.namespace=%s AND n.key=o.value->'metadata'->>'storage_key')
                ORDER BY o.key LIMIT %s""",('release_changes','release_changes',limit))
            events += [row[0] for row in cursor.fetchall()]
    for event in events:
        if event.get('kind')!='release-notice':continue
        key=event['outbox_key']
        try:
            with store.advisory_lock(key) as acquired:
                if not acquired:continue
                current=store.get(key)
                if not current:continue
                exists=store.get(current.get('metadata',{}).get('storage_key','')) is not None
                if not exists and current.get('event_type')!='Deletion':
                    deletion={**current,'status':'pending','event_type':'Deletion','delivery_id':current['delivery_id']+':deleted'}
                    if not store.compare_and_put(key,current,deletion):continue
                    current=deletion
                if current.get('status')!='pending' or exists and current.get('event_type')=='Deletion':continue
                receipt=OSLCTRSService.publish_event(current['resource_uri'],current['event_type'],title=current['title'],metadata=current['metadata'],delivery_id=current['delivery_id'])
                if receipt.get('status')!='disabled':store.compare_and_put(key,current,{**current,'status':'completed','receipt':receipt})
        except Exception:logging.getLogger(__name__).exception('Release TRS notification deferred')


def reconcile(limit=50):
    from backend.Services.oslc_trs_service import OSLCTRSService
    if not OSLCTRSService.is_enabled():return
    store=PostgresRegistry(NAMESPACE)
    limit=max(1,min(int(limit),200))
    repair_workflow_change_notices(store,limit)
    total,events=store.page(limit=limit,field='status',value='pending')
    events += missing_merge_events(store,limit)+missing_native_events(store,limit)
    for event in events:
        key=event.get('outbox_key') or event['delivery_id']
        try:
            if event.get('outbox_key'):
                # Serialize delivery per resource. A concurrent native state update
                # may replace this notice; never overwrite its newer pending revision.
                with store.advisory_lock(key) as acquired:
                    if acquired is False:continue
                    current=store.get(key)
                    if not current:continue
                    metadata=current.get('metadata') or {}
                    identifier=metadata.get('preview_id') or metadata.get('identifier')
                    if not isinstance(identifier,str) or not identifier:continue
                    exists=native_exists(metadata) if metadata.get('source_kind') else merge_exists(identifier)
                    if not exists and current.get('event_type')!='Deletion':
                        deletion={**current,'status':'pending','event_type':'Deletion',
                            'delivery_id':current['delivery_id']+':deleted',
                            'title':'Retained merge proposal removed',
                            'metadata':{**metadata,'deleted':True} if metadata.get('source_kind') else {'preview_id':identifier,'deleted':True}}
                        if not store.compare_and_put(key,current,deletion):continue
                        current=deletion
                    if current.get('status')!='pending':continue
                    # A restored resource must not receive a stale deletion. Its
                    # next native transition or a Base re-read supplies current state.
                    if exists and current.get('event_type')=='Deletion':continue
                    receipt=OSLCTRSService.publish_event(current['resource_uri'],current['event_type'],
                        title=current['title'],metadata=current['metadata'],delivery_id=current['delivery_id'])
                    if receipt.get('status')=='disabled':continue
                    store.compare_and_put(key,current,{**current,'status':'completed','receipt':receipt})
            else:
                receipt=OSLCTRSService.publish_event(event['resource_uri'],event['event_type'],
                    title=event['title'],metadata=event['metadata'],delivery_id=event['delivery_id'])
                if receipt.get('status')!='disabled':store.put(key,{**event,'status':'completed','receipt':receipt})
        except Exception:
            logging.getLogger(__name__).exception('TRS notification deferred delivery_id=%s',event['delivery_id'])

    release_notices(limit)
