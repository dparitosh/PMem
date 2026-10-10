"""Parameterized, read-only Cypher queries used by graph read surfaces."""
from __future__ import annotations

# Older ingestion writes typed nodes directly, without an OntologyResource
# projection. Keep its counts distinct from explicit RDF declarations.
LEGACY_NODE_FILTER = "(n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty OR n:AnnotationProperty OR n:NamedIndividual) AND NOT n:OntologyResource"
LEGACY_SCOPE_FILTER = "($ontology_id = '' OR n.ontology_id = $ontology_id OR n.source_ontology = $ontology_id OR ($ontology_prefix <> '' AND (n.prefix = $ontology_prefix OR n.source_ontology = $ontology_prefix)))"
LEGACY_METRICS = (
    "CALL { MATCH (n) WHERE " + LEGACY_NODE_FILTER + " AND " + LEGACY_SCOPE_FILTER + " "
    "RETURN count(n) AS resources, "
    "sum(CASE WHEN n:OntologyClass THEN 1 ELSE 0 END) AS classes, "
    "sum(CASE WHEN n:ObjectProperty THEN 1 ELSE 0 END) AS object_properties, "
    "sum(CASE WHEN n:DatatypeProperty THEN 1 ELSE 0 END) AS data_properties, "
    "sum(CASE WHEN n:AnnotationProperty THEN 1 ELSE 0 END) AS annotation_properties, "
    "sum(CASE WHEN n:NamedIndividual THEN 1 ELSE 0 END) AS named_individuals } "
    "CALL { MATCH (n)-[r]->(b) WHERE " + LEGACY_NODE_FILTER + " AND " + LEGACY_SCOPE_FILTER + " AND "
    + LEGACY_NODE_FILTER.replace('n:', 'b:') + " AND "
    + LEGACY_SCOPE_FILTER.replace('n.', 'b.') + " RETURN count(r) AS relationships } "
    "RETURN resources, classes, object_properties, data_properties, annotation_properties, named_individuals, relationships"
)
LEGACY_SEARCH = (
    "MATCH (n) WHERE " + LEGACY_NODE_FILTER + " AND " + LEGACY_SCOPE_FILTER + " "
    "WITH n, coalesce(n.name, n.label, n.uri, n.iri, '') AS label, "
    "coalesce(n.uri, n.iri, '') AS iri "
    "WITH n, label, reduce(score = 0, term IN $terms | score + CASE "
    "WHEN toLower(label) = term THEN 5 "
    "WHEN toLower(label) CONTAINS term OR toLower(iri) CONTAINS term THEN 1 ELSE 0 END) AS score "
    "WHERE score > 0 RETURN elementId(n) AS id, label, "
    "coalesce(n.concept_type, head(labels(n)), 'resource') AS type, "
    "coalesce(n.ontology_id, n.source_ontology, n.prefix) AS ontology_id, score "
    "ORDER BY score DESC, label LIMIT $limit"
)
LEGACY_OVERVIEW = (
    'MATCH (n) WHERE ' + LEGACY_NODE_FILTER + ' '
    'RETURN elementId(n) AS id, coalesce(n.name, n.label, n.uri, n.iri) AS label, '
    "coalesce(n.concept_type, head(labels(n)), 'resource') AS type, "
    'coalesce(n.ontology_id, n.source_ontology, n.prefix) AS ontology_id '
    'ORDER BY label LIMIT $limit'
)
LEGACY_EDGES = (
    'MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids '
    'RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type, elementId(r) AS edge_id, r.predicate AS predicate LIMIT $limit'
)
LEGACY_TRAVERSAL_NODES = (
    'MATCH (root) WHERE elementId(root) = $node_id AND '
    + LEGACY_NODE_FILTER.replace('n:', 'root:') + ' '
    'OPTIONAL MATCH path=(root)-[*0..5]-(neighbor) '
    'WHERE length(path) <= $depth AND all(n IN nodes(path) WHERE '
    + LEGACY_NODE_FILTER + ' AND '
    'coalesce(n.ontology_id, n.source_ontology, n.prefix) = coalesce(root.ontology_id, root.source_ontology, root.prefix)) '
    'WITH root, neighbor ORDER BY elementId(neighbor) '
    'WITH root, collect(DISTINCT neighbor) AS neighbors '
    'UNWIND [root] + [n IN neighbors WHERE n <> root][..($limit - 1)] AS node '
    'RETURN DISTINCT elementId(node) AS id, coalesce(node.name, node.label, node.uri, node.iri) AS label, '
    "coalesce(node.concept_type, head(labels(node)), 'resource') AS type, "
    'coalesce(node.ontology_id, node.source_ontology, node.prefix) AS ontology_id'
)


ONTOLOGY_PROJECTION_NODES = (
    "MATCH (n:OntologyResource {ontology_id: $ontology_id}) "
    "RETURN n.iri AS id, elementId(n) AS graph_id, n.label AS label, n.kind AS type LIMIT $limit"
)
ONTOLOGY_PROJECTION_EDGES = (
    "MATCH (a:OntologyResource {ontology_id: $ontology_id})-[r]->(b:OntologyResource {ontology_id: $ontology_id}) "
    "WHERE a.iri IN $ids AND b.iri IN $ids RETURN a.iri AS source, b.iri AS target, elementId(a) AS graph_source, elementId(b) AS graph_target, type(r) AS type, elementId(r) AS edge_id, coalesce(r.predicate, type(r)) AS predicate LIMIT $limit"
)
ONTOLOGY_TRAVERSAL_NODES = (
    "MATCH (root:OntologyResource) WHERE elementId(root) = $iri OR root.iri = $iri "
    "OPTIONAL MATCH path=(root)-[*0..5]-(neighbor:OntologyResource) "
    "WHERE length(path) <= $hops AND all(n IN nodes(path) WHERE n:OntologyResource AND n.ontology_id = root.ontology_id) "
    "WITH root, neighbor ORDER BY neighbor.iri "
    "WITH root, collect(DISTINCT neighbor) AS neighbors "
    "UNWIND [root] + [n IN neighbors WHERE n <> root][..($limit - 1)] AS node "
    "RETURN DISTINCT elementId(node) AS id, node.iri AS iri, node.label AS label, node.kind AS type, node.ontology_id AS ontology_id"
)
ONTOLOGY_TRAVERSAL_EDGES = (
    "MATCH (a:OntologyResource)-[r]->(b:OntologyResource) "
    "WHERE elementId(a) IN $ids AND elementId(b) IN $ids AND a.ontology_id = b.ontology_id "
    "RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type, elementId(r) AS edge_id, r.predicate AS predicate LIMIT $limit"
)
ONTOLOGY_SEARCH_NODES = (
    "MATCH (n:OntologyResource) "
    "WHERE $ontology_id = '' OR n.ontology_id = $ontology_id "
    "WITH n, reduce(score = 0, term IN $terms | score + CASE "
    "WHEN toLower(coalesce(n.label, '')) = term OR toLower(n.iri) ENDS WITH '/' + term OR toLower(n.iri) ENDS WITH '#' + term THEN 5 "
    "WHEN toLower(coalesce(n.label, '')) CONTAINS term OR toLower(n.iri) CONTAINS term THEN 1 ELSE 0 END) AS score "
    "WHERE score > 0 "
    "RETURN elementId(n) AS id, n.iri AS iri, n.label AS label, n.kind AS type, n.ontology_id AS ontology_id, score "
    "ORDER BY score DESC, label LIMIT $limit"
)


# Complete bounded mapping targets; executed only by the Graph data service.
MAPPING_TERMS = """UNWIND $kinds AS kind
            MATCH (n) WHERE (n.prefix IN $scopes OR n.ontology_prefix IN $scopes
                OR n.ontology_id IN $scopes OR n.source_ontology IN $scopes)
            AND ((kind.kind='Class' AND n:OntologyClass)
                OR (kind.kind='ObjectProperty' AND n:ObjectProperty)
                OR (kind.kind='DatatypeProperty' AND n:DatatypeProperty)
                OR (kind.kind='AnnotationProperty' AND n:AnnotationProperty)
                OR (n:OntologyResource AND EXISTS {
                    MATCH (n)-[r:SEMANTIC_RELATION]->(t:OntologyResource)
                    WHERE r.predicate=$rdf_type AND t.iri=kind.iri }))
            OPTIONAL MATCH (n)-[:DOMAIN]->(domain)
            OPTIONAL MATCH (n)-[:RANGE]->(range)
            RETURN elementId(n) AS element_id, coalesce(n.name,n.label,n.iri,n.uri) AS name,
                coalesce(n.iri,n.uri) AS iri, kind.kind AS kind,
                collect(DISTINCT coalesce(domain.iri,domain.uri,domain.name)) AS domains,
                collect(DISTINCT coalesce(range.iri,range.uri,range.name)) AS ranges
            ORDER BY element_id, kind LIMIT 10001"""
