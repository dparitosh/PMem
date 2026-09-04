"""Parameterized, read-only Cypher queries used by graph read surfaces."""
from __future__ import annotations


ONTOLOGY_PROJECTION_NODES = (
    "MATCH (n:OntologyResource {ontology_id: $ontology_id}) "
    "RETURN n.iri AS id, n.label AS label, n.kind AS type LIMIT $limit"
)
ONTOLOGY_PROJECTION_EDGES = (
    "MATCH (a:OntologyResource {ontology_id: $ontology_id})-[r]->(b:OntologyResource {ontology_id: $ontology_id}) "
    "RETURN a.iri AS source, b.iri AS target, type(r) AS type, coalesce(r.predicate, type(r)) AS predicate LIMIT $limit"
)
ONTOLOGY_TRAVERSAL_NODES = (
    "MATCH (root:OntologyResource {iri: $iri}) "
    "OPTIONAL MATCH path=(root)-[*0..5]-(neighbor:OntologyResource) "
    "WHERE length(path) <= $hops AND neighbor.ontology_id = root.ontology_id "
    "WITH root, collect(DISTINCT neighbor)[..$limit] AS neighbors "
    "UNWIND CASE WHEN size(neighbors) = 0 THEN [root] ELSE neighbors END AS node "
    "RETURN DISTINCT node.iri AS id, node.label AS label, node.kind AS type, node.ontology_id AS ontology_id"
)
ONTOLOGY_TRAVERSAL_EDGES = (
    "MATCH (a:OntologyResource)-[r]->(b:OntologyResource) "
    "WHERE a.iri IN $ids AND b.iri IN $ids AND a.ontology_id = b.ontology_id "
    "RETURN a.iri AS source, b.iri AS target, type(r) AS type LIMIT $limit"
)
ONTOLOGY_SEARCH_NODES = (
    "MATCH (n:OntologyResource) "
    "WITH n, reduce(score = 0, term IN $terms | score + CASE "
    "WHEN toLower(coalesce(n.label, '')) = term OR toLower(n.iri) ENDS WITH '/' + term OR toLower(n.iri) ENDS WITH '#' + term THEN 5 "
    "WHEN toLower(coalesce(n.label, '')) CONTAINS term OR toLower(n.iri) CONTAINS term THEN 1 ELSE 0 END) AS score "
    "WHERE score > 0 "
    "RETURN n.iri AS id, n.label AS label, n.kind AS type, n.ontology_id AS ontology_id, score "
    "ORDER BY score DESC, label LIMIT $limit"
)
