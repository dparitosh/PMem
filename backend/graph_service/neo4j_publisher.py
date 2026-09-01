"""Minimal, direct Neo4j publisher with no dependency on the legacy graph proxy."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase
from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF, RDFS


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
        resources = [
            {"iri": iri, "label": labels.get(iri, iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]),
             "kind": "class" if iri in class_iris else "property" if iri in property_iris else "resource"}
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
        SET node.prefix = $prefix, node.label = row.label, node.kind = row.kind, node.updated_at = $updated_at
        """
        relation_queries = {
            "SUBCLASS_OF": "MERGE (source)-[edge:SUBCLASS_OF {ontology_id: $ontology_id}]->(target) SET edge.predicate = row.predicate",
            "DOMAIN": "MERGE (source)-[edge:DOMAIN {ontology_id: $ontology_id}]->(target) SET edge.predicate = row.predicate",
            "RANGE": "MERGE (source)-[edge:RANGE {ontology_id: $ontology_id}]->(target) SET edge.predicate = row.predicate",
            "SEMANTIC_RELATION": "MERGE (source)-[edge:SEMANTIC_RELATION {ontology_id: $ontology_id, predicate: row.predicate}]->(target)",
        }
        with GraphDatabase.driver(self.uri, auth=(self.username, self.password)) as driver:
            with driver.session(database=self.database) as session:
                session.run(resource_query, rows=resources, ontology_id=ontology_id, prefix=prefix, updated_at=now).consume()
                for relation_type, rows in relationships.items():
                    if not rows:
                        continue
                    query = f"""
                    UNWIND $rows AS row
                    MATCH (source:OntologyResource {{ontology_id: $ontology_id, iri: row.source}})
                    MATCH (target:OntologyResource {{ontology_id: $ontology_id, iri: row.target}})
                    {relation_queries[relation_type]}
                    """
                    session.run(query, rows=rows, ontology_id=ontology_id).consume()
        return {
            "status": "success", "ontology_id": ontology_id, "resources": len(resources),
            "relationships": sum(len(rows) for rows in relationships.values()),
            "hierarchy_edges": len(relationships["SUBCLASS_OF"]),
        }


publisher = Neo4jPublisher()
