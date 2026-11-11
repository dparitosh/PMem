"""Bounded business evidence at explicit product/part/requirement/process grains.

Only source-declared types and selected outgoing predicates count. No inferred
BOM completeness, unit conversion or business approval is established.
"""
import re
from backend.mesh_store import PostgresRegistry

ROLES=('product','part','requirement','process')
FIELDS={*(role+'_class' for role in ROLES),'product_part_property','classification_properties','requirement_property','bom_property','process_property'}

def analyse_business(payload):
    dataset=payload.get('dataset_id','');model=payload.get('business_model')
    if not isinstance(dataset,str) or not re.fullmatch('[0-9a-f]{64}',dataset):raise ValueError('Choose a prepared semantic dataset')
    if not isinstance(model,dict) or set(model)-FIELDS:raise ValueError('Choose the business record roles and relationship meanings')
    if 'classification_properties' in model and not isinstance(model['classification_properties'],list):raise ValueError('Classification dimensions must be a list')
    for key,value in model.items():
        values=value if key=='classification_properties' and isinstance(value,list) else [value]
        if len(values)>6 or any(not isinstance(v,str) or not v or len(v.encode())>800 for v in values):raise ValueError('Select bounded vocabulary identities for the business model')
    if not model.get('product_class') or not model.get('part_class'):raise ValueError('Select product and part record types')
    classes={role:model.get(role+'_class') for role in ROLES}
    metrics=[];dimensions=[];links=[];warnings=[]
    with PostgresRegistry('semantic_business_analysis')._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY');c.execute("SET LOCAL statement_timeout='10s'")
        c.execute('SELECT metadata FROM depo_semantic_datasets WHERE dataset_id=%s',(dataset,));row=c.fetchone()
        if not row:raise ValueError('Prepared dataset not found')
        source=row[0]
        if payload.get('configuration_id') and source.get('configuration_id')!=payload['configuration_id']:raise ValueError('Dataset does not belong to the selected configuration')
        populations={}
        for role,iri in classes.items():
            if not iri:populations[role]=None;continue
            c.execute("SELECT count(*) FROM depo_semantic_terms WHERE dataset_id=%s AND term_kind='individual' AND types @> ARRAY[%s]::text[]",(dataset,iri))
            populations[role]=c.fetchone()[0]
            if not populations[role]:raise ValueError('Selected '+role+' type has no business records in this snapshot')
            metrics.append({'area':role,'measure':role.title()+' records','value':populations[role],'grain':'distinct source IRI','status':'observed'})
            c.execute("SELECT iri,label FROM depo_semantic_terms WHERE dataset_id=%s AND term_kind='individual' AND types @> ARRAY[%s]::text[] ORDER BY iri LIMIT 101",(dataset,iri))
            values=c.fetchall();dimensions.append({'dimension':role,'class_iri':iri,'rows':[{'identity':iri,'name':label} for iri,label in values[:100]],'limited':len(values)>100})
        def relationship(key,from_role,to_role,measure):
            predicate=model.get(key)
            if not predicate or not classes.get(to_role):
                metrics.append({'area':from_role,'measure':measure,'value':None,'status':'not_assessed','reason':'Select the outgoing relationship and target record type'});return None
            c.execute("""SELECT count(DISTINCT a.iri),count(DISTINCT b.iri),count(DISTINCT (a.iri,b.iri))
                FROM depo_semantic_terms a JOIN depo_semantic_values v ON v.dataset_id=a.dataset_id AND v.subject_iri=a.iri
                JOIN depo_semantic_terms b ON b.dataset_id=v.dataset_id AND b.iri=v.lexical_value
                WHERE a.dataset_id=%s AND a.term_kind='individual' AND a.types @> ARRAY[%s]::text[]
                AND v.property_iri=%s AND v.value_kind='iri' AND b.term_kind='individual' AND b.types @> ARRAY[%s]::text[]""",(dataset,classes[from_role],predicate,classes[to_role]))
            linked_sources,linked_targets,pairs=c.fetchone()
            metrics.append({'area':from_role,'measure':measure,'value':pairs,'status':'observed','linked_source_records':linked_sources,'linked_target_records':linked_targets,'predicate':predicate,'direction':from_role+' → '+to_role})
            c.execute("""SELECT count(*) FROM depo_semantic_terms a JOIN depo_semantic_values v ON v.dataset_id=a.dataset_id AND v.subject_iri=a.iri
                WHERE a.dataset_id=%s AND a.term_kind='individual' AND a.types @> ARRAY[%s]::text[] AND v.property_iri=%s
                AND (v.value_kind <> 'iri' OR NOT EXISTS (SELECT 1 FROM depo_semantic_terms b WHERE b.dataset_id=v.dataset_id AND b.iri=v.lexical_value AND b.term_kind='individual' AND b.types @> ARRAY[%s]::text[]))""",(dataset,classes[from_role],predicate,classes[to_role]))
            unresolved=c.fetchone()[0]
            if unresolved:warnings.append(str(unresolved)+' '+measure+' assertions have missing or differently typed targets; excluded from verified links')
            c.execute("""SELECT DISTINCT a.iri,a.label,b.iri,b.label
                FROM depo_semantic_terms a JOIN depo_semantic_values v ON v.dataset_id=a.dataset_id AND v.subject_iri=a.iri
                JOIN depo_semantic_terms b ON b.dataset_id=v.dataset_id AND b.iri=v.lexical_value
                WHERE a.dataset_id=%s AND a.term_kind='individual' AND a.types @> ARRAY[%s]::text[]
                AND v.property_iri=%s AND v.value_kind='iri' AND b.term_kind='individual' AND b.types @> ARRAY[%s]::text[] ORDER BY a.iri,b.iri LIMIT 101""",(dataset,classes[from_role],predicate,classes[to_role]))
            edges=c.fetchall();links.append({'name':measure,'from_role':from_role,'to_role':to_role,'predicate':predicate,'limited':len(edges)>100,
                'rows':[{'source_identity':a,'source_name':an,'target_identity':b,'target_name':bn} for a,an,b,bn in edges[:100]]})
            return linked_sources,linked_targets,pairs
        relationship('product_part_property','product','part','Recorded product-to-part links')
        trace=relationship('requirement_property','part','requirement','Recorded part-to-requirement links')
        denominator=populations.get('requirement')
        metrics.append({'area':'requirement','measure':'Requirements with a recorded part link (%)','value':round(100*trace[1]/denominator,2) if trace and denominator else None,'numerator':trace[1] if trace else None,'denominator':denominator,'status':'observed' if trace and denominator else 'not_assessed','formula':'100 × distinct selected requirement IRIs targeted by selected parts / all selected requirement IRIs in this snapshot','scope':'Recorded traceability only; satisfaction, verification and whole-system completeness are not established'})
        relationship('bom_property','part','part','Recorded parent-part to child-part links')
        process=relationship('process_property','part','process','Recorded part-to-process links')
        metrics.append({'area':'process','measure':'Parts with a recorded process link (%)','value':round(100*process[0]/populations['part'],2) if process else None,'numerator':process[0] if process else None,'denominator':populations['part'],'status':'observed' if process else 'not_assessed','formula':'100 × distinct selected parts with a typed process target / all selected parts','scope':'Assignment evidence only; execution readiness is not established'})
        metrics.append({'area':'part','measure':'BOM completeness (%)','value':None,'status':'not_assessed','reason':'An expected assembly scope, revisions, effectivity and required children are needed; leaf parts are not missing BOMs'})
        classifications=[]
        for prop in model.get('classification_properties',[]):
            c.execute("""SELECT left(v.lexical_value,1000),v.datatype_iri,v.language,count(DISTINCT t.iri)
                FROM depo_semantic_terms t JOIN depo_semantic_values v ON v.dataset_id=t.dataset_id AND v.subject_iri=t.iri
                WHERE t.dataset_id=%s AND t.term_kind='individual' AND t.types @> ARRAY[%s]::text[] AND v.property_iri=%s
                GROUP BY v.lexical_value,v.datatype_iri,v.language ORDER BY count(DISTINCT t.iri) DESC,v.lexical_value,v.datatype_iri,v.language LIMIT 101""",(dataset,classes['part'],prop))
            values=c.fetchall();classifications.append({'property_iri':prop,'grain':'distinct part IRI per value; multi-valued groups may overlap','rows':[{'value':value,'datatype':datatype,'language':language,'parts':count} for value,datatype,language,count in values[:100]],'limited':len(values)>100})
    return {'algorithm':'business-overview','dataset_id':dataset,'configuration_id':source.get('configuration_id'),'configuration_context':source.get('configuration_context'),'class_iri':classes['product'],'property_iris':[],
        'business_model':model,'links':links,'population_entities':populations['product'],'rows':metrics,'dimensions':dimensions,'classifications':classifications,
        'hierarchy':['Product portfolio','Part classification','Engineering traceability','Manufacturing BOM and process'],
        'limited':any(d['limited'] for d in dimensions+classifications+links),'source':source,'warnings':warnings,
        'scope':'Snapshot business evidence with explicit role/predicate mapping; no cross-source identity merging, effectivity normalization or approved dimensional warehouse',
        'unit_policy':'Counts and percentages only; no mass/cost/quantity summation or unit conversion',
        'classification':'draft-analysis; semantic model review and product publication remain separate'}
