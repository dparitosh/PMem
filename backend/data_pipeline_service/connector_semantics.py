"""Explicit connector-field projection through the existing CEIM contract.

This prepares validated proposals; it cannot approve mappings or publish a graph.
"""
import hashlib
import json
from backend.artifact_store import ArtifactStore
from backend.ceim.contract import contract
from backend.depo_platform.execution_guard import ensure_execution_allowed
from . import run_records
from .connector_sources import MAX_BYTES,MAX_RECORDS


def execute(runner,payload,*,correlation_id):
    run=run_records.get(payload.get('acquisition_run_id',''))
    artifact_id=payload.get('artifact_id')
    if not run or run.get('status')!='completed' or run.get('job_type') not in {'registered-source-ingest','rest-source-ingest'}:
        raise ValueError('Select a completed registered-source acquisition run')
    owned=(run.get('output_manifest') or {}).get('partition_artifacts') or {}
    if not artifact_id or owned.get('source')!=artifact_id:
        raise ValueError('Selected source artifact does not belong to this acquisition run')
    metadata,path=ArtifactStore().resolve(artifact_id)
    if metadata.get('kind') not in {'connector-records','rest-source-records'} or path.stat().st_size>MAX_BYTES:
        raise ValueError('Select a bounded retained source-record artifact')
    content=path.read_bytes()
    if 'sha256:'+hashlib.sha256(content).hexdigest()!=artifact_id:raise ValueError('Retained source integrity check failed')
    records=json.loads(content)
    if not isinstance(records,list) or len(records)>MAX_RECORDS or any(not isinstance(row,dict) for row in records):
        raise ValueError('Source must contain at most 1000 object records')
    standard=str(payload.get('standard') or '').strip().lower();source_type=payload.get('source_type','');id_field=payload.get('id_field','')
    fields=payload.get('attribute_fields')
    pack=contract.mapping_pack(standard);mapping=(pack.get('entities') or {}).get(source_type)
    if not mapping or not isinstance(id_field,str) or not id_field or not isinstance(fields,dict) or len(fields)>64:
        raise ValueError('Choose a supported CEIM source type, identity field and explicit attribute fields')
    allowed=set((mapping.get('properties') or {}))-{'$source_id'}
    if any(target not in allowed or not isinstance(field,str) or not field for target,field in fields.items()):
        raise ValueError('Attribute targets must belong to the selected versioned CEIM mapping pack')
    normalized=[];identities=set()
    for row in records:
        ensure_execution_allowed();identity=row.get(id_field)
        if not isinstance(identity,(str,int)) or isinstance(identity,bool) or not str(identity).strip():
            raise ValueError('Every source row requires an explicit non-empty business identity')
        if str(identity) in identities:raise ValueError('Duplicate source identities require explicit conflict review')
        identities.add(str(identity))
        attributes={target:row[field] for target,field in fields.items() if field in row}
        if any(value is not None and (not isinstance(value,(str,int,float,bool)) or isinstance(value,str) and len(value)>4000) for value in attributes.values()):
            raise ValueError('Nested or oversized source attributes require an explicit preparation step')
        normalized.append(contract.normalize_entity(standard=standard,record={'source_id':str(identity),'source_type':source_type,'attributes':attributes}))
    validation=contract.validate_projection(entities=normalized,relationships=[])
    batch={'contract':'normalized-ceim-batch-v1','representation':'normalized-ceim-v1','standard':standard,
        'ceim_version':contract.version,'mapping_digest':pack['digest'],'entities':normalized,'relationships':[],
        'source_system':run.get('source_system'),'source_acquisition_run_id':run['run_id'],'source_artifact_id':artifact_id}
    output=ArtifactStore().ingest_bytes(json.dumps(batch,sort_keys=True,allow_nan=False).encode(),filename='connector-semantic-proposal.json',
        kind='accepted-semantic-partition' if validation.get('conforms') else 'rejected-semantic-partition',media_type='application/json',
        provenance={'source_run_id':run['run_id'],'source_artifact_id':artifact_id,'correlation_id':correlation_id})
    return {'status':'completed' if validation.get('conforms') else 'quality_warning','standard':standard,'ceim_version':contract.version,
        'mapping_digest':pack['digest'],'source_acquisition_run_id':run['run_id'],'source_artifact_id':artifact_id,
        'counts':{'entities':len(normalized),'relationships':0},'validation':validation,
        'partition_artifacts':{'accepted' if validation.get('conforms') else 'rejected':output['artifact_id']},
        'mapping_status':'proposal; semantic release and publication approval remain separate','publication':'not_attempted'}
