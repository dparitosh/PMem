"""Bounded RDF snapshots of active published projections, never staging nodes."""
import json
from rdflib import Graph, URIRef, BNode, Literal
from rdflib.namespace import RDF
from backend.depo_platform.graph_access import projection_access
from .neo4j_publisher import publisher


def snapshot_scopes():
    with projection_access():
        return publisher._session_rows("MATCH (p:OntologyPublication) WHERE p.current=true AND p.status='published' RETURN p.ontology_id AS ontology_id,p.prefix AS name,p.publication_id AS publication_id ORDER BY ontology_id LIMIT 201")


def projection_snapshot(ontology_id,namespace=''):
    if not isinstance(ontology_id,str) or not 1<=len(ontology_id)<=256 or len(namespace)>800:raise ValueError('Select a published graph and optional namespace')
    with projection_access(),publisher._driver() as driver,driver.session(database=publisher.database) as session:
        tx=session.begin_transaction(timeout=25)
        try:
            receipts=tx.run("MATCH (p:OntologyPublication {ontology_id:$id}) WHERE p.current=true AND p.status='published' RETURN p.publication_id AS publication_id,properties(p)['artifact_sha256'] AS artifact_sha256",id=ontology_id).data()
            if len(receipts)!=1:raise ValueError('Choose one active published graph; publication evidence is unavailable')
            nodes=tx.run("MATCH (n:OntologyResource {ontology_id:$id}) WHERE n.iri STARTS WITH $namespace RETURN n.iri AS iri,n.kind AS kind,n.rdf_types AS types,n.rdf_properties AS properties ORDER BY n.iri LIMIT 10001",id=ontology_id,namespace=namespace).data()
            if not nodes:raise ValueError('No projected RDF resources exist in this scope')
            if len(nodes)>10000:raise ValueError('Graph exceeds 10000 resources; select a namespace partition')
            edges=tx.run("MATCH (a:OntologyResource {ontology_id:$id})-[r]->(b) WHERE a.iri STARTS WITH $namespace AND r.predicate IS NOT NULL AND b.iri IS NOT NULL AND NOT b:StagedOntologyResource AND NOT b:RetainedOntologyIdentity RETURN DISTINCT a.iri AS source,r.predicate AS predicate,b.iri AS target,b.kind AS kind ORDER BY source,predicate,target LIMIT 100001",id=ontology_id,namespace=namespace).data()
            if len(edges)>100000:raise ValueError('Graph exceeds 100000 relationships; select a narrower namespace')
            graph=Graph();blank={n['iri'] for n in nodes if n['kind'] in {'expression','restriction','axiom'} and not str(n['iri']).startswith(('http:','https:','urn:'))}
            blank.update(e['target'] for e in edges if e['kind'] in {'expression','restriction','axiom'} and not str(e['target']).startswith(('http:','https:','urn:')))
            term=lambda value:BNode(value) if value in blank else URIRef(value)
            for node in nodes:
                subject=term(node['iri'])
                for iri in node['types'] or []:graph.add((subject,RDF.type,URIRef(iri)))
                props=json.loads(node['properties'] or '{}')
                if not isinstance(props,dict):raise ValueError('Projected literal metadata is invalid')
                for predicate,values in props.items():
                    for value in values:
                        graph.add((subject,URIRef(predicate),Literal(value['value'],lang=value.get('language') or None,datatype=URIRef(value['datatype']) if value.get('datatype') else None)))
            for edge in edges:graph.add((term(edge['source']),URIRef(edge['predicate']),term(edge['target'])))
            if len(graph)>250000:raise ValueError('Snapshot exceeds 250000 triples; select a narrower namespace')
            content=graph.serialize(format='nt',encoding='utf-8')
            if len(content)>25*1024*1024:raise ValueError('Snapshot exceeds 25 MiB; select a narrower namespace')
            tx.commit()
            return {'content':content.decode(),'format':'nt','ontology_id':ontology_id,'namespace':namespace,'publication':receipts[0],'triples':len(graph),'scope':'Published RDF projection only; namespace limits subjects. Referenced external terms do not imply equivalence.'}
        except BaseException:tx.rollback();raise
