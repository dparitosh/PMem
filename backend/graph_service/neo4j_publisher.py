"""Minimal, direct Neo4j publisher with no dependency on the legacy graph proxy."""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
import re
from typing import Any

from neo4j import GraphDatabase, Query
from rdflib import Graph, Literal
from rdflib.compare import to_canonical_graph
from rdflib.namespace import OWL, RDF, RDFS
from semantica.kg import GraphAnalyzer
from . import query_repository as cypher


class Neo4jPublisher:
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL", "neo4j://127.0.0.1:7687")
        self.username = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD", "")
        self.auth_mode = os.getenv("NEO4J_AUTH_MODE", "token").strip().lower()
        self.database = os.getenv("NEO4J_DATABASE", "ontology")

    def _driver(self):
        if self.auth_mode not in {"token", "none"}:
            raise RuntimeError("NEO4J_AUTH_MODE must be token or none")
        auth = None if self.auth_mode == "none" else (self.username, self.password)
        return GraphDatabase.driver(self.uri, auth=auth, connection_timeout=10, max_transaction_retry_time=0)

    def health(self) -> dict[str, Any]:
        if self.auth_mode != "none" and not self.password:
            return {"status": "not_configured", "database": self.database}
        try:
            with self._driver() as driver:
                driver.verify_connectivity()
                with driver.session(database=self.database) as session:
                    session.run(Query("RETURN 1", timeout=3)).consume()
            return {"status": "ok", "database": self.database}
        except Exception as exc:
            return {"status": "unavailable", "database": self.database, "detail": f"{type(exc).__name__}: {exc}"}

    def publish_turtle(self, *, content: bytes, ontology_id: str, prefix: str, publication_id: str | None = None) -> dict[str, Any]:
        """Upsert an ontology's RDF resources and hierarchy into Neo4j.

        The model retains original RDF predicates and additionally promotes
        subclass/domain/range edges to stable graph relationship types for
        hierarchical exploration.  Repeating a publish is idempotent.
        """
        if self.auth_mode != "none" and not self.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        rdf_graph = Graph()
        rdf_graph.parse(data=content, format="turtle")
        rdf_graph = to_canonical_graph(rdf_graph)
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
        ceim_relationships = {
            "hasPart": "HAS_PART", "hasGeometry": "HAS_GEOMETRY", "hasFeature": "HAS_FEATURE",
            "hasCharacteristic": "HAS_CHARACTERISTIC", "usesDatum": "USES_DATUM",
            "usesReferenceFrame": "USES_REFERENCE_FRAME", "realizes": "REALIZES",
            "satisfies": "SATISFIES", "traceTo": "TRACE_TO", "derivedFrom": "DERIVED_FROM",
            "verifiedBy": "VERIFIED_BY", "validatedBy": "VALIDATED_BY", "impacts": "IMPACTS",
            "produces": "PRODUCES", "consumes": "CONSUMES",
        }
        relationships: dict[str, list[dict[str, str]]] = {
            "SUBCLASS_OF": [], "DOMAIN": [], "RANGE": [], "SEMANTIC_RELATION": [],
        }
        relationships.update({relationship: [] for relationship in ceim_relationships.values()})
        # Preserve arbitrary RDF predicates as SEMANTIC_RELATION, but promote
        # CEIM containment and engineering-structure links for graph traversal.
        ceim = "https://depo.example.org/ceim/0.1/"
        special_predicates = {
            str(RDFS.subClassOf): "SUBCLASS_OF", str(RDFS.domain): "DOMAIN", str(RDFS.range): "RANGE",
            **{f"{ceim}{predicate}": relationship for predicate, relationship in ceim_relationships.items()},
        }
        for subject, predicate, obj in rdf_graph:
            if isinstance(obj, Literal):
                continue
            relation_type = special_predicates.get(str(predicate), "SEMANTIC_RELATION")
            relationships[relation_type].append({"source": str(subject), "target": str(obj), "predicate": str(predicate)})

        now = datetime.now(timezone.utc).isoformat()
        publication_id = str(publication_id or "").strip() or None
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
        relation_queries.update({
            relationship: f"MERGE (source)-[edge:{relationship} {{ontology_id: $ontology_id}}]->(target) SET edge.predicate = row.predicate"
            for relationship in ceim_relationships.values()
        })
        def publish_transaction(tx):
            # The permanent, uniquely constrained receipt key serializes writers.
            tx.run("MERGE (lock:OntologyPublication {ontology_id: $ontology_id, publication_id: '__lock__'}) SET lock.publication_lock = $updated_at",
                   ontology_id=ontology_id, updated_at=now).consume()
            tx.run("MATCH (a:OntologyResource {ontology_id: $ontology_id})-[edge]->(b:OntologyResource {ontology_id: $ontology_id}) WHERE edge.ontology_id = $ontology_id AND type(edge) IN $types DELETE edge",
                   ontology_id=ontology_id, types=list(relationships)).consume()
            tx.run("MATCH (node:RetainedOntologyIdentity {ontology_id: $ontology_id}) WHERE node.iri IN $iris SET node:OntologyResource REMOVE node:RetainedOntologyIdentity",
                   ontology_id=ontology_id, iris=list(resource_iris)).consume()
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
            # Keep externally referenced identities, but remove their projection
            # label so stale records cannot inflate RDF metrics or search.
            tx.run("MATCH (node:OntologyResource {ontology_id: $ontology_id}) WHERE NOT node.iri IN $iris REMOVE node:OntologyResource SET node:RetainedOntologyIdentity",
                   ontology_id=ontology_id, iris=list(resource_iris)).consume()
            tx.run("MATCH (node:RetainedOntologyIdentity {ontology_id: $ontology_id}) WHERE NOT (node)--() DELETE node",
                   ontology_id=ontology_id).consume()
            tx.run("MATCH (node:OntologyResource {ontology_id: $ontology_id}) REMOVE node:RetainedOntologyIdentity",
                   ontology_id=ontology_id).consume()
            tx.run("MATCH (receipt:OntologyPublication {ontology_id: $ontology_id}) SET receipt.current = false",
                   ontology_id=ontology_id).consume()
            if publication_id:
                tx.run(
                    """
                    MERGE (receipt:OntologyPublication {ontology_id: $ontology_id, publication_id: $publication_id})
                    ON CREATE SET receipt.published_at = $published_at
                    SET receipt.prefix = $prefix, receipt.resources = $resources,
                        receipt.relationships = $relationships, receipt.hierarchy_edges = $hierarchy_edges,
                        receipt.status = 'published', receipt.current = true
                    """,
                    ontology_id=ontology_id, publication_id=publication_id, prefix=prefix,
                    resources=len(resources), relationships=sum(len(rows) for rows in relationships.values()),
                    hierarchy_edges=len(relationships["SUBCLASS_OF"]) + len(relationships["HAS_PART"]),
                    published_at=now,
                ).consume()

        with self._driver() as driver:
            with driver.session(database=self.database) as session:
                session.execute_write(publish_transaction)
        return {
            "status": "success", "ontology_id": ontology_id, "resources": len(resources),
            "relationships": sum(len(rows) for rows in relationships.values()),
            "hierarchy_edges": len(relationships["SUBCLASS_OF"]) + len(relationships["HAS_PART"]),
            "publication_id": publication_id,
        }

    def publication_receipt(self, *, ontology_id: str, publication_id: str) -> dict[str, Any] | None:
        rows = self._session_rows(
            """
            MATCH (receipt:OntologyPublication {ontology_id: $ontology_id, publication_id: $publication_id})
            RETURN receipt { .ontology_id, .publication_id, .prefix, .resources, .relationships,
                             .hierarchy_edges, .status, .published_at, .current } AS receipt
            """,
            ontology_id=ontology_id, publication_id=publication_id,
        )
        return dict(rows[0]["receipt"]) if rows else None

    def _session_rows(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        if self.auth_mode != "none" and not self.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        with self._driver() as driver:
            with driver.session(database=self.database) as session:
                from backend.depo_platform.network import bounded_timeout_seconds
                timeout = bounded_timeout_seconds("GRAPH_QUERY_TIMEOUT_SECONDS", default=30, maximum=300)
                return session.run(Query(query, timeout=timeout), parameters).data()

    def mapping_terms(self, scope: str) -> dict[str, Any]:
        if not isinstance(scope, str) or not scope.strip() or len(scope) > 256:
            raise ValueError('Select a valid ontology scope.')
        scopes = {scope, scope.lower()}
        if 'ap242' in scope.lower() or scope.lower() == 'step':
            scopes.update({'ap242', 'step_ap242_mbd3d', 'AP242', 'STEP_AP242_MBD3D'})
        kinds = [{'kind': kind, 'iri': 'http://www.w3.org/2002/07/owl#' + kind}
                 for kind in ('Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty')]
        rows = self._session_rows(cypher.MAPPING_TERMS, scopes=sorted(scopes), kinds=kinds,
                                  rdf_type='http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
        if len(rows) > 10000:
            raise ValueError('Ontology mapping lookup exceeds 10000 terms; narrow the ontology scope.')
        return {'scope': scope, 'terms': rows}

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

    def metrics(self, *, ontology_id: str = '', ontology_prefix: str = '') -> dict[str, Any]:
        """Aggregate the published RDF projection, never an explorer sample."""
        ontology_id = ontology_id.strip()
        if len(ontology_id) > 128:
            raise ValueError('ontology_id must contain at most 128 characters')
        ontology_prefix = ontology_prefix.strip()
        if len(ontology_prefix) > 128:
            raise ValueError('ontology_prefix must contain at most 128 characters')
        query = """
        CALL {
          MATCH (n:OntologyResource)
          WHERE $ontology_id = '' OR n.ontology_id = $ontology_id
          RETURN count(n) AS resources,
            sum(CASE WHEN EXISTS { MATCH (n)-[r]->(t:OntologyResource)
              WHERE r.predicate = $rdf_type AND t.iri IN $class_types } THEN 1 ELSE 0 END) AS classes,
            sum(CASE WHEN EXISTS { MATCH (n)-[r]->(t:OntologyResource)
              WHERE r.predicate = $rdf_type AND t.iri = $object_property } THEN 1 ELSE 0 END) AS object_properties,
            sum(CASE WHEN EXISTS { MATCH (n)-[r]->(t:OntologyResource)
              WHERE r.predicate = $rdf_type AND t.iri = $data_property } THEN 1 ELSE 0 END) AS data_properties,
            sum(CASE WHEN EXISTS { MATCH (n)-[r]->(t:OntologyResource)
              WHERE r.predicate = $rdf_type AND t.iri = $annotation_property } THEN 1 ELSE 0 END) AS annotation_properties,
            sum(CASE WHEN EXISTS { MATCH (n)-[r]->(t:OntologyResource)
              WHERE r.predicate = $rdf_type AND t.iri = $individual } THEN 1 ELSE 0 END) AS named_individuals
        }
        CALL {
          MATCH (a:OntologyResource)-[r]->(b:OntologyResource)
          WHERE ($ontology_id = '' OR a.ontology_id = $ontology_id)
            AND a.ontology_id = b.ontology_id
          RETURN count(r) AS relationships
        }
        CALL {
          MATCH (n:OntologyResource)
          WHERE $ontology_id = '' OR n.ontology_id = $ontology_id
          WITH n.ontology_id AS ontology, count(n) AS node_count
          ORDER BY node_count DESC, ontology LIMIT 201
          RETURN collect({ontology: ontology, node_count: node_count}) AS ontology_breakdown
        }
        RETURN resources, relationships, classes, object_properties, data_properties,
               annotation_properties, named_individuals, ontology_breakdown
        """
        rows = self._session_rows(query, ontology_id=ontology_id, rdf_type=str(RDF.type),
            class_types=[str(OWL.Class), str(RDFS.Class)], object_property=str(OWL.ObjectProperty),
            data_property=str(OWL.DatatypeProperty), annotation_property=str(OWL.AnnotationProperty), individual=str(OWL.NamedIndividual))
        if not rows:
            raise RuntimeError('Graph metrics query returned no aggregate result')
        result = dict(rows[0])
        breakdown = result.get('ontology_breakdown') or []
        result['ontology_breakdown'] = breakdown[:200]
        result['breakdown_truncated'] = len(breakdown) > 200
        legacy = self._session_rows(cypher.LEGACY_METRICS, ontology_id=ontology_id, ontology_prefix=ontology_prefix)
        if not legacy:
            raise RuntimeError('Existing ontology metrics query returned no aggregate result')
        result['existing_ontology'] = {**legacy[0], 'definition': 'Existing ingestion records counted by Neo4j labels. These are separate from declared RDF types in the published projection.'}
        return {**result, 'scope': {'type': 'published_rdf_projection', 'ontology_id': ontology_id or None,
            'sampled': False, 'inferred': False},
            'definition': 'Declared RDF/OWL types in the published projection. Named individuals count explicit owl:NamedIndividual declarations. Resources include referenced vocabulary and blank nodes; literal values are stored as properties, not relationship edges.'}

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

    def search(self, *, query: str, limit: int = 50, ontology_id: str = '', ontology_prefix: str = '') -> dict[str, Any]:
        stop_words = {"and", "the", "for", "from", "show", "with", "relationship", "relationships"}
        terms = sorted({token for token in re.findall(r"[a-z0-9]+", str(query).lower()) if len(token) >= 3 and token not in stop_words})
        if not terms:
            raise ValueError("query must contain at least one searchable term")
        safe_limit = max(1, min(int(limit), 200))
        if len(ontology_id) > 128:
            raise ValueError('ontology_id must be at most 128 characters')
        if len(ontology_prefix) > 128:
            raise ValueError('ontology_prefix must be at most 128 characters')
        nodes = self._session_rows(cypher.ONTOLOGY_SEARCH_NODES, terms=terms, limit=safe_limit, ontology_id=ontology_id)
        legacy = self._session_rows(cypher.LEGACY_SEARCH, terms=terms, limit=safe_limit, ontology_id=ontology_id, ontology_prefix=ontology_prefix)
        combined = sorted(nodes + legacy, key=lambda node: (-int(node.get('score') or 0), str(node.get('label') or '')))
        selected = combined[:safe_limit]
        # Read edges after ranking so excluded candidates cannot consume the
        # relationship budget of the resources actually returned to chat.
        selected_ids = {node['id'] for node in selected}
        edges = self._read_edges([node['id'] for node in nodes if node['id'] in selected_ids], limit=safe_limit * 4)
        edges += self._read_edges([node['id'] for node in legacy if node['id'] in selected_ids], limit=safe_limit * 4, existing=True)
        edges = edges[:safe_limit * 4]
        return self._explorer_payload(
            nodes=selected, edges=edges,
            view={"type": "search", "query": query, "terms": terms, "ontology_id": ontology_id, "limit": safe_limit, "truncated": len(combined) >= safe_limit, "source": "published_and_existing_ontology"},
        )

    def _legacy_overview(self, *, limit: int) -> dict[str, Any]:
        nodes = self._session_rows(cypher.LEGACY_OVERVIEW, limit=limit)
        ids = [node["id"] for node in nodes]
        edges = self._read_edges(ids, limit=limit * 4, existing=True)
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "overview", "source": "existing_ontology", "limit": limit, "truncated": len(nodes) >= limit},
        )

    def _read_edges(self, ids: list[str], *, limit: int, existing: bool = False) -> list[dict[str, Any]]:
        if not ids:
            return []
        return self._session_rows(cypher.LEGACY_EDGES if existing else cypher.ONTOLOGY_TRAVERSAL_EDGES,
                                  ids=ids, limit=limit)

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
            cypher.ONTOLOGY_TRAVERSAL_NODES.replace('*0..5', f'*0..{hops}'),
            iri=iri, hops=hops, limit=safe_limit,
        )
        if not nodes:
            return self._legacy_traversal(node_id=iri, depth=hops, limit=safe_limit)
        ids = [node["id"] for node in nodes]
        edges = self._read_edges(ids, limit=safe_limit * 4)
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "traversal", "root_node_id": iri, "depth": hops, "limit": safe_limit},
        )

    def _legacy_traversal(self, *, node_id: str, depth: int, limit: int) -> dict[str, Any]:
        depth = max(1, min(int(depth), 5))
        limit = max(1, min(int(limit), 1_000))
        nodes = self._session_rows(
            cypher.LEGACY_TRAVERSAL_NODES.replace('*0..5', f'*0..{depth}'),
            node_id=node_id, depth=depth, limit=limit,
        )
        ids = [node["id"] for node in nodes]
        edges = self._read_edges(ids, limit=limit * 4, existing=True)
        return self._explorer_payload(
            nodes=nodes,
            edges=edges,
            view={"type": "traversal", "source": "existing_ontology", "root_node_id": node_id, "depth": depth, "limit": limit},
        )

    def analytics(self, *, ontology_id: str, limit: int = 3000) -> dict[str, Any]:
        projection = self.projection(ontology_id=ontology_id, limit=limit)
        return {"ontology_id": ontology_id, "projection": projection,
                "scope": {"type": "bounded_projection", "requested_limit": limit,
                          "whole_graph_verified": False,
                          "warning": "Rankings and communities describe this projection, not necessarily the whole ontology"},
                "analytics": GraphAnalyzer().analyze_graph(projection)}

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
