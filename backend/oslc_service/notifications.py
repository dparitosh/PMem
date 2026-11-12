"""Receipt-bound TRS notifications retried by the existing outbox worker."""
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


def reconcile(limit=50):
    from backend.Services.oslc_trs_service import OSLCTRSService
    if not OSLCTRSService.is_enabled():return
    store=PostgresRegistry(NAMESPACE)
    total,events=store.page(limit=limit,field='status',value='pending')
    for event in events:
        key=event['delivery_id']
        try:
            receipt=OSLCTRSService.publish_event(event['resource_uri'],event['event_type'],
                title=event['title'],metadata=event['metadata'],delivery_id=key)
            store.put(key,{**event,'status':'completed','receipt':receipt})
        except Exception:
            logging.getLogger(__name__).exception('TRS notification deferred delivery_id=%s',key)
