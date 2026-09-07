"""Minimal, direct Neo4j publisher with no dependency on the legacy graph proxy."""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
import re
from typing import Any

from neo4j import GraphDatabase
from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF, RDFS
from semantica.kg import GraphAnalyzer
from . import query_repository as cypher


class Neo4jPublisher:
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
        self.username = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASS", "")
        self.database = os.getenv("NEO4J_DATABASE", "ontology")

    def health(self) -> dict[str, Any]:
        if not self.password:
            return {"status": "not_configured", "database": self.database}
        try:
            with GraphDatabase.driver(self.uri, auth=(self.username, self.password)) as driver:
                driver.verify_connectivity()
            return {"status": "ok", "database": self.database}
        except Exception as exc:
            return {"status": "unavailable", "database": self.database, "detail": f"{type(exc).__name__}: {exc}"}

    def publish_turtle(self, *, content: bytes, ontology_id: str, prefix: str) -> dict[str, Any]:
        """Upsert an ontology's RDF resources and hierarchy into Neo4j.

        The model retains original RDF predicates and additionally promotes
        subclass/domain/range edges to stable graph relationship types for
        hierarchical exploration.  Repeating a publish is idempotent.
        """
        if not self.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        rdf_graph = Graph()
        rdf_graph.parse(data=content, format="turtle")
        labels = {str(subject): str(label) for subject, label in rdf_graph.subject_objects(RDFS.label)}
        class_iris = {str(subject) for subject in rdf_graph.subjects(RDF.type, OWL.Class)}
        property_iris = {
            str(subject) for subject in rdf_graph.subjects(RDF.type, OWL.ObjectProperty)
        } | {str(subject) for subject in rdf_graph.subjects(RDF.type, OWL.DatatypeProperty)}
        resource_iris = {str(value) for triple in rdf_graph for value in (triple[0], triple[2]) if not isinstance(value, Literal)}
        literal_properties: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for subject, predicate, value in rdf_graph:
            if isinstance(value, Literal):
                literal_properties.setdefault(str(subject), {}).setdefault(str(predicate), []).append({
                    "value": str(value), "datatype": str(value.datatype) if value.datatype else None,
                    "language": value.language,
                })
        resources = [
            {"iri": iri, "label": labels.get(iri, iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]),
             "kind": "class" if iri in class_iris else "property" if iri in property_iris else "resource",
             "rdf_properties": json.dumps(literal_properties.get(iri, {}), sort_keys=True)}
            for iri in resource_iris
        ]
        relationships: dict[str, list[dict[str, str]]] = {"SUBCLASS_OF": [], "DOMAIN": [], "RANGE": [], "SEMANTIC_RELATION": []}
        special_predicates = {str(RDFS.subClassOf): "SUBCLASS_OF", str(RDFS.domain): "DOMAIN", str(RDFS.range): "RANGE"}
        for subject, predicate, obj in rdf_graph:
            if isinstance(obj, Literal):
                continue
            relation_type = special_predicates.get(str(predicate), "SEMANTIC_RELATION")
            relationships[relation_type].append({"source": str(subject), "target": str(obj), "predicate": str(predicate)})

        now = datetime.now(timezone.utc).isoformat()
        resource_query = """
        UNWIND $rows AS row
        MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})
        SET node.prefix = $prefix, node.label = row.label, node.kind = row.kind,
            node.rdf_properties = row.rdf_properties, node.updated_at = $updated_at
        """
        relation_queries = {
            "SUBCLASS_OF": "MERGE (source)-[edge:SUBCLASS_OF {ontology_id: $ontology_id}]->(target) SET edge.predicate = row.predicate",
            "DOMAIN": "MERGE (source)-[edge:DOMAIN {ontology_id: $ontology_id}]->(target) SET edge.predicate = row.predicate",
            "RANGE": "MERGE (source)-[edge:RANGE {ontology_id: $ontology_id}]->(target) SET edge.predicate = row.predicate",
            "SEMANTIC_RELATION": "MERGE (source)-[edge:SEMANTIC_RELATION {ontology_id: $ontology_id, predicate: row.predicate}]->(target)",
        }
        def publish_transaction(tx):
            tx.run(resource_query, rows=resources, ontology_id=ontology_id, prefix=prefix, updated_at=now).consume()
            for relation_type, rows in relationships.items():
                if not rows:
                    continue
                query = f"""
                UNWIND $rows AS row
                MATCH (source:OntologyResource {{ontology_id: $ontology_id, iri: row.source}})
                MATCH (target:OntologyResource {{ontology_id: $ontology_id, iri: row.target}})
                {relation_queries[relation_type]}
                """
                tx.run(query, rows=rows, ontology_id=ontology_id).consume()

        with GraphDatabase.driver(self.uri, auth=(self.username, self.password)) as driver:
            with driver.session(database=self.database) as session:
                session.execute_write(publish_transaction)
        return {
            "status": "success", "ontology_id": ontology_id, "resources": len(resources),
            "relationships": sum(len(rows) for rows in relationships.values()),
            "hierarchy_edges": len(relationships["SUBCLASS_OF"]),
        }

    def _session_rows(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        if not self.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        with GraphDatabase.driver(self.uri, auth=(self.username, self.password)) as driver:
            with driver.session(database=self.database) as session:
                return session.run(query, parameters).data()

    def projection(self, *, ontology_id: str, limit: int = 3000) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 10_000))
        nodes = self._session_rows(
            cypher.ONTOLOGY_PROJECTION_NODES,
            ontology_id=ontology_id, limit=safe_limit,
        )
        edges = self._session_rows(
            cypher.ONTOLOGY_PROJECTION_EDGES,
            ontology_id=ontology_id, limit=safe_limit * 4,
        )
        return {"nodes": nodes, "edges": edges, "ontology_id": ontology_id, "truncated": len(nodes) >= safe_limit}

    @staticmethod
    def _explorer_payload(*, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], view: dict[str, Any]) -> dict[str, Any]:
        """Adapt Neo4j projection rows to the stable Graph Explorer contract.

        The browser deliberately receives one shape regardless of graph-store
        provider.  Keeping this adapter in the graph service avoids the old
        port-8000 proxy and lets an API gateway expose this endpoint directly.
        """
        explorer_nodes = [
            {
                "elementId": str(node["id"]),
                "labels": [str(node.get("type") or "resource")],
                "properties": {
                    "iri": str(node["id"]),
                    "label": str(node.get("label") or node["id"]),
                    "kind": str(node.get("type") or "resource"),
                    **({"ontology_id": node["ontology_id"]} if node.get("ontology_id") else {}),
                    **({"search_score": int(node["score"])} if node.get("score") is not None else {}),
                },
                "can_traverse": True,
            }
            for node in nodes
        ]
        explorer_edges = [
            {
                "elementId": f"{edge['source']}::{edge.get('type') or 'RELATED_TO'}::{edge['target']}",
                "start": str(edge["source"]),
                "end": str(edge["target"]),
                "type": str(edge.get("type") or "RELATED_TO"),
                "properties": {"raw_type": str(edge.get("type") or "RELATED_TO")},
            }
            for edge in edges
        ]
        return {
            "nodes": explorer_nodes,
            "relationships": explorer_edges,
            "counts": {"nodes": len(explorer_nodes), "relationships": len(explorer_edges)},
            "view": view,
        }

    def overview(self, *, limit: int = 900) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 10_000))
        nodes = self._session_rows(
            "MATCH (n:OntologyResource) RETURN n.iri AS id, n.label AS label, n.kind AS type, n.ontology_id AS ontology_id "
            "ORDER BY n.ontology_id, n.label LIMIT $limit",
            limit=safe_limit,
        )
        # Existing ontologies created before the standalone graph service use
        # the domain labels below.  Read them directly when no published
        # OntologyResource projection exists; this is intentionally read-only
        # and avoids forcing a destructive graph migration merely to browse an
        # already-ingested ontology.
        if not nodes:
            return self._legacy_overview(limit=safe_limit)
        edges = self._session_rows(
            "MATCH (a:OntologyResource)-[r]->(b:OntologyResource) "
            "WHERE a.ontology_id = b.ontology_id "
            "RETURN a.iri AS source, b.iri AS target, type(r) AS type LIMIT $limit",
            limit=safe_limit * 4,
        )
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "overview", "limit": safe_limit, "truncated": len(nodes) >= safe_limit},
        )

    def search(self, *, query: str, limit: int = 50) -> dict[str, Any]:
        stop_words = {"and", "the", "for", "from", "show", "with", "relationship", "relationships"}
        terms = sorted({token for token in re.findall(r"[a-z0-9]+", str(query).lower()) if len(token) >= 3 and token not in stop_words})
        if not terms:
            raise ValueError("query must contain at least one searchable term")
        safe_limit = max(1, min(int(limit), 200))
        nodes = self._session_rows(cypher.ONTOLOGY_SEARCH_NODES, terms=terms, limit=safe_limit)
        ids = [node["id"] for node in nodes]
        edges = [] if not ids else self._session_rows(cypher.ONTOLOGY_TRAVERSAL_EDGES, ids=ids, limit=safe_limit * 4)
        return self._explorer_payload(
            nodes=nodes, edges=edges,
            view={"type": "search", "query": query, "terms": terms, "limit": safe_limit, "truncated": len(nodes) >= safe_limit},
        )

    def _legacy_overview(self, *, limit: int) -> dict[str, Any]:
        nodes = self._session_rows(
            "MATCH (n) WHERE n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty "
            "RETURN elementId(n) AS id, coalesce(n.name, n.label, n.uri) AS label, "
            "coalesce(n.concept_type, head(labels(n)), 'resource') AS type, "
            "n.source_ontology AS ontology_id "
            "ORDER BY coalesce(n.name, n.label, n.uri) LIMIT $limit",
            limit=limit,
        )
        ids = [node["id"] for node in nodes]
        edges = [] if not ids else self._session_rows(
            "MATCH (a)-[r]->(b) "
            "WHERE elementId(a) IN $ids AND elementId(b) IN $ids "
            "RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type LIMIT $limit",
            ids=ids, limit=limit * 4,
        )
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "overview", "source": "existing_ontology", "limit": limit, "truncated": len(nodes) >= limit},
        )

    def explorer_projection(self, *, ontology_id: str, limit: int = 900) -> dict[str, Any]:
        projection = self.projection(ontology_id=ontology_id, limit=limit)
        return self._explorer_payload(
            nodes=projection["nodes"],
            edges=projection["edges"],
            view={"type": "ontology", "ontology_id": ontology_id, "limit": min(max(int(limit), 1), 10_000), "truncated": projection["truncated"]},
        )

    def traversal(self, *, iri: str, depth: int = 1, limit: int = 200) -> dict[str, Any]:
        hops, safe_limit = max(1, min(int(depth), 5)), max(1, min(int(limit), 1_000))
        nodes = self._session_rows(
            cypher.ONTOLOGY_TRAVERSAL_NODES,
            iri=iri, hops=hops, limit=safe_limit,
        )
        if not nodes:
            return self._legacy_traversal(node_id=iri, depth=hops, limit=safe_limit)
        ids = [node["id"] for node in nodes]
        edges = [] if not ids else self._session_rows(
            cypher.ONTOLOGY_TRAVERSAL_EDGES,
            ids=ids, limit=safe_limit * 4,
        )
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "traversal", "root_node_id": iri, "depth": hops, "limit": safe_limit},
        )

    def _legacy_traversal(self, *, node_id: str, depth: int, limit: int) -> dict[str, Any]:
        nodes = self._session_rows(
            "MATCH (root) WHERE elementId(root) = $node_id "
            "OPTIONAL MATCH path=(root)-[*0..5]-(neighbor) "
            "WHERE length(path) <= $depth "
            "WITH root, collect(DISTINCT neighbor)[..$limit] AS neighbors "
            "UNWIND CASE WHEN size(neighbors) = 0 THEN [root] ELSE neighbors END AS node "
            "RETURN DISTINCT elementId(node) AS id, coalesce(node.name, node.label, node.uri) AS label, "
            "coalesce(node.concept_type, head(labels(node)), 'resource') AS type, node.source_ontology AS ontology_id",
            node_id=node_id, depth=depth, limit=limit,
        )
        ids = [node["id"] for node in nodes]
        edges = [] if not ids else self._session_rows(
            "MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids AND elementId(b) IN $ids "
            "RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type LIMIT $limit",
            ids=ids, limit=limit * 4,
        )
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "traversal", "source": "existing_ontology", "root_node_id": node_id, "depth": depth, "limit": limit},
        )

    def analytics(self, *, ontology_id: str, limit: int = 3000) -> dict[str, Any]:
        projection = self.projection(ontology_id=ontology_id, limit=limit)
        return {"ontology_id": ontology_id, "projection": projection, "analytics": GraphAnalyzer().analyze_graph(projection)}

    def neighborhood(self, *, ontology_id: str, iri: str, max_hops: int = 3, limit: int = 200) -> dict[str, Any]:
        hops, safe_limit = max(1, min(int(max_hops), 5)), max(1, min(int(limit), 1000))
        rows = self._session_rows(
            "MATCH (root:OntologyResource {ontology_id: $ontology_id, iri: $iri}) "
            "MATCH path=(root)-[*1..5]-(neighbor:OntologyResource {ontology_id: $ontology_id}) "
            "WHERE length(path) <= $hops "
            "RETURN neighbor.iri AS iri, neighbor.label AS label, neighbor.kind AS kind, min(length(path)) AS distance "
            "ORDER BY distance, label LIMIT $limit",
            ontology_id=ontology_id, iri=iri, hops=hops, limit=safe_limit,
        )
        return {"ontology_id": ontology_id, "anchor": iri, "max_hops": hops, "neighbors": rows}


publisher = Neo4jPublisher()
