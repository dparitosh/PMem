"""Minimal, direct Neo4j publisher with no dependency on the legacy graph proxy."""
from __future__ import annotations

from backend.depo_platform.ontology_maintenance import ontology_writer
from backend.depo_platform.rdf_preparation import prepare_rdf
from backend.depo_platform.graph_publication_lock import graph_publication

import os
import logging
import time
import uuid
import json
from datetime import datetime, timezone
import re
import threading
from typing import Any

from neo4j import GraphDatabase, Query, unit_of_work
from backend.depo_platform.network import bounded_timeout_seconds
from rdflib import Literal, URIRef
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
        self._read_driver = None
        self._driver_lock = threading.Lock()

    def _driver(self):
        if self.auth_mode not in {"token", "none"}:
            raise RuntimeError("NEO4J_AUTH_MODE must be token or none")
        auth = None if self.auth_mode == "none" else (self.username, self.password)
        return GraphDatabase.driver(self.uri, auth=auth, connection_timeout=10,
                                    connection_acquisition_timeout=10, max_transaction_retry_time=0)

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

    @ontology_writer
    @graph_publication
    def publish_turtle(self, *, content: bytes, ontology_id: str, prefix: str, publication_id: str | None = None) -> dict[str, Any]:
        """Upsert an ontology's RDF resources and hierarchy into Neo4j.

        The model retains original RDF predicates and additionally promotes
        subclass/domain/range edges to stable graph relationship types for
        hierarchical exploration.  Repeating a publish is idempotent.
        """
        if self.auth_mode != "none" and not self.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        publication_id = str(publication_id or "").strip() or None
        if publication_id == '__lock__':
            raise ValueError('publication_id is reserved for internal publication locking')
        logger = logging.getLogger(__name__)
        started = time.monotonic()
        logger.warning('Ontology publication phase=parse ontology_id=%s bytes=%s', ontology_id, len(content))
        resources, relationships, ceim_relationships = prepare_rdf(content, 'turtle', canonical='projection')
        logger.warning('Ontology publication phase=prepare_complete ontology_id=%s elapsed_seconds=%.3f', ontology_id, time.monotonic() - started)
        now = datetime.now(timezone.utc).isoformat()
        projection_revision = uuid.uuid4().hex
        resource_query = """
        UNWIND $rows AS row
        MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})
        SET node.prefix = $prefix, node.label = row.label, node.kind = row.kind,
            node.rdf_properties = row.rdf_properties, node.updated_at = $updated_at,
            node.source = row.source, node.description = row.description,
            node.publication_revision = $projection_revision
        FOREACH (_ IN CASE WHEN row.requirement THEN [1] ELSE [] END | SET node:Requirement)
        FOREACH (_ IN CASE WHEN row.requirement THEN [] ELSE [1] END | REMOVE node:Requirement)
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
        from backend.depo_platform.network import graph_write_timeout_seconds, graph_activation_timeout_seconds
        @unit_of_work(timeout=graph_write_timeout_seconds() + graph_activation_timeout_seconds())
        def publish_transaction(tx):
            # The permanent, uniquely constrained receipt key serializes writers.
            tx.run("MERGE (lock:OntologyPublication {ontology_id: $ontology_id, publication_id: '__lock__'}) SET lock.publication_lock = $updated_at",
                   ontology_id=ontology_id, updated_at=now).consume()
            # Restore referenced identities in bounded requests before resource upserts.
            for offset in range(0, len(resources), 1000):
                tx.run("UNWIND $iris AS iri MATCH (node:RetainedOntologyIdentity {ontology_id: $ontology_id, iri: iri}) SET node:OntologyResource REMOVE node:RetainedOntologyIdentity",
                       ontology_id=ontology_id, iris=[row["iri"] for row in resources[offset:offset + 1000]]).consume()
            for offset in range(0, len(resources), 1000):
                tx.run(resource_query, rows=resources[offset:offset + 1000], ontology_id=ontology_id,
                       prefix=prefix, updated_at=now, projection_revision=projection_revision).consume()
            for relation_type, rows in relationships.items():
                if not rows:
                    continue
                query = f"""
                UNWIND $rows AS row
                MATCH (source:OntologyResource {{ontology_id: $ontology_id, iri: row.source}})
                MATCH (target:OntologyResource {{ontology_id: $ontology_id, iri: row.target}})
                {relation_queries[relation_type]}
                SET edge.publication_revision = $projection_revision
                """
                for offset in range(0, len(rows), 1000):
                    tx.run(query, rows=rows[offset:offset + 1000], ontology_id=ontology_id, projection_revision=projection_revision).consume()
            # Only remove edges absent from this exact RDF revision. Matching
            # edges retain identity, including links referenced by other features.
            tx.run("MATCH (a:OntologyResource {ontology_id: $ontology_id})-[edge]->(b:OntologyResource {ontology_id: $ontology_id}) WHERE edge.ontology_id = $ontology_id AND type(edge) IN $types AND (edge.publication_revision IS NULL OR edge.publication_revision <> $projection_revision) DELETE edge",
                   ontology_id=ontology_id, types=list(relationships), projection_revision=projection_revision).consume()
            # Keep externally referenced identities, but remove their projection
            # label so stale records cannot inflate RDF metrics or search.
            tx.run("MATCH (node:OntologyResource {ontology_id: $ontology_id}) WHERE node.publication_revision IS NULL OR node.publication_revision <> $projection_revision REMOVE node:OntologyResource SET node:RetainedOntologyIdentity",
                   ontology_id=ontology_id, projection_revision=projection_revision).consume()
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

        logger.warning('Ontology publication phase=neo4j_write ontology_id=%s resources=%s relationships=%s elapsed_seconds=%.3f',
                       ontology_id, len(resources), sum(len(rows) for rows in relationships.values()), time.monotonic() - started)
        with self._driver() as driver:
            with driver.session(database=self.database) as session:
                staged = getattr(self, '_publish_staged_initial', None)
                if staged:
                    result = staged(session, ontology_id=ontology_id, publication_id=publication_id,
                        prefix=prefix, resources=resources, relationships=relationships,
                        relation_queries=relation_queries, resource_query=resource_query)
                    if result is not None:
                        return result
                session.execute_write(publish_transaction)
        logger.warning('Ontology publication phase=completed ontology_id=%s elapsed_seconds=%.3f', ontology_id, time.monotonic() - started)
        return {
            "status": "success", "ontology_id": ontology_id, "resources": len(resources),
            "relationships": sum(len(rows) for rows in relationships.values()),
            "hierarchy_edges": len(relationships["SUBCLASS_OF"]) + len(relationships["HAS_PART"]),
            "publication_id": publication_id,
        }

    def _publish_staged_initial(self, session, **kwargs):
        schema = session.run(Query("SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
            "WHERE name='uq_ontologystagedresource_identity' RETURN type, entityType, labelsOrTypes, properties", timeout=10)).single()
        if not schema:
            raise RuntimeError('Staged publication schema is missing. Run Neo4j schema provisioning before publishing; atomic fallback is disabled.')
        if (schema['type'] not in {'UNIQUENESS', 'NODE_PROPERTY_UNIQUENESS'}
                or schema['entityType'] != 'NODE' or schema['labelsOrTypes'] != ['StagedOntologyResource']
                or schema['properties'] != ['ontology_id', 'publication_id', 'iri']):
            raise RuntimeError('Staged publication constraint is incompatible')
        from .staged_publication import publish_initial
        from backend.depo_platform.network import graph_write_timeout_seconds, graph_activation_timeout_seconds
        return publish_initial(session, **kwargs,
            timeout=graph_write_timeout_seconds(), activation_timeout=graph_activation_timeout_seconds(),
            unit_of_work=unit_of_work, query_factory=Query)

    def publication_receipt(self, *, ontology_id: str, publication_id: str) -> dict[str, Any] | None:
        rows = self._session_rows(
            """
            MATCH (receipt:OntologyPublication {ontology_id: $ontology_id, publication_id: $publication_id})
            RETURN receipt { .ontology_id, .publication_id, .prefix, .resources, .relationships,
                             .hierarchy_edges, .status, .published_at, .current,
                             .resource_offset, .resources_expected, .relationships_expected } AS receipt
            """,
            ontology_id=ontology_id, publication_id=publication_id,
        )
        return dict(rows[0]["receipt"]) if rows else None

    def close(self):
        with self._driver_lock:
            if self._read_driver is not None:
                self._read_driver.close()
                self._read_driver = None

    def _session_rows(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        if self.auth_mode != "none" and not self.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        with self._driver_lock:
            if self._read_driver is None:
                self._read_driver = self._driver()
            driver = self._read_driver
        with driver.session(database=self.database) as session:
            from backend.depo_platform.network import bounded_timeout_seconds
            timeout = bounded_timeout_seconds("GRAPH_QUERY_TIMEOUT_SECONDS", default=30, maximum=300)
            return session.run(Query(query, timeout=timeout), parameters).data()

    def mapping_terms(self, scope: str) -> dict[str, Any]:
        if not isinstance(scope, str) or not scope.strip() or len(scope) > 256:
            raise ValueError('Select a valid ontology scope.')
        scopes = {scope, scope.lower()}
        if scope.lower() in {'ap242', 'step', 'step_ap242_mbd3d'}:
            scopes.update({'ap242', 'step_ap242_mbd3d', 'AP242', 'STEP_AP242_MBD3D'})
        kinds = [{'kind': kind, 'iri': 'http://www.w3.org/2002/07/owl#' + kind}
                 for kind in ('Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty')]
        rows = self._session_rows(cypher.MAPPING_TERMS, scope=scope, scopes=sorted(scopes), kinds=kinds,
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
            ontology_id=ontology_id, ids=[node["id"] for node in nodes], limit=safe_limit * 4,
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
                "elementId": str(node.get("graph_id") or node["id"]),
                "labels": [str(node.get("type") or "resource")],
                "properties": {
                    "iri": str(node.get("iri") or node["id"]),
                    "label": str(node.get("label") or node["id"]),
                    "kind": str(node.get("type") or "resource"),
                    **({"ontology_id": node["ontology_id"]} if node.get("ontology_id") else {}),
                    **({"search_score": int(node["score"])} if node.get("score") is not None else {}),
                },
                "can_traverse": True,
            }
            for node in nodes
        ]
        selected_ids = {node["elementId"] for node in explorer_nodes}
        explorer_edges = [
            {
                "elementId": str(edge.get("edge_id") or f"{edge.get('graph_source') or edge['source']}::{edge.get('predicate') or edge.get('type') or 'RELATED_TO'}::{edge.get('graph_target') or edge['target']}"),
                "start": str(edge.get("graph_source") or edge["source"]),
                "end": str(edge.get("graph_target") or edge["target"]),
                "type": str(edge.get("type") or "RELATED_TO"),
                "properties": {"raw_type": str(edge.get("type") or "RELATED_TO"), **({"predicate": edge["predicate"]} if edge.get("predicate") else {})},
            }
            for edge in edges if str(edge.get("graph_source") or edge["source"]) in selected_ids and str(edge.get("graph_target") or edge["target"]) in selected_ids
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
          WHERE ($ontology_id = '' OR n.ontology_id = $ontology_id) AND ($ontology_prefix = '' OR n.prefix = $ontology_prefix)
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
            AND ($ontology_prefix = '' OR (a.prefix = $ontology_prefix AND b.prefix = $ontology_prefix))
            AND a.ontology_id = b.ontology_id
          RETURN count(r) AS relationships
        }
        CALL {
          MATCH (n:OntologyResource)
          WHERE ($ontology_id = '' OR n.ontology_id = $ontology_id) AND ($ontology_prefix = '' OR n.prefix = $ontology_prefix)
          WITH n.ontology_id AS ontology, count(n) AS node_count
          ORDER BY node_count DESC, ontology LIMIT 201
          RETURN collect({ontology: ontology, node_count: node_count}) AS ontology_breakdown
        }
        RETURN resources, relationships, classes, object_properties, data_properties,
               annotation_properties, named_individuals, ontology_breakdown
        """
        rows = self._session_rows(query, ontology_id=ontology_id, ontology_prefix=ontology_prefix, rdf_type=str(RDF.type),
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
            "MATCH (n:OntologyResource) RETURN elementId(n) AS id, n.iri AS iri, n.label AS label, n.kind AS type, n.ontology_id AS ontology_id "
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
        edges = self._read_edges([node["id"] for node in nodes], limit=safe_limit * 4)
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
        nodes = self._session_rows(cypher.ONTOLOGY_SEARCH_NODES, terms=terms, limit=safe_limit, ontology_id=ontology_id, ontology_prefix=ontology_prefix)
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

    def _bounded_walk(self, root_id: str, depth: int, limit: int, *, existing: bool = False):
        """Expand one hop at a time; never enumerate every multi-hop path."""
        condition = cypher.LEGACY_NODE_FILTER.replace('n:', 'neighbor:') if existing else 'neighbor:OntologyResource'
        scope = "coalesce(neighbor.ontology_id,neighbor.source_ontology,neighbor.prefix) = coalesce(root.ontology_id,root.source_ontology,root.prefix)" if existing else 'neighbor.ontology_id = root.ontology_id'
        roots = self._session_rows("MATCH (n) WHERE elementId(n)=$id AND " + condition.replace("neighbor:", "n:") + " RETURN elementId(n) AS id, coalesce(n.iri,n.uri) AS iri, coalesce(n.label,n.name,n.iri,n.uri) AS label, coalesce(n.kind,head(labels(n))) AS type, n.ontology_id AS ontology_id", id=root_id)
        if not roots:
            return []
        selected = {root_id: roots[0]}
        frontier = [root_id]
        for _ in range(depth):
            remaining = limit - len(selected)
            if not frontier or remaining <= 0:
                break
            rows = self._session_rows(
                "MATCH (root), (n) WHERE elementId(root)=$root AND elementId(n) IN $frontier "
                "MATCH (n)--(neighbor) WHERE " + condition + " AND " + scope + " AND NOT elementId(neighbor) IN $seen "
                "RETURN DISTINCT elementId(neighbor) AS id, coalesce(neighbor.iri,neighbor.uri) AS iri, coalesce(neighbor.label,neighbor.name,neighbor.iri,neighbor.uri) AS label, coalesce(neighbor.kind,head(labels(neighbor))) AS type, neighbor.ontology_id AS ontology_id LIMIT $limit",
                root=root_id, frontier=frontier, seen=list(selected), limit=remaining)
            frontier = []
            for row in rows:
                if row['id'] not in selected and len(selected) < limit:
                    selected[row['id']] = row
                    frontier.append(row['id'])
        return list(selected.values())

    def traversal(self, *, iri: str, depth: int = 1, limit: int = 200) -> dict[str, Any]:
        hops, safe_limit = max(1, min(int(depth), 5)), max(1, min(int(limit), 1_000))
        roots = self._session_rows("MATCH (n:OntologyResource) WHERE elementId(n) = $identity OR n.iri = $identity RETURN elementId(n) AS id LIMIT 2", identity=iri)
        if len(roots) > 1:
            raise ValueError('Resource IRI is shared by multiple ontologies; select a scoped graph node ID')
        if not roots:
            return self._legacy_traversal(node_id=iri, depth=hops, limit=safe_limit)
        root_id = roots[0]['id']
        nodes = self._bounded_walk(root_id, hops, safe_limit)
        edges = self._read_edges([node['id'] for node in nodes], limit=safe_limit * 4)
        return self._explorer_payload(nodes=nodes, edges=edges,
            view={"type": "traversal", "root_node_id": root_id, "depth": hops, "limit": safe_limit,
                  "truncated": len(nodes) >= safe_limit})

    def _legacy_traversal(self, *, node_id: str, depth: int, limit: int) -> dict[str, Any]:
        nodes = self._bounded_walk(node_id, depth, limit, existing=True)
        edges = self._read_edges([node['id'] for node in nodes], limit=limit * 4, existing=True)
        return self._explorer_payload(nodes=nodes, edges=edges,
            view={"type": "traversal", "source": "existing_ontology", "root_node_id": node_id,
                  "depth": depth, "limit": limit, "truncated": len(nodes) >= limit})

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
            f"MATCH path=(root)-[*1..{hops}]-(neighbor:OntologyResource {{ontology_id: $ontology_id}}) "
            "WHERE length(path) <= $hops "
            "RETURN neighbor.iri AS iri, neighbor.label AS label, neighbor.kind AS kind, min(length(path)) AS distance "
            "ORDER BY distance, label LIMIT $limit",
            ontology_id=ontology_id, iri=iri, hops=hops, limit=safe_limit,
        )
        return {"ontology_id": ontology_id, "anchor": iri, "max_hops": hops, "neighbors": rows}


publisher = Neo4jPublisher()
