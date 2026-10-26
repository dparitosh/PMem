"""Bounded typed business reads for common product-development questions."""
import hashlib
import json
from backend.depo_platform.graph_access import graph_projection_reader
from backend.depo_platform.plm_questions import intent, requirement_subject

CEIM='https://depo.example.org/ceim/0.1/'


def name(label, raw):
    try: properties=json.loads(raw or '{}')
    except (ValueError,TypeError): properties={}
    if not isinstance(properties,dict): properties={}
    for key in ('name','title','partNumber','sourceId'):
        for iri,values in properties.items():
            if iri.rsplit('/',1)[-1].rsplit('#',1)[-1]==key and isinstance(values,list):
                text=next((v.get('value') for v in values if isinstance(v,dict) and isinstance(v.get('value'),str)),None)
                if text:return text[:220]
    text=str(label or 'Unnamed business record')
    if 'scoped%3A' in text:
        from urllib.parse import unquote
        source_id=unquote(text).rsplit(':',1)[-1]
        return 'Unnamed business record (source #'+source_id[:32]+')'
    return text[:220]


@graph_projection_reader
def retrieve(publisher, *, query, ontology_id='', ontology_prefix=''):
    selected=intent(query)
    if not selected:raise ValueError('Use a product, assembly or part–PMI question')
    scope="AND ($scope='' OR p.ontology_id=$scope) AND ($prefix='' OR p.prefix=$prefix) "
    common=dict(scope=ontology_id,prefix=ontology_prefix)
    if selected == 'associated_requirements':
        subject = requirement_subject(query)
        rows = []
        if subject:
            rows = publisher._session_rows(
                'MATCH (p) WHERE NOT (p:StagedOntologyResource OR p:OntologyPublication) '
                'AND (any(t IN coalesce(p.rdf_types,[]) WHERE t IN $business_types) '
                'OR (p.import_id IS NOT NULL AND p.import_row_key IS NOT NULL AND any(l IN labels(p) WHERE l IN $business_labels))) '
                "AND ($scope='' OR p.ontology_id=$scope OR p.source_ontology=$scope) "
                "AND ($prefix='' OR p.prefix=$prefix OR p.ontology_prefix=$prefix) "
                "AND toLower(coalesce(p.name,p.label,p.title,'')) CONTAINS toLower($subject) "
                'WITH p ORDER BY elementId(p) LIMIT 20 '
                'MATCH path=(p)-[*1..3]-(q) WHERE p<>q '
                'AND all(n IN nodes(path) WHERE NOT (n:StagedOntologyResource OR n:OntologyPublication OR n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty) '
                "AND NOT any(t IN coalesce(n.rdf_types,[]) WHERE t IN $schema_types) "
                "AND ($scope='' OR n.ontology_id=$scope OR n.source_ontology=$scope) "
                "AND ($prefix='' OR n.prefix=$prefix OR n.ontology_prefix=$prefix)) "
                'AND (any(t IN coalesce(q.rdf_types,[]) WHERE t IN $requirement_types) '
                'OR (q.import_id IS NOT NULL AND q.import_row_key IS NOT NULL '
                "AND (any(l IN labels(q) WHERE l IN $requirement_labels) OR toLower(coalesce(q.name,q.label,q.title,'')) CONTAINS 'requirement'))) "
                'RETURN DISTINCT elementId(p) AS subject_id,coalesce(p.name,p.label,p.title) AS subject, '
                'elementId(q) AS requirement_id,coalesce(q.name,q.label,q.title) AS requirement, '
                "coalesce(q.description,q.text,q.value,'') AS detail, "
                "[r IN relationships(path) | {id:elementId(r),type:type(r),predicate:r['predicate']}] AS path, "
                'coalesce(q.ontology_id,q.source_ontology,q.import_id) AS source,coalesce(q.prefix,q.ontology_prefix) AS prefix '
                'ORDER BY subject_id,requirement_id LIMIT 21',
                **common, subject=subject,
                business_types=[CEIM+k for k in ('Product','ProductRevision','Part','Assembly','Requirement','Specification')],
                business_labels=['Product','ProductRevision','Part','Assembly','ProductInstance','Requirement','Specification','RequirementRevision'],
                requirement_types=[CEIM+k for k in ('Requirement','Specification','RequirementRevision')],
                requirement_labels=['Requirement','Specification','RequirementRevision'],
                schema_types=['http://www.w3.org/2002/07/owl#Class','http://www.w3.org/2002/07/owl#ObjectProperty','http://www.w3.org/2002/07/owl#DatatypeProperty'])
    elif selected=='parts_with_pmi':
        rows=publisher._session_rows(
            'MATCH(p:OntologyResource)-[r]-(a:OntologyResource) WHERE p.ontology_id=a.ontology_id '
            'AND any(t IN coalesce(p.rdf_types,[]) WHERE t IN $part_types) '
            'AND any(t IN coalesce(a.rdf_types,[]) WHERE t IN $pmi_types) '+scope+
            "AND ((startNode(r)=p AND (r.predicate IN $outgoing OR (r.predicate IS NULL AND type(r) IN ['HAS_PMI','HAS_CHARACTERISTIC']))) "
            "OR (startNode(r)=a AND (r.predicate=$annotates OR (r.predicate IS NULL AND type(r)='ANNOTATES'))) "
            "OR r.predicate=$trace_predicate OR (r.predicate IS NULL AND type(r)='TRACE_TO')) "
            'RETURN elementId(p) AS part_id,p.label AS part,p.rdf_properties AS part_props, '
            'elementId(a) AS pmi_id,a.label AS pmi,a.rdf_properties AS pmi_props, '
            'elementId(r) AS relationship_id,type(r) AS relationship,r.predicate AS predicate,p.ontology_id AS source,p.prefix AS prefix '
            "ORDER BY CASE WHEN predicate=$trace_predicate OR (predicate IS NULL AND relationship='TRACE_TO') THEN 1 ELSE 0 END,part_id,pmi_id,relationship_id LIMIT 21",
            trace_predicate=CEIM+'traceTo',
            **common,part_types=[CEIM+k for k in ('Part','Product','ProductRevision','Assembly')],pmi_types=[CEIM+'PMIAnnotation',
                'https://depo.example.org/ontology/bill-of-characteristics/1.0/DimensionalCharacteristic',
                'https://depo.example.org/ontology/bill-of-characteristics/1.0/TolerancedCharacteristic'],
            outgoing=[CEIM+'hasPMI',CEIM+'hasCharacteristic'],annotates=CEIM+'annotates')
        for row in rows:
            row['part']=name(row['part'],row.pop('part_props',None));row['pmi']=name(row['pmi'],row.pop('pmi_props',None))
            predicate=row.get('predicate')
            trace=predicate==CEIM+'traceTo' if predicate is not None else row['relationship']=='TRACE_TO'
            row['association_status']='source_reference' if trace else 'recorded_association'
            row['association']='Source reference; ownership unverified' if trace else 'Recorded typed association; see source evidence'
    else:
        rows=publisher._session_rows(
            'CALL { MATCH(p:OntologyResource) WHERE any(t IN coalesce(p.rdf_types,[]) WHERE t IN $types) RETURN p '
            'UNION MATCH(p) WHERE p.import_id IS NOT NULL AND p.import_row_key IS NOT NULL '
            'AND any(label IN labels(p) WHERE label IN $labels) '
            'AND NOT (p:StagedOntologyResource OR p:RetainedOntologyIdentity OR p:OntologyPublication) RETURN p } '
            "WITH p WHERE ($scope='' OR p.ontology_id=$scope OR p.source_ontology=$scope) AND ($prefix='' OR p.prefix=$prefix OR p.ontology_prefix=$prefix) "
            'RETURN elementId(p) AS node_id,coalesce(p.name,p.label) AS name,p.rdf_properties AS props,coalesce(p.rdf_types,[]) AS types,labels(p) AS labels, '
            'coalesce(p.ontology_id,p.source_ontology,p.import_id) AS source,coalesce(p.prefix,p.ontology_prefix) AS prefix ORDER BY source,node_id LIMIT 21',
            **common,types=[CEIM+k for k in ('Product','ProductRevision','Part','Assembly')],labels=['Product','ProductRevision','Part','Assembly','ProductInstance'])
        for row in rows:
            row['name']=name(row['name'],row.pop('props',None));row['kind']=', '.join(t.rsplit('/',1)[-1] for t in row.pop('types') if t.startswith(CEIM)) or ', '.join(t for t in row.pop('labels',[]) if t in {'Product','ProductRevision','Part','Assembly','ProductInstance'})
    vocabulary = []
    predicates = sorted({edge['predicate'] for row in rows[:20] for edge in row.get('path', []) if edge.get('predicate')})
    if predicates:
        vocabulary = publisher._session_rows(
            'MATCH (term:OntologyResource) WHERE term.iri IN $predicates '
            'RETURN term.iri AS iri,term.label AS label,term.definition AS description '
            'ORDER BY iri,label LIMIT 100', predicates=predicates[:60])
        # Conflicting labels from different releases are not resolved by order.
        for row in rows[:20]:
            for edge in row.get('path', []):
                labels = {item.get('label') for item in vocabulary if item.get('iri') == edge.get('predicate') and item.get('label')}
                edge['business_label'] = next(iter(labels)) if len(labels) == 1 else None
    identity=hashlib.sha256(json.dumps([selected,ontology_id,ontology_prefix,rows[:20],vocabulary],sort_keys=True).encode()).hexdigest()
    return {'evidence_type':'business_answer','resource_id':'business-answer:'+identity,'label':'Product-development evidence',
        'intent':selected,'rows':rows[:20],'vocabulary':vocabulary,'description':'Bounded typed business-instance read; source references are not semantic ownership.',
        'source':'graph-service:typed-business-read','coverage':{'limit':20,'has_more':len(rows)>20,'whole_graph_complete':False}}
