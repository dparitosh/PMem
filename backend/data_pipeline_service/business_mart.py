"""Approved snapshot model -> atomic ODS, dimensions, link/measure facts and KPIs.

Uses fixed SQL identifiers and deployment-owned formulas; never accepts SQL.
"""
import hashlib
import json
from decimal import Decimal, localcontext
from psycopg.types.json import Jsonb
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.execution_guard import ensure_execution_allowed
from .analytics_models import validate_definition
from .business_analytics import analyse_business, ROLES

TABLES=('depo_analytics_dim_entity','depo_analytics_ods_value','depo_analytics_fact_link','depo_analytics_fact_measure','depo_analytics_fact_kpi')
RELATIONS=(('product_part_property','product','part'),('requirement_property','part','requirement'),('bom_property','part','part'),('process_property','part','process'))


def materialize_mart(payload):
    with localcontext() as context:
        context.prec=1200
        return _materialize_mart(payload)


def _materialize_mart(payload):
    model_id=payload.get('analytics_model_id','')
    import re
    if not re.fullmatch('[0-9a-f]{64}',model_id):raise ValueError('Select an approved analytics model')
    with PostgresRegistry('analytics_models')._connect() as db,db.transaction(),db.cursor() as c:
        c.execute("SELECT dataset_id,definition,name,version,status,approved_by FROM depo_analytics_models WHERE model_id=%s",(model_id,))
        row=c.fetchone()
    if not row or row[4]!='approved':raise ValueError('The selected analytics model is not approved')
    dataset,definition,name,version,_,approver=row
    if dataset!=payload.get('dataset_id'):raise ValueError('Analytics model belongs to another dataset')
    canonical={'dataset_id':dataset,'name':name,'version':version,'definition':definition}
    if hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=model_id:raise ValueError('Approved analytics model integrity check failed')
    validate_definition(definition)
    model=definition['business_model']
    result=analyse_business({**payload,'business_model':model})
    mart=hashlib.sha256(('business-mart-v1:'+model_id).encode()).hexdigest()
    with PostgresRegistry('analytics_marts')._connect() as db,db.transaction(),db.cursor() as c:
        c.execute("SET LOCAL statement_timeout='30s'");c.execute("SET LOCAL lock_timeout='5s'")
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('analytics-mart:'+mart,))
        c.execute('SELECT receipt FROM depo_analytics_marts WHERE mart_id=%s',(mart,));existing=c.fetchone()
        if existing:receipt=existing[0]
        else:
            c.execute('INSERT INTO depo_analytics_marts(mart_id,model_id,dataset_id,receipt) VALUES(%s,%s,%s,%s)',(mart,model_id,dataset,Jsonb({})))
            for role in ROLES:
                if not model.get(role+'_class'):continue
                c.execute("INSERT INTO depo_analytics_dim_entity SELECT %s,%s,iri,label,description,namespace_uri FROM depo_semantic_terms WHERE dataset_id=%s AND term_kind='individual' AND types @> ARRAY[%s]::text[]",(mart,role,dataset,model[role+'_class']))
            c.execute('''INSERT INTO depo_analytics_ods_value SELECT %s,v.fact_id,v.subject_iri,v.property_iri,v.value_kind,v.lexical_value,v.datatype_iri,v.language,v.numeric_value FROM depo_semantic_values v
                WHERE v.dataset_id=%s AND EXISTS(SELECT 1 FROM depo_analytics_dim_entity d WHERE d.mart_id=%s AND d.entity_iri=v.subject_iri)''',(mart,dataset,mart))
            for field,source,target in RELATIONS:
                if not model.get(field) or not model.get(target+'_class'):continue
                c.execute('''INSERT INTO depo_analytics_fact_link SELECT DISTINCT %s,%s,a.entity_iri,%s,%s,b.entity_iri
                    FROM depo_analytics_dim_entity a JOIN depo_semantic_values v ON v.dataset_id=%s AND v.subject_iri=a.entity_iri
                    JOIN depo_analytics_dim_entity b ON b.mart_id=a.mart_id AND b.role=%s AND b.entity_iri=v.lexical_value
                    WHERE a.mart_id=%s AND a.role=%s AND v.property_iri=%s AND v.value_kind='iri' ''',(mart,source,model[field],target,dataset,target,mart,source,model[field]))
            # Unknown/repeated values or units reject the transaction; never silently omit a record.
            for kpi in definition.get('kpis',[]):
                c.execute('''SELECT d.entity_iri,array_agg(DISTINCT v.fact_id) FILTER(WHERE v.fact_id IS NOT NULL),
                    array_agg(DISTINCT v.numeric_value) FILTER(WHERE v.numeric_value IS NOT NULL),
                    array_agg(DISTINCT u.fact_id) FILTER(WHERE u.fact_id IS NOT NULL),
                    array_agg(DISTINCT u.lexical_value) FILTER(WHERE u.lexical_value IS NOT NULL)
                    FROM depo_analytics_dim_entity d
                    LEFT JOIN depo_semantic_values v ON v.dataset_id=%s AND v.subject_iri=d.entity_iri AND v.property_iri=%s
                    LEFT JOIN depo_semantic_values u ON u.dataset_id=%s AND u.subject_iri=d.entity_iri AND u.property_iri=%s
                    WHERE d.mart_id=%s AND d.role=%s GROUP BY d.entity_iri ORDER BY d.entity_iri LIMIT 100001''',(dataset,kpi['property'],dataset,kpi['unit_property'],mart,kpi['role']))
                records=c.fetchall()
                if len(records)>100000:raise ValueError('Measure scope exceeds 100000 records; partition the source')
                rules={r['from_unit']:(Decimal(str(r['scale'])),Decimal(str(r['offset']))) for r in kpi['conversions']}
                amounts=[]
                for iri,facts,numbers,unit_facts,units in records:
                    if not facts or len(facts)!=1 or not numbers or len(numbers)!=1 or not unit_facts or len(unit_facts)!=1 or not units or units[0] not in rules:
                        raise ValueError('Measure '+kpi['name']+' requires exactly one numeric value and one reviewed unit per selected record')
                    scale,offset=rules[units[0]];value=numbers[0]*scale+offset
                    if not value.is_finite() or abs(value)>Decimal('1e100'):raise ValueError('Normalized measure exceeds supported bounds')
                    amounts.append((mart,kpi['role'],iri,kpi['name'],value,kpi['unit']))
                if not amounts:raise ValueError('Selected measure has no records')
                with c.copy('COPY depo_analytics_fact_measure(mart_id,role,entity_iri,measure,value,unit) FROM STDIN') as copy:
                    for item in amounts:copy.write_row(item)
                values=[item[4] for item in amounts]
                operation=kpi['aggregation'];value={'sum':lambda:sum(values),'average':lambda:sum(values)/len(values),'minimum':lambda:min(values),'maximum':lambda:max(values)}[operation]()
                c.execute('INSERT INTO depo_analytics_fact_kpi VALUES(%s,%s,%s,%s,%s,%s,%s)',(mart,kpi['name'],value,kpi['unit'],operation+'(source_value × reviewed scale + reviewed offset)',len(values),'observed'))
                result['rows'].append({'area':kpi['role'],'measure':kpi['name'],'value':str(value),'unit':kpi['unit'],'status':'observed','formula':operation+' of one normalized value per selected entity'})
            expected=definition.get('expected_bom',[])
            if expected:
                c.execute("SELECT entity_iri FROM depo_analytics_dim_entity WHERE mart_id=%s AND role='part'",(mart,));parts={r[0] for r in c.fetchall()}
                if any(p['parent'] not in parts or p['child'] not in parts for p in expected):raise ValueError('Expected BOM contains parts outside the pinned snapshot')
                c.execute("SELECT source_iri,target_iri FROM depo_analytics_fact_link WHERE mart_id=%s AND source_role='part' AND target_role='part' AND relation=%s",(mart,model['bom_property']))
                actual=set(c.fetchall());matched=sum((p['parent'],p['child']) in actual for p in expected)
                percentage=Decimal(matched)*100/len(expected)
                for metric in result['rows']:
                    if metric['measure']=='BOM completeness (%)':metric.update(value=round(float(percentage),2),status='observed',reason='Reviewed expected pairs in the pinned snapshot only',numerator=matched,denominator=len(expected),formula='100 × matched expected parent/child pairs / reviewed expected pairs')
            for metric in result['rows']:
                if metric.get('value') is not None and not any(k['name']==metric['measure'] for k in definition.get('kpis',[])):
                    c.execute('INSERT INTO depo_analytics_fact_kpi VALUES(%s,%s,%s,%s,%s,%s,%s)',(mart,metric['measure'],metric['value'],'%' if '(%)' in metric['measure'] else 'count',metric.get('formula',metric.get('grain',metric.get('direction','record count'))),metric.get('denominator') or result['population_entities'],'observed'))
            counts={}
            for table in TABLES:
                c.execute('SELECT count(*) FROM '+table+' WHERE mart_id=%s',(mart,));counts[table]=c.fetchone()[0]
            receipt={'mart_id':mart,'model_id':model_id,'model_name':name,'model_version':version,'model_approved_by':approver,'dataset_id':dataset,'scope':definition['scope'],'tables':[{'name':key,'rows':value} for key,value in counts.items()],
                     'business_rows':result['rows'],'consumption':'Filter every table/view by mart_id. Entity IRIs are source identities, not cross-source equivalence.','publication':'Prepared; product approval and catalog publication are separate'}
            ensure_execution_allowed()
            c.execute('UPDATE depo_analytics_marts SET receipt=%s WHERE mart_id=%s',(Jsonb(receipt),mart))
        ensure_execution_allowed()
    result.update(algorithm='business-mart',mart=receipt,rows=receipt['business_rows'],scope=definition['scope'],unit_policy='Measures use the approved explicit per-entity unit conversion rules; count/link KPIs retain snapshot scope',classification='approved-model; prepared mart requires separate product publication')
    return result
