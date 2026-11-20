"""Link retained events to the existing approved-job worker and native CR/CO."""
import hashlib
import json
import uuid
from fastapi import HTTPException
from backend.artifact_store import ArtifactStore
from . import speed_path,run_records,job_definitions


def linked_run(review):
 binding=review.get('processing_job')
 if not isinstance(binding,dict):return None
 record=run_records.get(binding.get('run_id',''))
 if not record or record.get('job_id')!=binding.get('job_id') or record.get('job_version')!=binding.get('version') or record.get('input_manifest',{}).get('event_review_id')!=review['reconciliation_id']:
  raise HTTPException(409,'Event processing linkage could not be verified')
 if record['input_manifest'].get('event_intent_digest')!=binding.get('event_intent_digest'):
  raise HTTPException(409,'Event processing baseline changed')
 return record


def lineage(review):
 record=linked_run(review)
 if not record:return {'linked':False}
 definition=job_definitions.get(record['job_id'],record['job_version']) or {}
 change=record.get('change_request') or {};order=change.get('order') or {}
 from .publication_change import valid_order
 authorized=valid_order(record)
 verified=bool(authorized and change.get('state')=='executed' and (record.get('output_manifest') or {}).get('publication',{}).get('status')=='published')
 return {'linked':True,'run_id':record['run_id'],'run_number':record.get('run_number'),
  'workflow_name':definition.get('name') or record['job_id'],'workflow_number':definition.get('workflow_number'),
  'job_id':record['job_id'],'version':record['job_version'],'status':record['status'],
  'request_number':change.get('request_number'),'order_number':order.get('order_number') if authorized else None,
  'publication_verified':verified,'change_state':change.get('state'),'request_id':change.get('request_id')}


def submit(identity,job_id,version,expected_digest,actor,correlation_id,configuration=None):
 with speed_path.reconciliations.advisory_lock('event-job:'+identity) as acquired:
  if not acquired:raise HTTPException(409,'Event processing is being prepared; refresh before retrying')
  review=speed_path.reconciliations.get(identity)
  if not review:raise HTTPException(404,'Event review was not found')
  binding=review.get('processing_job')
  if binding:
   if binding['job_id']!=job_id or binding['version']!=version or binding.get('requested_by')!=actor or binding.get('configuration')!=configuration or expected_digest not in {binding['review_digest'],speed_path._digest(review)}:
    raise HTTPException(409,'This event selection is already bound to another processing intent')
   return linked_run(review)
  if speed_path._digest(review)!=expected_digest:raise HTTPException(409,'Event evidence changed; refresh before processing')
  if review.get('status') not in {'ready_for_approved_publication','quarantined'}:raise HTTPException(409,'Prepare the retained event review before processing')
  definition=job_definitions.get(job_id,version)
  if not definition or definition.get('lifecycle_state')!='approved' or not definition.get('enabled') or definition.get('job_type')!='validate-semantic-batch':
   raise HTTPException(409,'Select an approved, enabled semantic validation workflow')
  entities=[];relationships=[];artifacts=[];sources=[];digests=[];total_bytes=0
  for key in review['event_ids']:
   event=speed_path.events.get(key)
   if not event or event.get('reconciliation_id')!=identity or event.get('status') not in {'reconciled','quarantined'}:raise HTTPException(409,'Event ownership changed')
   source=speed_path.sources.get(event['source_id'])
   if not source or not source.get('enabled') or source.get('lifecycle_state')!='approved' or event['standard'] not in source.get('allowed_standards',[]):raise HTTPException(409,'An event source is no longer approved')
   try:
    _,path=ArtifactStore().resolve(event['artifact_id'])
    total_bytes+=path.stat().st_size
    if total_bytes>25*1024*1024:raise HTTPException(413,'Select an event batch with at most 25 MiB of retained inputs')
    content=path.read_bytes()
   except (ValueError,OSError) as exc:raise HTTPException(409,'Retained event content failed integrity verification') from exc
   if 'sha256:'+hashlib.sha256(content).hexdigest()!=event['artifact_id']:raise HTTPException(409,'Retained event content failed integrity verification')
   payload=json.loads(content)
   if speed_path._digest({k:v for k,v in payload.items() if k not in {'approved_by','approval_token'}})!=event['payload_digest']:raise HTTPException(409,'Retained event intent changed')
   entities.extend(payload['records'].get('entities') or []);relationships.extend(payload['records'].get('relationships') or [])
   from backend.ceim.limits import MAX_BATCH_RECORDS
   if len(entities)+len(relationships)>MAX_BATCH_RECORDS:raise HTTPException(413,'Event batch exceeds the semantic processing record limit')
   artifacts.append(event['artifact_id']);sources.append(source.get('name') or event['source_id']);digests.append(event['payload_digest'])
  intent=speed_path._digest({'review_id':identity,'events':review['event_ids'],'digests':digests,'job_id':job_id,'version':version,'actor':actor,'configuration':configuration})
  run_id=str(uuid.uuid5(uuid.NAMESPACE_URL,intent))
  titles=[str(row.get('attributes',{}).get('name')) for row in entities if isinstance(row.get('attributes',{}).get('name'),str) and row['attributes']['name'].strip()]
  name=titles[0][:160] if titles else ', '.join(sorted(set(sources)))[:160]
  if len(entities)>1:name+=' + '+str(len(entities)-1)+' records'
  payload={'source_name':name,'standard':review['standard'],'entities':entities,'relationships':relationships,'artifact_ids':artifacts,
   'source_system':', '.join(sorted(set(sources)))[:500],'execution_actor':actor,'event_review_id':identity,'event_intent_digest':intent}
  from .semantic_configuration import bind_context
  payload=bind_context(payload,configuration,definition['job_type'])
  record=run_records.get(run_id)
  if record:
   if record.get('input_manifest',{}).get('event_intent_digest')!=intent:raise HTTPException(409,'Existing event execution intent could not be verified')
  else:record=run_records.enqueue(definition,payload,correlation_id=correlation_id,run_id=run_id)
  speed_path.reconciliations.put(identity,{**review,'name':name,'processing_job':{'run_id':run_id,'job_id':job_id,'version':version,'requested_by':actor,'configuration':configuration,'review_digest':expected_digest,'event_intent_digest':intent}})
  return record
