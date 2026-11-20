"""Bounded source fingerprints owned by the graph service, including legacy intake."""
import hashlib
import json
from backend.depo_platform.graph_access import graph_projection_reader

@graph_projection_reader
def source_revision(publisher, node_id, ontology_id):
    from .context_router import _ontology_node_clause
    eligible = _ontology_node_clause()
    scope = "(coalesce(n.ontology_id,n.source_ontology,n.prefix,'')=$scope)"
    with publisher._driver() as driver, driver.session(database=publisher.database) as session:
        tx=session.begin_transaction(timeout=15)
        try:
            roots=tx.run('MATCH (n) WHERE elementId(n)=$node AND '+eligible+" RETURN coalesce(n.ontology_id,n.source_ontology,n.prefix,'') AS scope",node=node_id).data()
            if len(roots)!=1 or not roots[0]['scope'] or roots[0]['scope']!=ontology_id:
                raise ValueError('Selected business record does not belong to this source scope')
            nodes=tx.run('MATCH (n) WHERE '+eligible+' AND '+scope+' RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties ORDER BY id LIMIT 10001',scope=ontology_id).data()
            if len(nodes)>10000:raise ValueError('Source revision exceeds 10000 records; select a narrower published source')
            ids=[row['id'] for row in nodes]
            edges=tx.run('MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids RETURN elementId(r) AS id,elementId(a) AS source,elementId(b) AS target,type(r) AS type,properties(r) AS properties ORDER BY id LIMIT 40001',ids=ids).data()
            if len(edges)>40000:raise ValueError('Source revision exceeds 40000 relationships; select a narrower published source')
            for row in nodes:row['labels']=sorted(row.get('labels') or [])
            digest=hashlib.sha256(json.dumps({'nodes':nodes,'relationships':edges},sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
            tx.commit()
            return {'kind':'graph-source-revision','node_id':node_id,'ontology_id':ontology_id,'revision_sha256':digest,'status':'retained_graph','limited':False}
        except BaseException:
            tx.rollback();raise
