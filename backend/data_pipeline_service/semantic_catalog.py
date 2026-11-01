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
        if record.get('status')!='completed' or record.get('job_type') not in {'semantic-dataset-analysis','semantic-business-mart','graph-source-snapshot'}:
            raise HTTPException(409,'A completed semantic analysis result is required')
        output=record.get('output_manifest') or {}
        metadata,path=ArtifactStore().resolve(output.get('result_artifact_id',''))
        if metadata.get('kind')!='data-job-output' or (metadata.get('provenance') or {}).get('run_id')!=run_id:
            raise ValueError('Result ownership could not be verified')
        if path.stat().st_size>8*1024*1024:raise ValueError('Result exceeds the display limit')
        result=json.loads(path.read_text(encoding='utf-8'))
        if result.get('configuration_id')!=output.get('configuration_id'):
            raise ValueError('Analysis configuration differs from its retained run')
        allowed=('algorithm','dataset_id','configuration_id','configuration_context','population_entities','rows','dimensions','classifications','links','hierarchy','limited','warnings','scope','unit_policy','classification','business_model','mart')
        return {'run_id':run_id,**{key:result[key] for key in allowed if key in result}}
    except (ValueError,KeyError,TypeError):raise HTTPException(409,'Retained analysis evidence is missing or invalid; restore it before retrying') from None
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Retained analysis evidence is unavailable') from None


from fastapi import Request
from backend.depo_platform.request_bodies import AnalyticsModelBody, ApprovalBody
from backend.depo_platform.authorization import approval_identity

@router.get('/models')
def analytics_models(dataset_id: str=Query(pattern='^[0-9a-f]{64}$')):
    from .analytics_models import model_rows
    try:return model_rows(dataset_id)
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Analytics models are unavailable; verify migrations and service health') from None

@router.post('/models',status_code=201)
def save_analytics_model(payload: AnalyticsModelBody, request: Request):
    from .analytics_models import create_model
    actor=approval_identity(request,payload,token_env='ONTOLOGY_APPROVAL_TOKEN')
    try:return {'model_id':create_model(payload['dataset_id'],payload['name'],payload['version'],payload['definition'],actor),'status':'draft'}
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except DatabaseError as exc:
        if getattr(exc,'sqlstate',None)=='23505':raise HTTPException(409,'This model name/version already has different content; create a new version') from None
        raise HTTPException(503,'Model could not be retained; verify status before retrying') from None

@router.post('/models/{model_id}/approve')
def approve_analytics_model(model_id: str,payload: ApprovalBody,request: Request):
    from .analytics_models import approve_model
    actor=approval_identity(request,payload,token_env='DATA_JOB_APPROVAL_TOKEN')
    try:approve_model(model_id,actor);return {'model_id':model_id,'status':'approved','approved_by':actor}
    except ValueError as exc:raise HTTPException(404,str(exc)) from None
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Model approval outcome is unconfirmed; refresh before retrying') from None

@router.get('/marts/{mart_id}')
def analytics_mart(mart_id: str):
    import re
    if not re.fullmatch('[0-9a-f]{64}',mart_id):raise HTTPException(422,'Invalid mart identity')
    try:
        with PostgresRegistry('analytics_marts')._connect() as db,db.transaction(),db.cursor() as c:
            c.execute('SET TRANSACTION READ ONLY');c.execute("SET LOCAL statement_timeout='5s'")
            c.execute('SELECT receipt FROM depo_analytics_marts WHERE mart_id=%s',(mart_id,));row=c.fetchone()
        if not row:raise HTTPException(404,'Analytics mart not found')
        return row[0]
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Analytics mart is unavailable') from None

@router.get('/marts/{mart_id}/rows')
def analytics_mart_rows(mart_id: str,table: str,offset: int=Query(0,ge=0)):
    import re
    from .business_mart import TABLES
    if not re.fullmatch('[0-9a-f]{64}',mart_id) or table not in TABLES:raise HTTPException(422,'Choose a retained analytics table')
    try:
        with PostgresRegistry('analytics_marts')._connect() as db,db.transaction(),db.cursor() as c:
            c.execute('SET TRANSACTION READ ONLY');c.execute("SET LOCAL statement_timeout='5s'")
            order={'depo_analytics_dim_entity':'role,entity_iri','depo_analytics_ods_value':'fact_id','depo_analytics_fact_link':'source_role,source_iri,relation,target_role,target_iri','depo_analytics_fact_measure':'role,entity_iri,measure','depo_analytics_fact_kpi':'measure'}[table]
            c.execute('SELECT * FROM '+table+' WHERE mart_id=%s ORDER BY '+order+' LIMIT 51 OFFSET %s',(mart_id,offset))
            columns=[d.name for d in c.description];rows=c.fetchall()
        return {'mart_id':mart_id,'table':table,'columns':columns,'rows':[dict(zip(columns,row)) for row in rows[:50]],'next_offset':offset+50 if len(rows)>50 else None}
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Analytics table is unavailable') from None

@router.get('/datasets/{dataset_id}/members')
def analytics_members(dataset_id: str,class_iri: str,search: str=Query('',max_length=200),offset: int=Query(0,ge=0)):
    import re
    if not re.fullmatch('[0-9a-f]{64}',dataset_id) or not class_iri or len(class_iri)>2000:raise HTTPException(422,'Choose a dataset and record type')
    try:
        with PostgresRegistry('analytics_members')._connect() as db,db.transaction(),db.cursor() as c:
            c.execute('SET TRANSACTION READ ONLY');c.execute("SET LOCAL statement_timeout='5s'")
            c.execute("SELECT iri,label FROM depo_semantic_terms WHERE dataset_id=%s AND term_kind='individual' AND types @> ARRAY[%s]::text[] AND strpos(lower(label),lower(%s))>0 ORDER BY iri LIMIT 101 OFFSET %s",(dataset_id,class_iri,search,offset));rows=c.fetchall()
        return {'dataset_id':dataset_id,'members':[{'iri':iri,'name':name} for iri,name in rows[:100]],'next_offset':offset+100 if len(rows)>100 else None}
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Business records are unavailable') from None

@router.get('/datasets/{dataset_id}/values')
def analytics_values(dataset_id: str,class_iri: str,property_iri: str):
    from .semantic_analysis import analyse
    try:return analyse({'dataset_id':dataset_id,'class_iri':class_iri,'property_iris':[property_iri],'algorithm':'frequency'})
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except (DatabaseError,RuntimeError,OSError):raise HTTPException(503,'Business values are unavailable') from None
