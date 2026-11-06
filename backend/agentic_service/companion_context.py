"""Read-only Companion context through the owning service's authenticated API."""
import asyncio
import json
import re
import httpx
from backend.depo_platform.service_urls import service_url
from backend.depo_platform.network import gateway_subscription_headers, bounded_timeout_seconds
from .response_limits import read_bounded_response


async def _read_json(service, default, path, params, headers):
    root=service_url(service,default).rstrip('/')
    if not root.endswith('/api/v1'):root+='/api/v1'
    endpoint=root+path
    auth={key:value for key,value in (headers or {}).items() if key.lower()=='authorization'}
    auth.update(gateway_subscription_headers(endpoint))
    budget=bounded_timeout_seconds('COMPANION_RETRIEVAL_TIMEOUT_SECONDS',default=15,maximum=120)
    async with asyncio.timeout(budget),httpx.AsyncClient(timeout=budget,trust_env=False) as client:
        async with client.stream('GET',endpoint,params=params,headers=auth) as response:
            response.raise_for_status()
            body=json.loads(await read_bounded_response(response))
    if not isinstance(body,dict):raise ValueError('Invalid service evidence')
    return body,endpoint


async def mapping_context(query, *, headers, ontology_id='', ontology_prefix=''):
    if not re.search(r'\b(map|maps|mapping|mappings|merge|merged|merging|alignment|consolidation)\b',query,re.I):
        return {'evidence':[], 'status':'not_requested'}
    # Forward only the authenticated read bearer. A graph APIM subscription key
    # must never be forwarded to another service's gateway.
    body,_=await _read_json('ONTOLOGY_SERVICE_URL','http://127.0.0.1:8011','/ontologies/companion/mapping-evidence',
                           {'query':query,'ontology_id':ontology_id,'ontology_prefix':ontology_prefix},headers)
    items=body.get('evidence') if isinstance(body,dict) else None
    if not isinstance(items,list) or len(items)>6 or any(not isinstance(item,dict) or item.get('evidence_type')!='mapping_review' or not isinstance(item.get('description'),str) or not isinstance(item.get('resource_id'),str) or not item.get('resource_id') or len(item['resource_id'])>2000 or len(item['description'])>6000 or item.get('source')!='ontology-service:retained-merge-review' or not isinstance(item.get('label'),str) for item in items):
        raise ValueError('Invalid retained mapping evidence')
    items=[{key:item.get(key) for key in ('evidence_type','resource_id','label','description','created_at','source')} for item in items]
    return {'evidence':items,'status':'available','coverage':body.get('coverage')}


PAGE_READS={
    'catalog':('DATA_CATALOG_URL','http://127.0.0.1:8016','/catalog/products','products'),
    'data-products':('DATA_PRODUCT_SERVICE_URL','http://127.0.0.1:8017','/data-products','products'),
    'data-flow':('DATA_PIPELINE_SERVICE_URL','http://127.0.0.1:8019','/pipeline/jobs/runs','runs'),
}


async def business_context(node_id, *, headers, ontology_id='', ontology_prefix=''):
    body, endpoint=await _read_json('GRAPH_SERVICE_URL','http://127.0.0.1:8013','/graph/business-context',
        {'node_id':node_id,'ontology_id':ontology_id,'ontology_prefix':ontology_prefix,'depth':1,'limit':20},headers)
    nodes,edges=body.get('nodes'),body.get('relationships')
    if not isinstance(nodes,list) or not isinstance(edges,list) or len(nodes)>100 or len(edges)>400:
        raise ValueError('Invalid business context evidence')
    if body.get('root_node_id')!=node_id or any(not isinstance(n,dict) or not isinstance(n.get('elementId'),str) or not isinstance(n.get('properties'),dict) for n in nodes):
        raise ValueError('Invalid business context identity')
    ids={n['elementId'] for n in nodes}
    if len(ids)!=len(nodes) or node_id not in ids:
        raise ValueError('Missing or duplicate business context identity')
    for n in nodes:
        props=n['properties']
        if ontology_id and ontology_id not in (props.get('ontology_id'),props.get('source_ontology')):
            raise ValueError('Business evidence changed selected ontology')
        if ontology_prefix and ontology_prefix not in (props.get('prefix'),props.get('ontology_prefix')):
            raise ValueError('Business evidence changed selected prefix')
    if any(not isinstance(e,dict) or e.get('start') not in ids or e.get('end') not in ids for e in edges):
        raise ValueError('Business relationship changed evidence scope')
    return body,endpoint


async def document_context(query, *, headers, ontology_id='', ontology_prefix=''):
    body,_=await _read_json('GRAPH_SERVICE_URL','http://127.0.0.1:8013','/graph/document-evidence',
        {'query':query[:500],'ontology_id':ontology_id,'ontology_prefix':ontology_prefix,'limit':6},headers)
    items=body.get('evidence')
    if body.get('status') not in {'available','no_evidence','not_indexed'} or not isinstance(items,list) or len(items)>6:
        raise ValueError('Invalid indexed evidence response')
    for item in items:
        if not isinstance(item,dict) or item.get('evidence_type') not in {'document_excerpt','graph_excerpt'} or item.get('source')!='neo4j:retained-evidence-index':
            raise ValueError('Invalid indexed evidence source')
        if not isinstance(item.get('label'),str) or len(item['label'])>300 or not isinstance(item.get('resource_id'),str) or not item['resource_id'] or len(item['resource_id'])>256 or not isinstance(item.get('description'),str) or len(item['description'])>2000:
            raise ValueError('Invalid indexed evidence identity or excerpt')
    body['evidence']=[{key:item.get(key) for key in ('evidence_type','resource_id','label','description','source_node_id','content_hash','publication_revision','source')} for item in items]
    return body
CONTEXT_PAGES={'graph','whereused','modeling','requirements','ontology','qif'}


def semantic_question(query):
    return bool(re.search(r'\b(owl[ -]?dl|hermit|logical(?:ly)? consisten\w*|unsatisfiab\w*|embedded (?:ontology|foundation)|foundation (?:term|definition|vocabulary))\b', query, re.I))


async def semantic_context(query, *, headers, ontology_id=''):
    """Explicit semantic questions use model evidence, never lexical business matches."""
    from urllib.parse import quote
    from backend.depo_platform.semantic_support import assessment
    if not semantic_question(query): return None
    if re.search(r'\b(embedded|foundation)\b', query, re.I):
        body, endpoint = await _read_json('ONTOLOGY_SERVICE_URL', 'http://127.0.0.1:8011',
            '/ontologies/foundation', {'limit': 12}, headers)
        if not isinstance(body.get('terms'), list) or not body.get('bundle_sha256'):
            raise ValueError('Foundation definitions are unavailable')
        terms = body['terms'][:12]
        from .business_answers import cell
        text = 'Embedded reference vocabulary; customer alignment and business facts require separate evidence.\n\n| Term | Meaning |\n|---|---|'
        for term in terms:
            text += f"\n| {cell((term.get('labels') or [term.get('iri')])[0])} | {cell('; '.join(term.get('definitions') or []))} |"
        evidence = {'resource_id': 'foundation:' + body['bundle_sha256'], 'label': 'Embedded foundation definitions',
                    'description': text, 'source': endpoint, 'evidence_type': 'semantic_reference'}
        return {'status': 'grounded', 'answerable': True, 'response': text + f"\n\n[evidence:{evidence['resource_id']}]", 'evidence': [evidence], 'sources': [endpoint],
                'retrieval': {'answer_scope': 'reference_definitions', 'semantic_entailment_verified': False},
                'generation': {'enabled': False, 'status': 'not_requested'}}
    if not ontology_id:
        return {'status': 'needs_input', 'answerable': False, 'response': 'Select an ontology to inspect its current logical consistency evidence.',
                'evidence': [], 'sources': [], 'generation': {'enabled': False, 'status': 'not_requested'}}
    body, endpoint = await _read_json('ONTOLOGY_SERVICE_URL', 'http://127.0.0.1:8011',
        '/ontologies/' + quote(ontology_id, safe='') + '/semantic-evidence', {}, headers)
    if body.get('ontology_id') != ontology_id: raise ValueError('Semantic evidence changed selected ontology')
    report = assessment(body)
    identifier = str(body.get('evidence_id') or ('not-checked:' + ontology_id))
    text = f"Logical consistency: {report.get('status', 'unknown')}. {report['business_summary']}\n\nNext action: {report['next_action']}. This check does not establish instance conformance or authorize publication."
    evidence = {'resource_id': identifier, 'label': 'Selected model reasoning assessment', 'description': text,
                'source': endpoint, 'evidence_type': 'semantic_assessment', 'assessment': report}
    return {'status': 'grounded', 'answerable': True, 'response': text + f' [evidence:{identifier}]',
            'evidence': [evidence], 'sources': [endpoint], 'retrieval': {'answer_scope': 'retained_model_consistency',
                'semantic_entailment_verified': report.get('consistency_verified') is True},
            'generation': {'enabled': False, 'status': 'not_requested'}}


async def page_context(query, *, page, headers, ontology_id='', ontology_prefix=''):
    """Use existing owning-service reads. A page hint never grants access."""
    if page in PAGE_READS:
        service,default,path,collection=PAGE_READS[page]
        body,endpoint=await _read_json(service,default,path,{'limit':20,'offset':0},headers)
        rows=body.get(collection)
    elif page in CONTEXT_PAGES and not ontology_id and not ontology_prefix:
        body,endpoint=await _read_json('ONTOLOGY_SERVICE_URL','http://127.0.0.1:8011','/ontologies/business-context/search',{'query':query,'limit':8},headers)
        rows=body.get('results');collection='business objects'
    else:
        return {'evidence':[],'status':'not_requested'}
    if not isinstance(rows,list) or len(rows)>20 or any(not isinstance(row,dict) for row in rows):
        raise ValueError('Invalid page evidence')
    evidence=[]
    # Keep this projection deliberately small: no credentials, task payloads,
    # arbitrary metadata or model-generated records are forwarded as facts.
    for row in rows[:8]:
        node=row.get('node') if isinstance(row.get('node'),dict) else row
        identifier=next((str(node[key]) for key in ('id','product_version','product_id','run_id','job_id') if node.get(key)),None)
        if not identifier:continue
        label=str(node.get('name') or node.get('label') or node.get('content') or ((node.get('properties') or {}).get('content') if isinstance(node.get('properties'),dict) else None) or row.get('content') or identifier)[:400]
        details={key:str(node[key])[:300] for key in ('status','version','domain','type','validation_status','publication_status') if node.get(key) is not None}
        from .business_answers import business_text
        detail_text='; '.join(f"{key.replace('_',' ').capitalize()}: {business_text(value)}" for key,value in details.items())
        description=f"{business_text(label)}. {detail_text or 'No additional business details recorded'}. Retained {collection} record; approval and publication must be checked separately."
        evidence.append({'evidence_type':'application_record','resource_id':identifier[:256],'label':label,'description':description,'source':endpoint})
    total=body.get('total')
    evidence.insert(0,{'evidence_type':'application_record','resource_id':'page:'+page,'label':page+' service evidence',
        'description':f"{page}: the service returned {len(rows)} {collection} on this page"+(f" out of {total} retained records" if type(total) is int and total>=0 else '')+'. This is a bounded listing; it does not establish relevance, semantic equivalence or whole-graph completeness.', 'source':endpoint})
    return {'evidence':evidence[:8],'status':'available',
            'representation': 'postgres_business_context' if collection == 'business objects' else 'owning_service_records',
            'source_revision_status': 'unverified',
            'coverage': {'returned_records': len(rows), 'selected_evidence': min(len(evidence), 8),
                         'bounded_listing': True, 'whole_graph_complete': False}}


async def plm_context(query, *, headers, ontology_id='', ontology_prefix='', node_id=''):
    body,_=await _read_json('GRAPH_SERVICE_URL','http://127.0.0.1:8013','/graph/business-answer',
        {'query':query[:500],'ontology_id':ontology_id,'ontology_prefix':ontology_prefix, **({'node_id':node_id} if node_id else {})},headers)
    if body.get('evidence_type')!='business_answer' or body.get('source')!='graph-service:typed-business-read' or not isinstance(body.get('rows'),list) or len(body['rows'])>20 or not isinstance(body.get('resource_id'),str) or not body['resource_id'].startswith('business-answer:'):
        raise ValueError('Invalid PLM evidence')
    from backend.depo_platform.plm_questions import intent
    if not intent(query) or body.get('intent') != intent(query):
        raise ValueError('PLM evidence intent does not match the question')
    if any(not isinstance(row,dict) or (ontology_id and row.get('source')!=ontology_id) or (ontology_prefix and row.get('prefix')!=ontology_prefix) for row in body['rows']):
        raise ValueError('PLM evidence changed selected source')
    required = {'associated_requirements':('subject','requirement'), 'parts_with_pmi':('part','pmi'),
                'product_assembly':('name',)}[body['intent']]
    for row in body['rows']:
        identity_field={'associated_requirements':'subject_id','parts_with_pmi':'part_id','product_assembly':'node_id'}[body['intent']]
        if node_id and row.get(identity_field)!=node_id:
            raise ValueError('PLM evidence changed the selected business object')
        if any(not isinstance(row.get(key),str) or not row[key].strip() for key in required):
            raise ValueError('PLM evidence is missing business names')
        if body['intent']=='associated_requirements' and (not isinstance(row.get('path'),list) or not row['path']
                or any(not isinstance(edge,dict) or not isinstance(edge.get('type'),str) for edge in row['path'])):
            raise ValueError('PLM evidence is missing a recorded requirement path')
        if body['intent']=='parts_with_pmi' and row.get('association_status') not in {'source_reference','recorded_association'}:
            raise ValueError('PLM evidence is missing an assessed PMI association')
    return {key:body.get(key) for key in ('evidence_type','resource_id','label','intent','rows','description','source','coverage','vocabulary')}
