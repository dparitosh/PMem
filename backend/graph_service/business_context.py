"""Read-only business context over the existing bounded traversal engine."""
from backend.Services.graph_view_service import GraphViewService
from backend.depo_platform.graph_access import graph_projection_reader


def relationship_kind(edge):
    relation = str(edge.get('type') or '').upper()
    if relation in {'SEMANTICALLY_MAPPED_TO', 'INSTANCE_OF', 'TYPED_BY'}:
        return 'recorded_semantic_mapping'
    if relation in {'TRACE_TO', 'MASTERREF', 'MASTER_REFERENCE', 'DERIVED_FROM'} or (edge.get('properties') or {}).get('source_path'):
        return 'source_reference'
    return 'recorded_relationship'


@graph_projection_reader
def retrieve(publisher, *, node_id, ontology_id='', ontology_prefix='', depth=1, limit=60):
    if not isinstance(node_id, str) or not node_id.strip() or len(node_id) > 256:
        raise ValueError('Select a bounded graph node identity')
    rows = publisher._session_rows(
        "MATCH (n) WHERE elementId(n)=$node_id "
        "AND NOT n:StagedOntologyResource AND NOT n:RetainedOntologyIdentity AND NOT n:OntologyPublication "
        "AND ($scope='' OR n.ontology_id=$scope OR n.source_ontology=$scope) "
        "AND ($prefix='' OR n.prefix=$prefix OR n.ontology_prefix=$prefix) "
        "RETURN elementId(n) AS elementId, labels(n) AS labels, properties(n) AS properties",
        node_id=node_id, scope=ontology_id, prefix=ontology_prefix)
    if not rows:
        raise LookupError('Selected business object is unavailable in this scope')
    root = rows[0]
    if not GraphViewService._is_individual_node(root) or GraphViewService._is_metadata_like_node(root):
        raise ValueError('Select a business instance; ontology terms use the ontology browser')
    graph = GraphViewService.get_traversal_slice(node_id=node_id, depth=max(1,min(2,int(depth))), limit=max(20,min(100,int(limit))))
    graph = GraphViewService._filter_graph_nodes(graph, only_individual_nodes=True)
    nodes = [n for n in graph['nodes'] if
             (not ontology_id or (n.get('properties') or {}).get('ontology_id') == ontology_id or (n.get('properties') or {}).get('source_ontology') == ontology_id)
             and (not ontology_prefix or (n.get('properties') or {}).get('prefix') == ontology_prefix or (n.get('properties') or {}).get('ontology_prefix') == ontology_prefix)]
    if not any(n['elementId'] == node_id for n in nodes):
        nodes.insert(0,root)
    ids = {n['elementId'] for n in nodes}
    edges = [dict(e, evidence_kind=relationship_kind(e)) for e in graph['relationships'] if e.get('start') in ids and e.get('end') in ids]
    reasons = {node_id: {'reason':'selected_business_object','path_relationship_ids':[]}}
    for _ in range(max(1,min(2,int(depth)))):
        known=set(reasons)
        for edge in edges:
            for source,target in [(edge['start'],edge['end']),(edge['end'],edge['start'])]:
                if source in known and target not in reasons:
                    reasons[target]={'reason':edge['evidence_kind'],'path_relationship_ids':[*reasons[source]['path_relationship_ids'],edge['elementId']]}
    connected = set(reasons)
    from .vocabulary_evidence import read_vocabulary, unique_label
    vocabulary = read_vocabulary(publisher, [(edge.get('properties') or {}).get('predicate') for edge in edges],
                                 ontology_id=ontology_id, ontology_prefix=ontology_prefix)
    for edge in edges:
        edge['business_label'] = unique_label(vocabulary, (edge.get('properties') or {}).get('predicate'))
    return {'nodes':sorted([n for n in nodes if n['elementId'] in connected],key=lambda n:(n['elementId']!=node_id,n['elementId'])),
            'relationships':[e for e in edges if e['start'] in connected and e['end'] in connected],
            'inclusion':reasons,'root_node_id':node_id,
            'view':{'type':'business-context','ontology_id':ontology_id,'ontology_prefix':ontology_prefix,
                    'depth':max(1,min(2,int(depth))),'limit':max(20,min(100,int(limit))),
                    'truncated':len(graph['nodes']) >= max(20,min(100,int(limit))),
                    'whole_graph_complete':False,'semantic_entailment_verified':False,
                    'limitation':'Recorded connections are evidence to investigate, not proof of impact, equivalence or causation.'}}
