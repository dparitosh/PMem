"""Native worker registers a named immutable snapshot through owning services."""
import json
from urllib.parse import quote
from backend.depo_platform.peer_http import peer_response
from backend.depo_platform.network import service_bearer_headers
from backend.depo_platform.service_urls import service_url


def register_graph_snapshot(payload,correlation_id):
    identity=payload.get('ontology_id','');namespace=payload.get('namespace','')
    if not isinstance(identity,str) or not 1<=len(identity)<=256:raise ValueError('Choose a published graph source')
    expected=payload.get('graph_publication_id')
    if not isinstance(expected,str) or not expected:raise ValueError('Refresh and select a published graph version')
    graph=service_url('GRAPH_SERVICE_URL','http://127.0.0.1:8013/api/v1')
    response=peer_response('GET',graph+'/graph/analytics/snapshot/'+quote(identity,safe=''),params={'namespace':namespace},
        headers=service_bearer_headers('GRAPH_READ_TOKEN',service_name='graph snapshot',endpoint=graph),budget=45,response_limit=32*1024*1024)
    if response.status_code==422:raise ValueError('Snapshot rejected; partition the published graph by namespace or restore its publication evidence')
    response.raise_for_status();snapshot=response.json()
    if snapshot.get('ontology_id')!=identity or snapshot.get('namespace')!=namespace:raise ValueError('Graph snapshot scope differs from requested source')
    if snapshot.get('publication',{}).get('publication_id')!=expected:raise ValueError('Published graph version changed; refresh and select it again')
    registry=service_url('SEMANTIC_REGISTRY_URL','http://127.0.0.1:8011/api/v1/metadata-registry')
    name=(payload.get('name') or 'Published graph '+identity)[:250]
    # Retain publication identity inside RDF as provenance, without modifying business entities.
    from rdflib import Graph,URIRef,Literal
    from rdflib.namespace import DCTERMS
    rdf=Graph().parse(data=snapshot['content'],format='nt')
    import hashlib
    source=URIRef('urn:depo:snapshot:'+hashlib.sha256(json.dumps(snapshot['publication'],sort_keys=True).encode()).hexdigest())
    rdf.add((source,DCTERMS.source,Literal(identity)))
    rdf.add((source,DCTERMS.identifier,Literal(snapshot['publication']['publication_id'])))
    content=('\n'.join(sorted(rdf.serialize(format='nt').splitlines()))+'\n').encode('utf-8')
    response=peer_response('POST',registry+'/rdf-sources',headers=service_bearer_headers('ONTOLOGY_APPROVAL_TOKEN',service_name='metadata source registration',endpoint=registry),budget=60,response_limit=1024*1024,
        data={'name':name},files={'file':('published-graph.nt',content,'application/n-triples')})
    response.raise_for_status();registered=response.json()
    artifact=registered['artifact_id']
    return {'algorithm':'graph-snapshot','dataset_id':None,'configuration_id':None,'population_entities':0,'rows':[{'source':name,'triples':snapshot['triples'],'status':'Registered source draft; select it to prepare records'}],
        'source':{'artifact_id':artifact},'source_id':registered['source_id'],'limited':False,'scope':snapshot['scope'],'unit_policy':'No conversion performed','classification':'draft source; no product approval',
        'graph_publication':snapshot['publication']}
