"""Bounded graph computations; no model-generated queries or business writes."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
import networkx as nx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.depo_platform.graph_access import scoped_projection_access
from backend.depo_platform.operations import current_operation
from .business_types import business_instance_filter
from .engineering_comparison import kind

ALGORITHMS = ('pagerank', 'personalized-pagerank', 'node-similarity', 'traceability', 'triangle-count')
TOOL_VERSION = '1'
NODE_LIMIT, EDGE_LIMIT = 1000, 5000

class ComputationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ontology_id: Annotated[str, Field(min_length=1, max_length=128)]
    publication_id: Annotated[str, Field(min_length=1, max_length=128)]
    algorithm: Literal['pagerank', 'personalized-pagerank', 'node-similarity', 'traceability', 'triangle-count']
    predicates: Annotated[list[Annotated[str, Field(min_length=1, max_length=800)]], Field(min_length=1, max_length=12)]
    node_id: Annotated[str, Field(max_length=256)] = ''
    top_n: Annotated[int, Field(ge=1, le=50)] = 10

    @model_validator(mode='after')
    def selected(self):
        if len(set(self.predicates)) != len(self.predicates):
            raise ValueError('Select distinct relationship predicates')
        if self.algorithm in {'pagerank', 'triangle-count'} and self.node_id:
            raise ValueError('Global graph metrics do not accept a seed; select personalized PageRank for a seed')
        if self.algorithm not in {'pagerank', 'triangle-count'} and not self.node_id:
            raise ValueError('Select the seed business record')
        return self


def snapshot(publisher, request):
    """One transaction, exact publication, business-only endpoints and hard caps."""
    timeout = current_operation().timeout(15) if current_operation() else 15
    with publisher._driver() as driver, driver.session(database=publisher.database) as session:
        tx = session.begin_transaction(timeout=timeout)
        try:
            receipts = tx.run("MATCH (p:OntologyPublication {ontology_id:$scope}) WHERE p.current=true AND p.status='published' RETURN p.publication_id AS publication_id, properties(p)['artifact_sha256'] AS artifact_sha256", scope=request.ontology_id).data()
            if len(receipts) != 1 or receipts[0]['publication_id'] != request.publication_id:
                raise ValueError('Selected graph publication changed or is unavailable; select its current receipt')
            nodes = tx.run("MATCH (n) WHERE n.ontology_id=$scope AND " + business_instance_filter('n') + " RETURN elementId(n) AS id, coalesce(n.iri,n.uri,elementId(n)) AS iri, coalesce(n.name,n.label,'Unnamed record') AS name, labels(n) AS labels, n.rdf_types AS rdf_types ORDER BY id LIMIT 1001", scope=request.ontology_id).data()
            if not nodes: raise ValueError('No published business records in this scope')
            if len(nodes) > NODE_LIMIT: raise ValueError('Scope exceeds 1000 business records; choose a smaller published scope')
            ids = [row['id'] for row in nodes]
            if request.node_id and request.node_id not in ids: raise ValueError('Seed record is outside the selected published scope')
            edges = tx.run("MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids AND r.predicate IN $predicates RETURN DISTINCT elementId(a) AS source, elementId(b) AS target, r.predicate AS predicate ORDER BY source,target,predicate LIMIT 5001", ids=ids, predicates=request.predicates).data()
            if len(edges) > EDGE_LIMIT: raise ValueError('Scope exceeds 5000 selected relationships; narrow the predicates')
            tx.commit()
            return nodes, edges, receipts[0]
        except BaseException:
            tx.rollback()
            raise


def calculate(request, nodes, edges, receipt, ranked=None):
    graph = nx.DiGraph()
    graph.add_nodes_from(row['id'] for row in nodes)
    # Parallel predicates do not multiply influence; retain originals as evidence.
    graph.add_edges_from((e['source'], e['target']) for e in edges if e['source'] != e['target'])
    by_id = {row['id']: row for row in nodes}
    seed = request.node_id
    if request.algorithm in {'pagerank', 'personalized-pagerank'}:
        personalization = {node: float(node == seed) for node in graph} if seed else None
        scores = ({row['node_id']:row['score'] for row in ranked[0]} if ranked else nx.pagerank(graph, alpha=0.85, personalization=personalization, max_iter=100, tol=1e-8))
        results = [{'node_id': node, 'name': by_id[node]['name'], 'score': score} for node, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:request.top_n]]
        meaning = 'Directed structural relevance; not engineering criticality, confidence or approval'
    elif request.algorithm == 'triangle-count':
        # Structural closure only: direction is deliberately ignored for this
        # metric, while the retained evidence still contains directed edges.
        counts = nx.triangles(graph.to_undirected())
        results = [{'node_id': node, 'name': by_id[node]['name'], 'triangle_count': count}
                   for node, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:request.top_n]]
        meaning = 'Undirected structural triangle counts over selected predicates; not traceability completeness, requirement satisfaction or approval'
    elif request.algorithm == 'node-similarity':
        # Preserve predicate and direction: unrelated neighbor roles cannot match.
        features = {node: set() for node in graph}
        for edge in edges:
            features[edge['source']].add(('out', edge['predicate'], edge['target']))
            features[edge['target']].add(('in', edge['predicate'], edge['source']))
        scores = []
        for node in graph:
            if node == seed: continue
            shared = features[seed] & features[node]
            union = features[seed] | features[node]
            if shared:
                scores.append({'node_id': node, 'name': by_id[node]['name'], 'score': len(shared)/len(union), 'shared_features': [list(value) for value in sorted(shared)[:20]], 'shared_feature_count': len(shared)})
        results = sorted(scores, key=lambda row: (-row['score'], row['node_id']))[:request.top_n]
        meaning = 'Predicate- and direction-aware neighborhood Jaccard; not interchangeability'
    else:
        # An observed typed two-edge motif; no inferred satisfaction or missing-link verdict.
        adjacent = {node: [] for node in graph}
        for edge in edges:
            adjacent[edge['source']].append(edge)
            adjacent[edge['target']].append(edge)
        motifs = []
        for first in adjacent[seed]:
            middle = first['target'] if first['source'] == seed else first['source']
            for second in adjacent[middle]:
                end = second['target'] if second['source'] == middle else second['source']
                if end == seed or end == middle: continue
                sequence = [seed, middle, end]
                roles = [kind({'labels':by_id[node].get('labels',[]), 'properties':{'rdf_types':by_id[node].get('rdf_types',[])}}) for node in sequence]
                if 'unclassified' in roles: continue
                motifs.append({'nodes':[{'node_id':node,'name':by_id[node]['name'],'role':role} for node,role in zip(sequence,roles)],'edges':[first,second]})
                if len(motifs) > request.top_n: break
            if len(motifs) > request.top_n: break
        results = motifs[:request.top_n]
        meaning = 'Recorded typed two-edge paths; direction retained; no requirement satisfaction inferred'
    for row in results:
        if row.get('node_id') in by_id:
            record = by_id[row['node_id']]
            row['record_types'] = [value for value in (record.get('rdf_types') or record.get('labels') or [])
                                   if value != 'http://www.w3.org/2002/07/owl#NamedIndividual']
    result_limited = len(nodes)>request.top_n if request.algorithm in {'pagerank','personalized-pagerank','triangle-count'} else len(scores)>request.top_n if request.algorithm=='node-similarity' else len(motifs)>request.top_n
    canonical = {'request':request.model_dump(), 'nodes':nodes, 'edges':edges, 'publication':receipt}
    digest = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schema_version':TOOL_VERSION, 'ontology_id':request.ontology_id, 'publication_id':request.publication_id,
        'algorithm':request.algorithm, 'parameters':request.model_dump(), 'projection_digest':digest,
        'engine':ranked[1] if ranked else {'name':'networkx','version':nx.__version__}, 'computed_at':datetime.now(timezone.utc).isoformat(),
        'coverage':{'nodes':len(nodes),'edges':len(edges),'scope_complete':True,'whole_enterprise_complete':False,
                    'projection':'selected business records and predicates only'},
        'results':results, 'result_count':len(results), 'results_limited':result_limited, 'interpretation':meaning, 'advisory_only':True, 'approval_granted':False,
        'publication':receipt,
        **({'global_triangle_count':sum(counts.values()) // 3, 'orientation':'undirected'} if request.algorithm=='triangle-count' else {})}


def compute(publisher, request):
    with scoped_projection_access(request.ontology_id):
        nodes, edges, receipt = snapshot(publisher, request)
        ranked = None
        if request.algorithm in {'pagerank','personalized-pagerank'}:
            from .gds_computation import pagerank
            ranked = pagerank(publisher, request, nodes)
        result = calculate(request, nodes, edges, receipt, ranked=ranked)
        if current_operation(): current_operation().timeout(1)
        return result


def retain(result, store=None):
    """Immutable computation evidence; no graph scores or approval state are written."""
    from backend.mesh_store import PostgresRegistry
    store = store if store is not None else PostgresRegistry('graph_computation_evidence_v1')
    canonical = {key:value for key,value in result.items() if key != 'computed_at'}
    identity = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    record = {**result, 'evidence_id':identity, 'currentness':'retained snapshot; not revalidated on retrieval'}
    try: return store.create(identity,record)
    except FileExistsError:
        existing = store.get(identity)
        if not isinstance(existing,dict) or {key:value for key,value in existing.items() if key not in {'computed_at','evidence_id','currentness'}} != canonical:
            raise ValueError('Computation evidence identity conflict')
        return existing


def options(publisher, ontology_id=''):
    """Named, bounded selections for the UI; never accept a model-written query."""
    from contextlib import nullcontext
    with scoped_projection_access(ontology_id) if ontology_id else nullcontext():
        timeout = current_operation().timeout(15) if current_operation() else 15
        with publisher._driver() as driver, driver.session(database=publisher.database) as session:
            tx = session.begin_transaction(timeout=timeout)
            try:
                sources = tx.run("MATCH (p:OntologyPublication) WHERE p.current=true AND p.status='published' AND ($scope='' OR p.ontology_id=$scope) RETURN p.ontology_id AS ontology_id, p.publication_id AS publication_id, coalesce(p.ontology_name,p.name,p.prefix,p.ontology_id) AS name, p.published_at AS published_at ORDER BY name,ontology_id LIMIT 201", scope=ontology_id).data()
                if len(sources)>200: raise ValueError('More than 200 published scopes; select an exact ontology')
                if not ontology_id:
                    tx.commit()
                    return {'sources':sources}
                if len(sources)!=1: raise ValueError('Select one current published ontology scope')
                nodes = tx.run("MATCH (n) WHERE n.ontology_id=$scope AND " + business_instance_filter('n') + " RETURN elementId(n) AS node_id, coalesce(n.name,n.label,'Unnamed record') AS name, n.revision AS revision, n.rdf_types AS record_types ORDER BY name,node_id LIMIT 1001",scope=ontology_id).data()
                if len(nodes)>NODE_LIMIT: raise ValueError('Scope exceeds 1000 business records; select a smaller published scope')
                predicates = tx.run("MATCH (a)-[r]->(b) WHERE a.ontology_id=$scope AND b.ontology_id=$scope AND r.predicate IS NOT NULL AND " + business_instance_filter('a') + " AND " + business_instance_filter('b') + " RETURN DISTINCT r.predicate AS predicate ORDER BY predicate LIMIT 101",scope=ontology_id).data()
                tx.commit()
                return {'sources':sources,'nodes':nodes,'predicates':[row['predicate'] for row in predicates[:100]],'predicates_limited':len(predicates)>100}
            except BaseException:
                tx.rollback()
                raise
