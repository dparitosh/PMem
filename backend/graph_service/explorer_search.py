"""Parameterized, scoped search of graph objects and relationship evidence."""
import time
from .neo4j_publisher import publisher
from backend.depo_platform.graph_access import graph_projection_reader

PRIVATE_KEYS=['password','secret','token','apikey','authorization','credential','embedding','vector']


def eligible(alias):
    return f"""NOT ({alias}:StagedOntologyResource OR {alias}:RetainedOntologyIdentity OR {alias}:OntologyPublication OR {alias}:GraphChunk OR {alias}:DatasheetChunk)
      AND ((NOT $instances_only AND ({alias}:OntologyResource OR {alias}:OntologyClass OR {alias}:ObjectProperty OR {alias}:DatatypeProperty OR {alias}:AnnotationProperty OR {alias}:NamedIndividual))
        OR any(label IN labels({alias}) WHERE label IN $instance_labels)
        OR {alias}:NamedIndividual OR ({alias}:OntologyResource AND {alias}.kind IN ['NamedIndividual','Individual','individual'])
        OR {alias}.is_cad_business_object=true OR {alias}.semantic_role IN $instance_roles)
      AND (NOT $instances_only OR (NOT ({alias}:OntologyClass OR {alias}:ObjectProperty OR {alias}:DatatypeProperty OR {alias}:AnnotationProperty)
        AND (NOT {alias}:OntologyResource OR {alias}.kind IN ['NamedIndividual','Individual','individual'])))
      AND ($scope='' OR $scope IN [{alias}.ontology_id,{alias}.source_ontology,{alias}.prefix,{alias}.ontology_prefix]
        OR EXISTS {{ MATCH ({alias})-[typed]->(cls) WHERE type(typed) IN ['INSTANCE_OF','TYPED_BY','CLASSIFIED_AS']
          AND NOT (cls:StagedOntologyResource OR cls:RetainedOntologyIdentity)
          AND $scope IN [cls.ontology_id,cls.prefix,cls.ontology_prefix] }})"""


def matches(alias):
    return f"""any(key IN keys({alias}) WHERE NOT any(private IN $private_keys WHERE replace(replace(toLower(key),'_',''),'-','') CONTAINS private)
      AND (toLower(key) CONTAINS $needle OR any(value IN CASE WHEN {alias}[key] IS :: LIST<ANY> THEN {alias}[key] ELSE [{alias}[key]] END
        WHERE toLower(coalesce(toStringOrNull(value),'')) CONTAINS $needle)))"""


def properties(alias):
    return f"""[key IN keys({alias}) WHERE NOT any(private IN $private_keys WHERE replace(replace(toLower(key),'_',''),'-','') CONTAINS private) | [left(key,128),left(coalesce(toStringOrNull({alias}[key]),
      reduce(text='',v IN CASE WHEN {alias}[key] IS :: LIST<ANY> THEN {alias}[key][..64] ELSE [] END | text+' '+coalesce(toStringOrNull(v),''))),256)]][..32]"""


def node(alias):
    return f"{{elementId:elementId({alias}), label:left(coalesce(toStringOrNull({alias}.label),toStringOrNull({alias}.name),toStringOrNull({alias}.title),{alias}.iri,{alias}.uri,elementId({alias})),400),type:coalesce({alias}.kind,head(labels({alias}))),labels:CASE WHEN {alias}.kind IS NOT NULL THEN [{alias}.kind]+labels({alias}) ELSE labels({alias}) END,can_traverse:true,properties:{properties(alias)}}}"


NODE_QUERY=f"""MATCH (n) WHERE {eligible('n')} AND (toLower(elementId(n)) CONTAINS $needle OR any(label IN labels(n) WHERE toLower(label) CONTAINS $needle) OR {matches('n')})
  RETURN {node('n')} AS node ORDER BY node.label,node.elementId LIMIT $limit"""
EDGE_QUERY=f"""MATCH (a)-[r]->(b) WHERE {eligible('a')} AND {eligible('b')}
  AND (toLower(type(r)) CONTAINS $needle OR toLower(elementId(r)) CONTAINS $needle OR {matches('r')})
  RETURN {node('a')} AS source,{node('b')} AS target,
    {{elementId:elementId(r),start:elementId(a),end:elementId(b),type:type(r),properties:{properties('r')}}} AS edge
  ORDER BY edge.type,edge.elementId LIMIT $limit"""


def unpack(value):
    fields=dict(value.get('properties') or [])
    if value.get('label'):
        fields.setdefault('name',value['label'])
        fields.setdefault('kind',value.get('type','resource'))
    return {**value,'properties':fields}


@graph_projection_reader
def search(query, scope='', limit=80, instances_only=False):
    if not isinstance(query,str) or not 1<=len(query.strip())<=500 or len(scope)>256:
        raise ValueError('Supply a search of 1–500 characters and a scope of at most 256 characters')
    from backend.Services.graph_view_service import GraphViewService
    limit=max(1,min(int(limit),200))
    term=query.strip().lower().rstrip('*')
    if not term:raise ValueError('Supply a search term before the wildcard')
    params=dict(needle=term,scope=scope,limit=limit+1,instances_only=instances_only,
        instance_labels=GraphViewService.INSTANCE_NODE_LABELS,instance_roles=GraphViewService.INSTANCE_SEMANTIC_ROLES,private_keys=PRIVATE_KEYS)
    deadline=time.monotonic()+30
    def read(statement,**values):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Explorer search deadline elapsed')
        return publisher._session_rows(statement,_timeout_seconds=remaining,**values)
    rows=read(NODE_QUERY,**params)
    relationships=read(EDGE_QUERY,**params)
    nodes={row['node']['elementId']:unpack(row['node']) for row in rows[:limit]}
    edges=[]
    for row in relationships[:limit]:
        nodes.update({row[key]['elementId']:unpack(row[key]) for key in ('source','target')})
        edges.append(unpack(row['edge']))
    # Include the bounded connections between the selected matching endpoints.
    ids=list(nodes)
    if ids:
        connected=read(f"MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids RETURN {{elementId:elementId(r),start:elementId(a),end:elementId(b),type:type(r),properties:{properties('r')}}} AS edge ORDER BY edge.elementId LIMIT $limit",ids=ids,limit=limit*4,private_keys=PRIVATE_KEYS)
        edges=list({edge['elementId']:edge for edge in edges+[unpack(row['edge']) for row in connected]}.values())
    return {'nodes':list(nodes.values()),'relationships':edges,'counts':{'nodes':len(nodes),'relationships':len(edges)},
        'view':{'type':'universal-search','query':query,'scope':scope,'limit':limit,'truncated':len(rows)>limit or len(relationships)>limit,
                'match_fields':['node','relationship','property_name','property_value'],'source':'neo4j','strategy':'bounded_substring_scan','property_excerpt':{'fields':32,'characters_per_value':256}}}
