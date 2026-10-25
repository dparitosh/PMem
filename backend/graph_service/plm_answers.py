"""Bounded typed business reads for common product-development questions."""
import hashlib
import json
from backend.depo_platform.graph_access import graph_projection_reader
from backend.depo_platform.plm_questions import intent

CEIM='https://depo.example.org/ceim/0.1/'


def name(label, raw):
    try: properties=json.loads(raw or '{}')
    except (ValueError,TypeError): properties={}
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
    if selected=='parts_with_pmi':
        rows=publisher._session_rows(
            'MATCH(p:OntologyResource)-[r]-(a:OntologyResource) WHERE p.ontology_id=a.ontology_id '
            'AND any(t IN coalesce(p.rdf_types,[]) WHERE t IN $part_types) '
            'AND $annotation IN coalesce(a.rdf_types,[]) '+scope+
            "AND (type(r) IN ['HAS_PMI','ANNOTATES','HAS_CHARACTERISTIC','TRACE_TO'] OR r.predicate IN $predicates) "
            'RETURN elementId(p) AS part_id,p.label AS part,p.rdf_properties AS part_props, '
            'elementId(a) AS pmi_id,a.label AS pmi,a.rdf_properties AS pmi_props, '
            'elementId(r) AS relationship_id,type(r) AS relationship,r.predicate AS predicate,p.ontology_id AS source,p.prefix AS prefix '
            'ORDER BY part_id,pmi_id,relationship_id LIMIT 21',
            **common,part_types=[CEIM+k for k in ('Part','Product','ProductRevision','Assembly')],annotation=CEIM+'PMIAnnotation',
            predicates=[CEIM+'hasPMI',CEIM+'annotates',CEIM+'hasCharacteristic',CEIM+'traceTo'])
        for row in rows:
            row['part']=name(row['part'],row.pop('part_props',None));row['pmi']=name(row['pmi'],row.pop('pmi_props',None))
            row['association']='Source reference; ownership unverified' if row['relationship']=='TRACE_TO' or row.get('predicate')==CEIM+'traceTo' else 'Recorded typed relationship; review source'
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
    identity=hashlib.sha256(json.dumps([selected,ontology_id,ontology_prefix,rows[:20]],sort_keys=True).encode()).hexdigest()
    return {'evidence_type':'business_answer','resource_id':'business-answer:'+identity,'label':'Product-development evidence',
        'intent':selected,'rows':rows[:20],'description':'Bounded typed Neo4j business-instance read; source references are not semantic ownership.',
        'source':'graph-service:typed-business-read','coverage':{'limit':20,'has_more':len(rows)>20,'whole_graph_complete':False}}
