"""Bounded lexical evidence retrieval; embeddings are neither required nor implied."""
import re
from backend.depo_platform.graph_access import graph_projection_reader

INDEX='idx_depo_context_evidence'


@graph_projection_reader
def retrieve(publisher, *, query, ontology_id='', ontology_prefix='', node_id='', limit=6):
    tokens=sorted(set(re.findall(r'[a-z0-9]{3,}',str(query).lower())))[:16]
    if not tokens:
        raise ValueError('Supply at least one searchable evidence term')
    indexes=publisher._session_rows('SHOW INDEXES YIELD name,state WHERE name=$name RETURN name,state',name=INDEX)
    if not indexes or indexes[0]['state']!='ONLINE':
        return {'status':'not_indexed','evidence':[],'retrieval':{'mode':'lexical_fulltext','whole_source_complete':False}}
    # Alphanumeric tokens only: user text cannot inject Lucene operators.
    search=' OR '.join('"'+token+'"' for token in tokens)
    rows=publisher._session_rows(
        'CALL db.index.fulltext.queryNodes($index,$lucene_query,{limit:100}) YIELD node AS chunk,score '
        'OPTIONAL MATCH (chunk)-[:EMBEDDED_FROM]->(source) '
        'WITH chunk,score,source WHERE (source IS NULL OR NOT (source:StagedOntologyResource OR source:RetainedOntologyIdentity OR source:OntologyPublication)) '
        "AND ($scope='' OR chunk.ontology_id=$scope OR source.ontology_id=$scope OR source.source_ontology=$scope) "
        "AND ($prefix='' OR chunk.prefix=$prefix OR source.prefix=$prefix OR source.ontology_prefix=$prefix) "
        "AND ($node_id='' OR elementId(source)=$node_id OR chunk.node_id=$node_id) "
        'RETURN DISTINCT elementId(chunk) AS resource_id,elementId(source) AS source_node_id,labels(chunk) AS labels, '
        "left(coalesce(chunk.title,source.name,source.label,'Retained evidence'),300) AS title, "
        'left(chunk.content,2000) AS excerpt,chunk.content_hash AS content_hash,source.publication_revision AS publication_revision,score '
        'ORDER BY score DESC,resource_id LIMIT $limit',
        index=INDEX,lucene_query=search,scope=ontology_id,prefix=ontology_prefix,node_id=node_id,limit=max(1,min(10,int(limit))))
    evidence=[{'evidence_type':'document_excerpt' if 'DatasheetChunk' in r.get('labels',[]) else 'graph_excerpt',
        'resource_id':r['resource_id'],'label':r['title'],'description':r['excerpt'],
        'source_node_id':r.get('source_node_id'),'content_hash':r.get('content_hash'),
        'publication_revision':r.get('publication_revision'),'source':'neo4j:retained-evidence-index'} for r in rows if r.get('excerpt')]
    return {'status':'available' if evidence else 'no_evidence','evidence':evidence,
            'retrieval':{'mode':'lexical_fulltext','source_revision_status':'unverified','candidate_limit':100,'returned':len(evidence),'whole_source_complete':False,
                         'semantic_entailment_verified':False,'limitation':'Indexed excerpts only; absent results do not establish that no source documents exist.'}}
