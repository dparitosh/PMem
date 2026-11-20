"""Optional Neo4j GDS adapter with private, short-lived in-memory projections."""
import logging
from uuid import uuid4
from neo4j import Query
from backend.depo_platform.operations import current_operation


def pagerank(publisher, request, nodes):
    """Return None only when GDS is absent; execution errors never silently fall back."""
    with publisher._driver() as driver, driver.session(database=publisher.database) as session:
        def run(query, **parameters):
            timeout=current_operation().timeout(15) if current_operation() else 15
            return session.run(Query(query,timeout=timeout),parameters).data()
        available=run("SHOW FUNCTIONS YIELD name WHERE name='gds.version' RETURN name")
        if not available: return None
        version=run('RETURN gds.version() AS version')[0]['version']
        name='nexus_read_'+uuid4().hex
        ids=[node['id'] for node in nodes]
        parameters={'ids':ids,'predicates':request.predicates}
        try:
            run("CALL gds.graph.project.cypher($name, $nodes, $edges, {parameters:$parameters}) YIELD nodeCount,relationshipCount RETURN nodeCount,relationshipCount",
                name=name, nodes='MATCH (n) WHERE elementId(n) IN $ids RETURN id(n) AS id',
                edges='MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids AND a<>b AND r.predicate IN $predicates RETURN DISTINCT id(a) AS source,id(b) AS target',parameters=parameters)
            estimate=run('CALL gds.pageRank.stream.estimate($name,{}) YIELD bytesMax RETURN bytesMax',name=name)
            if not estimate or estimate[0]['bytesMax']>64*1024*1024: raise ValueError('Computation exceeds the 64 MiB graph-analysis budget')
            config={'dampingFactor':0.85,'maxIterations':100,'tolerance':1e-8,'concurrency':1}
            if request.node_id:
                seed=run('MATCH (n) WHERE elementId(n)=$seed RETURN id(n) AS id',seed=request.node_id)
                if len(seed)!=1: raise ValueError('Selected seed is unavailable')
                config['sourceNodes']=[seed[0]['id']]
            rows=run('CALL gds.pageRank.stream($name,$config) YIELD nodeId,score RETURN elementId(gds.util.asNode(nodeId)) AS node_id,score ORDER BY score DESC,node_id LIMIT $top',name=name,config=config,top=request.top_n)
            return rows, {'name':'neo4j-gds','version':version}
        finally:
            # Never write algorithm scores into the business graph. Cleanup uses
            # a short independent deadline even when the computation expired.
            try: session.run(Query('CALL gds.graph.drop($name,false) YIELD graphName RETURN graphName',timeout=5),name=name).consume()
            except Exception:
                logging.getLogger(__name__).exception('Transient graph projection cleanup failed: %s',name)
