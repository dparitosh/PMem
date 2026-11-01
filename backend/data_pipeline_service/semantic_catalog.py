"""Catalog/registry entry point for reusable, versioned semantic datasets."""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Error as DatabaseError
from backend.depo_platform.authorization import graph_read_identity
from backend.mesh_store import PostgresRegistry

router=APIRouter(prefix='/pipeline/semantic',tags=['Semantic datasets'],dependencies=[Depends(graph_read_identity)])


def source_page(offset=0):
    total,products=PostgresRegistry('catalog_products').page(limit=50,offset=offset,exclude_latest=True)
    from .metadata_sources import read_metadata
    page=read_metadata(offset=offset)
    assets=page['assets'];more=page.get('has_more',False)
    sources=[]
    for origin,record in [('catalog',record) for record in products]+[('metadata',record) for record in assets]:
        if record.get('lifecycle_status',record.get('lifecycle_state')) in {'retired','deprecated'}:continue
        identity=(str(record.get('product_id',''))+':'+str(record.get('version',''))) if origin=='catalog' else record.get('asset_id','')
        refs=record.get('artifacts',[]) if origin=='catalog' else [record.get('implementation_ref')]
        for ref in refs:
            identifier=ref.get('artifact_id') if isinstance(ref,dict) else ref
            if not isinstance(identifier,str) or not identifier.startswith('sha256:'):continue
            filename=ref.get('filename','') if isinstance(ref,dict) else ''
            if filename and not filename.lower().endswith(('.ttl','.nt','.rdf','.owl','.jsonld')):continue
            sources.append({'source_id':origin+':'+identity,'artifact_id':identifier,'name':record.get('name') or identity,
                            'version':record.get('version'),'namespace_uri':record.get('namespace_uri',''),
                            'prefix':record.get('namespace_prefix',''),'owner':record.get('owner',''),
                            'origin':origin,'filename':filename,'status':record.get('lifecycle_status',record.get('lifecycle_state','not_recorded'))})
    return {'sources':sources,'offset':offset,'next_offset':offset+50 if more or offset+50<total else None,
            'scope':'Retained RDF references from versioned catalog entries and metadata assets. Other files and live graph projections require a registered RDF snapshot.'}


@router.get('/sources')
def sources(offset:int=Query(0,ge=0)):
    try:return source_page(offset)
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Catalog or metadata registry is unavailable; no empty-source conclusion can be drawn') from None


@router.get('/datasets')
def datasets(offset:int=Query(0,ge=0)):
    try:
        with PostgresRegistry('semantic_dataset_projection')._connect() as db,db.transaction(),db.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute("SET LOCAL statement_timeout='5s'")
            cursor.execute('SELECT metadata FROM depo_semantic_datasets ORDER BY created_at DESC,dataset_id LIMIT 51 OFFSET %s',(offset,))
            rows=[row[0] for row in cursor.fetchall()]
        return {'datasets':rows[:50],'next_offset':offset+50 if len(rows)>50 else None,'offset':offset}
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Semantic datasets are unavailable; verify PostgreSQL migrations and service health') from None


@router.get('/datasets/{dataset_id}')
def schema(dataset_id:str):
    import re
    if not re.fullmatch('[0-9a-f]{64}',dataset_id):raise HTTPException(422,'Invalid dataset identity')
    try:
        with PostgresRegistry('semantic_dataset_projection')._connect() as db,db.transaction(),db.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute("SET LOCAL statement_timeout='5s'")
            cursor.execute('SELECT metadata FROM depo_semantic_datasets WHERE dataset_id=%s',(dataset_id,))
            row=cursor.fetchone()
            if not row:raise HTTPException(404,'Semantic dataset not found')
            metadata=row[0]
            cursor.execute('SELECT namespace_uri,prefix FROM depo_semantic_namespaces WHERE dataset_id=%s ORDER BY namespace_uri,prefix LIMIT 501',(dataset_id,))
            aliases=[{'namespace_uri':uri,'prefix':prefix} for uri,prefix in cursor.fetchall()]
            cursor.execute("SELECT c.iri,COALESCE(d.label,c.iri),count(*) FROM depo_semantic_terms t CROSS JOIN LATERAL unnest(t.types) c(iri) LEFT JOIN depo_semantic_terms d ON d.dataset_id=t.dataset_id AND d.iri=c.iri WHERE t.dataset_id=%s AND t.term_kind='individual' AND c.iri <> 'http://www.w3.org/2002/07/owl#NamedIndividual' GROUP BY c.iri,d.label ORDER BY c.iri LIMIT 501",(dataset_id,))
            classes=[{'iri':iri,'name':name,'entities':count} for iri,name,count in cursor.fetchall()]
        return {'dataset':metadata,'namespaces':aliases[:500],'classes':classes[:500],'limited':len(aliases)>500 or len(classes)>500}
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Semantic dataset metadata is unavailable') from None


@router.get('/datasets/{dataset_id}/fields')
def fields(dataset_id:str,class_iri:str=Query(min_length=1,max_length=2000)):
    from .semantic_analysis import analyse
    try:return analyse({'dataset_id':dataset_id,'class_iri':class_iri,'algorithm':'profile'},preview=True)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Semantic field discovery is unavailable') from None


@router.get('/configurations/{configuration_id}')
def configuration(configuration_id: str):
    from .semantic_configuration import get_configuration
    try:
        return get_configuration(configuration_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503, 'Analytics configuration is unavailable') from None


@router.get('/datasets/{dataset_id}/change-assessment')
def change_assessment(dataset_id: str):
    import re
    if not re.fullmatch('[0-9a-f]{64}', dataset_id):
        raise HTTPException(422, 'Invalid dataset identity')
    try:
        record = PostgresRegistry('semantic_refresh_reviews').get(dataset_id)
        return record or {'dataset_id': dataset_id, 'status': 'not_assessed',
                          'publication_changed': False}
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503, 'Retained change assessment is unavailable') from None


@router.get('/runs/{run_id}/result')
def analysis_result(run_id: str):
    from . import run_records
    from backend.artifact_store import ArtifactStore
    import json
    try:
        record=run_records.get(run_id)
        if not record:raise HTTPException(404,'Analysis run not found')
        if record.get('status')!='completed' or record.get('job_type')!='semantic-dataset-analysis':
            raise HTTPException(409,'A completed semantic analysis result is required')
        output=record.get('output_manifest') or {}
        metadata,path=ArtifactStore().resolve(output.get('result_artifact_id',''))
        if metadata.get('kind')!='data-job-output' or (metadata.get('provenance') or {}).get('run_id')!=run_id:
            raise ValueError('Result ownership could not be verified')
        if path.stat().st_size>8*1024*1024:raise ValueError('Result exceeds the display limit')
        result=json.loads(path.read_text(encoding='utf-8'))
        if result.get('configuration_id')!=output.get('configuration_id'):
            raise ValueError('Analysis configuration differs from its retained run')
        allowed=('algorithm','dataset_id','configuration_id','configuration_context','population_entities','rows','dimensions','classifications','links','hierarchy','limited','warnings','scope','unit_policy','classification','business_model')
        return {'run_id':run_id,**{key:result[key] for key in allowed if key in result}}
    except (ValueError,KeyError,TypeError):raise HTTPException(409,'Retained analysis evidence is missing or invalid; restore it before retrying') from None
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Retained analysis evidence is unavailable') from None
