"""Deployment-owned SQL analysis strategies. No arbitrary SQL or Python inputs."""
import json
import math
import re
from backend.mesh_store import PostgresRegistry
from backend.artifact_store import ArtifactStore

ALGORITHMS = {'profile','frequency','numeric-summary','correlation','dimension-preview'}


def analyse(payload, *, preview=False):
    dataset=payload.get('dataset_id','')
    if not isinstance(dataset,str) or not re.fullmatch('[0-9a-f]{64}',dataset):raise ValueError('Select a retained semantic dataset')
    class_iri=payload.get('class_iri','')
    properties=payload.get('property_iris',[])
    algorithm=payload.get('algorithm','profile')
    if not isinstance(class_iri,str) or not class_iri or len(class_iri)>2000:raise ValueError('Select a business entity type')
    if not isinstance(properties,list) or len(properties)>20 or any(not isinstance(value,str) or not value or len(value)>2000 for value in properties) or len(set(properties))!=len(properties):raise ValueError('Select up to 20 distinct properties')
    if algorithm not in ALGORITHMS:raise ValueError('Select a supported analysis')
    if algorithm in {'frequency','numeric-summary'} and len(properties)!=1:raise ValueError('Select exactly one property')
    if algorithm=='correlation' and len(properties)!=2:raise ValueError('Select two numeric properties')
    if algorithm=='dimension-preview' and not properties:raise ValueError('Select the dimension attributes')
    registry=PostgresRegistry('semantic_analysis')
    with registry._connect() as db,db.transaction(),db.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        cursor.execute("SET LOCAL statement_timeout='10s'")
        cursor.execute('SELECT metadata FROM depo_semantic_datasets WHERE dataset_id=%s',(dataset,))
        retained=cursor.fetchone()
        if not retained:raise ValueError('Semantic dataset not found')
        if payload.get('configuration_id') and retained[0].get('configuration_id')!=payload['configuration_id']:raise ValueError('Dataset does not belong to the selected configuration')
        scope="t.dataset_id=%s AND t.term_kind='individual' AND t.types @> ARRAY[%s]::text[]"
        cursor.execute('SELECT count(*) FROM depo_semantic_terms t WHERE '+scope,(dataset,class_iri))
        total=cursor.fetchone()[0]
        if not total:raise ValueError('No typed business instances exist for this class in this snapshot')
        join=' FROM depo_semantic_terms t JOIN depo_semantic_values v ON v.dataset_id=t.dataset_id AND v.subject_iri=t.iri WHERE '+scope
        if properties:
            cursor.execute('SELECT DISTINCT v.property_iri'+join+' AND v.property_iri=ANY(%s)',(dataset,class_iri,properties))
            if {row[0] for row in cursor.fetchall()}!=set(properties):raise ValueError('Selected properties do not occur on these business instances')
        limited=False
        if algorithm=='profile':
            cursor.execute('SELECT v.property_iri,count(DISTINCT t.iri),count(*),count(v.numeric_value),count(DISTINCT v.datatype_iri)'+join+' GROUP BY v.property_iri ORDER BY v.property_iri LIMIT 501',(dataset,class_iri))
            fetched=cursor.fetchall();limited=len(fetched)>500
            rows=[dict(zip(['property_iri','entities_with_value','value_count','numeric_values','datatype_count'],row)) for row in fetched[:500]]
            for row in rows:row['entities_without_value']=total-row['entities_with_value']
        elif algorithm=='frequency':
            cursor.execute('SELECT left(v.lexical_value,1000),v.datatype_iri,v.language,count(DISTINCT t.iri)'+join+' AND v.property_iri=%s GROUP BY v.lexical_value,v.datatype_iri,v.language ORDER BY count(DISTINCT t.iri) DESC,v.lexical_value,v.datatype_iri,v.language LIMIT 101',(dataset,class_iri,properties[0]))
            fetched=cursor.fetchall();limited=len(fetched)>100
            rows=[dict(zip(['value','datatype','language','entity_count'],row)) for row in fetched[:100]]
        elif algorithm in {'numeric-summary','correlation'}:
            # Never multiply rows or silently pick one value from repeated data.
            cursor.execute('SELECT 1'+join+' AND v.property_iri=ANY(%s) GROUP BY t.iri,v.property_iri HAVING count(*)>1 OR count(v.numeric_value)<>count(*) LIMIT 1',(dataset,class_iri,properties))
            if cursor.fetchone():raise ValueError('Numeric analysis requires one numeric value per entity and selected property; review repeated/non-numeric values first')
            # Conflicting declared units must not be silently combined.
            unit_predicates=['http://qudt.org/schema/qudt/unit','http://www.ontology-of-units-of-measure.org/resource/om-2/hasUnit']
            cursor.execute('SELECT 1 FROM depo_semantic_values WHERE dataset_id=%s AND subject_iri=ANY(%s) AND property_iri=ANY(%s) GROUP BY subject_iri HAVING count(DISTINCT lexical_value)>1 LIMIT 1',(dataset,properties,unit_predicates))
            if cursor.fetchone():raise ValueError('Declared units differ; an approved unit-normalization model is required')
            cursor.execute('SELECT 1 FROM depo_semantic_terms t JOIN depo_semantic_values u ON u.dataset_id=t.dataset_id AND u.subject_iri=t.iri WHERE '+scope+' AND u.property_iri=ANY(%s) HAVING count(DISTINCT u.lexical_value)>1',(dataset,class_iri,unit_predicates))
            if cursor.fetchone():raise ValueError('Entity-level units differ; an approved unit-normalization model is required')
            if algorithm=='numeric-summary':
                cursor.execute('SELECT count(v.numeric_value),min(v.numeric_value)::text,max(v.numeric_value)::text,avg(v.numeric_value)::text,stddev_samp(v.numeric_value)::text'+join+' AND v.property_iri=%s',(dataset,class_iri,properties[0]))
                rows=[dict(zip(['observations','minimum','maximum','average','sample_standard_deviation'],cursor.fetchone()))]
            else:
                cursor.execute('SELECT 1'+join+' AND v.property_iri=ANY(%s) AND abs(v.numeric_value)>1e150 LIMIT 1',(dataset,class_iri,properties))
                if cursor.fetchone():raise ValueError('Values exceed the safe correlation range; normalize the selected measures first')
                cursor.execute('WITH observations AS (SELECT t.iri,max(v.numeric_value) FILTER(WHERE v.property_iri=%s) AS x,max(v.numeric_value) FILTER(WHERE v.property_iri=%s) AS y'+join+' AND v.property_iri=ANY(%s) GROUP BY t.iri) SELECT count(*) FILTER(WHERE x IS NOT NULL AND y IS NOT NULL),corr(x::double precision,y::double precision) FROM observations',(properties[0],properties[1],dataset,class_iri,properties))
                pair_count,coefficient=cursor.fetchone()
                if coefficient is not None and not math.isfinite(coefficient):coefficient=None
                rows=[{'paired_observations':pair_count,'pearson_correlation':coefficient,'interpretation':'Association only; not evidence of causation'}]
        else:
            cursor.execute('SELECT iri,label FROM depo_semantic_terms t WHERE '+scope+' ORDER BY iri LIMIT 101',(dataset,class_iri))
            entities=cursor.fetchall();limited=len(entities)>100;entities=entities[:100]
            cursor.execute('SELECT subject_iri,property_iri,left(lexical_value,1000),datatype_iri,language FROM depo_semantic_values WHERE dataset_id=%s AND subject_iri=ANY(%s) AND property_iri=ANY(%s) ORDER BY subject_iri,property_iri,fact_id LIMIT 5001',(dataset,[iri for iri,_ in entities],properties))
            values=cursor.fetchall();limited=limited or len(values)>5000
            by_entity={iri:{prop:[] for prop in properties} for iri,_ in entities}
            for iri,prop,value,datatype,language in values[:5000]:by_entity[iri][prop].append({'value':value,'datatype':datatype,'language':language})
            rows=[{'entity_iri':iri,'name':name,'attributes':by_entity[iri]} for iri,name in entities]
        # Bound downstream result artifacts as well as database response sizes.
        while rows and len(json.dumps(rows,default=str).encode())>2*1024*1024:
            rows.pop();limited=True
        return {'dataset_id':dataset,'algorithm':algorithm,'class_iri':class_iri,'property_iris':properties,
                'configuration_id':retained[0].get('configuration_id'),'configuration_context':retained[0].get('configuration_context'),
                'population_entities':total,'rows':rows,'limited':limited,'source':retained[0],
                'scope':'snapshot; dimension output is a bounded preview, not a published data mart',
                'unit_policy':'No conversion performed; missing unit metadata is unknown, not dimensionless',
                'classification':'draft-analysis; publication and business approval are separate'}


def execute_analysis(runner,payload,*,correlation_id):
    result=analyse(payload)
    artifact=ArtifactStore().ingest_bytes(json.dumps(result,default=str,sort_keys=True).encode(),filename='semantic-analysis.json',kind='semantic-analysis',media_type='application/json',provenance={'dataset_id':result['dataset_id'],'correlation_id':correlation_id})
    return {**result,'status':'completed','job_type':'semantic-dataset-analysis','counts':{'entities':result['population_entities'],'result_rows':len(result['rows'])},
            'partition_artifacts':{'accepted':artifact['artifact_id']},
            'data_product_draft':{'contract':'semantic-analysis-product-v1','name':payload.get('name') or result['algorithm'],
              'configuration_id':result.get('configuration_id'),'configuration_context':result.get('configuration_context'),
              'product_kind':'pipeline-evidence','domain':'semantic-engineering','quality_status':'requires_review',
              'analytics_readiness':'bounded-preview' if result['algorithm']=='dimension-preview' or result['limited'] else 'snapshot-analysis',
              'sources':[{'artifact_id':result['source']['artifact_id'],'dataset_id':result['dataset_id'],
                          'configuration_id':result.get('configuration_id'),'configuration_context':result.get('configuration_context')}],
              'artifacts':[{'artifact_id':artifact['artifact_id'],'kind':'analysis'},{'artifact_id':result['source']['artifact_id'],'kind':'rdf-source'}],
              'publication_requirements':['Approved semantic release','Data-product steward approval']}}
