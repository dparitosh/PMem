"""Versioned, dataset-pinned analytics definitions. Approval never changes a version."""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from psycopg.types.json import Jsonb
from backend.mesh_store import PostgresRegistry
from .business_analytics import FIELDS, ROLES


def validate_definition(value):
    if not isinstance(value,dict) or set(value)-{'business_model','scope','kpis','expected_bom'}:
        raise ValueError('Choose a business model, scope, measures and expected BOM')
    scope=value.get('scope')
    if not isinstance(scope,str) or not 10<=len(scope)<=2000:
        raise ValueError('Describe the reviewed product/revision/effectivity scope (10–2000 characters)')
    model=value.get('business_model')
    if not isinstance(model,dict) or set(model)-FIELDS or not model.get('product_class') or not model.get('part_class'):
        raise ValueError('Select product and part types and their vocabulary relationships')
    for key,val in model.items():
        vals=val if key=='classification_properties' else [val]
        if not isinstance(vals,list) or len(vals)>6 or any(not isinstance(x,str) or not x or len(x.encode())>800 for x in vals):
            raise ValueError('Invalid vocabulary selection')
    kpis=value.get('kpis',[])
    if not isinstance(kpis,list) or len(kpis)>12:raise ValueError('Select up to twelve numeric measures')
    names={'Product records','Part records','Requirement records','Process records','Recorded product-to-part links','Recorded part-to-requirement links','Requirements with a recorded part link (%)','Recorded parent-part to child-part links','Recorded part-to-process links','Parts with a recorded process link (%)','BOM completeness (%)'}
    for kpi in kpis:
        if not isinstance(kpi,dict) or set(kpi)-{'name','role','property','aggregation','unit','unit_property','conversions'}:raise ValueError('Invalid KPI definition')
        name=kpi.get('name','')
        if not isinstance(name,str) or not 1<=len(name)<=100 or name in names:raise ValueError('Measures need distinct business names')
        names.add(name)
        if kpi.get('role') not in ROLES or not model.get(kpi['role']+'_class'):raise ValueError('Select a defined record role for the measure')
        if kpi.get('aggregation') not in {'sum','average','minimum','maximum'}:raise ValueError('Select a supported measure formula')
        for key in ('property','unit','unit_property'):
            if not isinstance(kpi.get(key),str) or not 1<=len(kpi[key].encode())<=800:raise ValueError('Select the numeric property, unit property and reporting unit')
        conversions=kpi.get('conversions')
        if not isinstance(conversions,list) or not 1<=len(conversions)<=20:raise ValueError('Define reviewed unit conversion rules, including identity conversion')
        units=set()
        for rule in conversions:
            if not isinstance(rule,dict) or set(rule)!={'from_unit','scale','offset'}:raise ValueError('Invalid unit rule')
            unit=rule['from_unit']
            if not isinstance(unit,str) or not unit or len(unit)>800 or unit in units:raise ValueError('Each source unit needs one conversion')
            units.add(unit)
            for field in ('scale','offset'):
                try:number=Decimal(str(rule[field]))
                except (InvalidOperation,ValueError):raise ValueError('Conversion coefficients must be finite numbers') from None
                if not number.is_finite() or abs(number)>Decimal('1e20') or len(number.as_tuple().digits)>30:raise ValueError('Conversion coefficient is outside supported precision')
                if field=='scale' and number<=0:raise ValueError('Unit scale must be positive')
    pairs=value.get('expected_bom',[])
    if not isinstance(pairs,list) or len(pairs)>5000:raise ValueError('Expected BOM supports at most 5000 reviewed pairs')
    seen=set()
    for pair in pairs:
        if not isinstance(pair,dict) or set(pair)!={'parent','child'} or any(not isinstance(x,str) or not x or len(x.encode())>800 for x in pair.values()):raise ValueError('Each expected BOM row needs a parent and child identity')
        item=(pair['parent'],pair['child'])
        if item in seen or item[0]==item[1]:raise ValueError('Expected BOM pairs must be unique and non-reflexive')
        seen.add(item)
    if pairs and not model.get('bom_property'):raise ValueError('Choose the BOM relationship before defining completeness')
    return value


def create_model(dataset_id,name,version,definition,actor):
    validate_definition(definition)
    if not re.fullmatch('[0-9a-f]{64}',dataset_id or ''):raise ValueError('Select a prepared dataset')
    if not isinstance(name,str) or not 1<=len(name.strip())<=200 or not re.fullmatch(r'\d+\.\d+\.\d+',version or ''):raise ValueError('Enter a model name and semantic version such as 1.0.0')
    canonical={'dataset_id':dataset_id,'name':name.strip(),'version':version,'definition':definition}
    identity=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with PostgresRegistry('analytics_models')._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SELECT 1 FROM depo_semantic_datasets WHERE dataset_id=%s',(dataset_id,))
        if not c.fetchone():raise ValueError('Prepared dataset not found')
        c.execute('INSERT INTO depo_analytics_models(model_id,dataset_id,name,version,definition,status,created_by) VALUES(%s,%s,%s,%s,%s,\'draft\',%s) ON CONFLICT(model_id) DO NOTHING',(identity,dataset_id,name.strip(),version,Jsonb(definition),actor))
    return identity


def approve_model(model_id,actor):
    if not re.fullmatch('[0-9a-f]{64}',model_id or ''):raise ValueError('Invalid analytics model identity')
    with PostgresRegistry('analytics_models')._connect() as db,db.transaction(),db.cursor() as c:
        c.execute("UPDATE depo_analytics_models SET status='approved',approved_by=%s,approved_at=now() WHERE model_id=%s AND status='draft' RETURNING model_id",(actor,model_id))
        if not c.fetchone():
            c.execute('SELECT status FROM depo_analytics_models WHERE model_id=%s',(model_id,))
            row=c.fetchone()
            if not row or row[0]!='approved':raise ValueError('Model version not found')


def model_rows(dataset_id):
    with PostgresRegistry('analytics_models')._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SET TRANSACTION READ ONLY');c.execute("SET LOCAL statement_timeout='5s'")
        c.execute('SELECT model_id,name,version,status,definition,approved_by FROM depo_analytics_models WHERE dataset_id=%s ORDER BY created_at DESC,model_id LIMIT 101',(dataset_id,))
        rows=c.fetchall()
    return {'models':[dict(zip(('model_id','name','version','status','definition','approved_by'),row)) for row in rows[:100]],'limited':len(rows)>100}
