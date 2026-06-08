"""Official-driver graph view services for visualization and contextual subgraphs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

try:
    from backend.core.db_config import get_config, get_driver
except Exception:  # pragma: no cover
    from core.db_config import get_config, get_driver

logger = logging.getLogger(__name__)


def _node_payload(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "elementId": node.get("elementId"),
        "labels": node.get("labels") or [],
        "properties": node.get("properties") or {},
    }


def _relationship_payload(rel: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "elementId": rel.get("elementId"),
        "type": rel.get("type"),
        "start": rel.get("start"),
        "end": rel.get("end"),
        "properties": rel.get("properties") or {},
    }


class GraphViewService:
    """Read-only graph view generation using the official Neo4j driver."""

    SCHEMA_RELATIONSHIP_TYPES = [
        "SUBCLASS_OF",
        "DOMAIN",
        "RANGE",
        "SUBPROPERTY_OF",
        "EQUIVALENT_CLASS",
        "DISJOINT_WITH",
    ]

    @staticmethod
    def _run(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        config = get_config()
        driver = get_driver()
        with driver.session(database=config.database) as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    @staticmethod
    def _write(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        config = get_config()
        driver = get_driver()
        with driver.session(database=config.database) as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    @staticmethod
    def _extract_xsd_named_subclass_rows(file_path: Path, class_uri_lookup: Dict[str, str]) -> List[Dict[str, str]]:
        if not file_path.exists():
            return []

        try:
            root = ET.parse(file_path).getroot()
        except Exception:
            logger.warning("Failed to parse XSD for named subclass derivation: %s", file_path)
            return []

        xsd_ns = {"xs": "http://www.w3.org/2001/XMLSchema"}
        subclass_pairs = set()

        def local_type_name(raw: Optional[str]) -> str:
            value = str(raw or "").strip()
            if not value:
                return ""
            if ":" in value:
                value = value.split(":", 1)[1]
            return value

        for complex_type in root.findall(".//xs:complexType[@name]", xsd_ns):
            child_name = str(complex_type.get("name") or "").strip()
            if not child_name:
                continue

            extension_points = [
                complex_type.find("./xs:complexContent/xs:extension", xsd_ns),
                complex_type.find("./xs:complexContent/xs:restriction", xsd_ns),
                complex_type.find("./xs:simpleContent/xs:extension", xsd_ns),
                complex_type.find("./xs:simpleContent/xs:restriction", xsd_ns),
            ]
            for extension in extension_points:
                if extension is None:
                    continue
                parent_name = local_type_name(extension.get("base"))
                if not parent_name or parent_name == child_name:
                    continue
                child_uri = class_uri_lookup.get(child_name)
                parent_uri = class_uri_lookup.get(parent_name)
                if child_uri and parent_uri:
                    subclass_pairs.add((child_uri, parent_uri))

        return [
            {"child_uri": child_uri, "parent_uri": parent_uri}
            for child_uri, parent_uri in sorted(subclass_pairs)
        ]

    @staticmethod
    def rows_to_graph(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        nodes: Dict[str, Dict[str, Any]] = {}
        relationships: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            for key in ("n", "m"):
                node = row.get(key)
                if node and node.get("elementId"):
                    nodes[node["elementId"]] = _node_payload(node)
            rel = row.get("r")
            if rel and rel.get("elementId"):
                relationships[rel["elementId"]] = _relationship_payload(rel)

        return {
            "nodes": list(nodes.values()),
            "relationships": list(relationships.values()),
            "counts": {
                "nodes": len(nodes),
                "relationships": len(relationships),
            },
        }

    @classmethod
    def _ontology_view_rows(cls, prefix: str, limit: int) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 5000))
        relationship_slice_limit = max(12, min(safe_limit // 5, 240))
        isolated_limit = max(20, min(safe_limit // 4, 320))
        return cls._run(
            """
            CALL () {
              CALL () {
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'SUBCLASS_OF'
                  AND any(label IN labels(n) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND any(label IN labels(m) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'DOMAIN'
                  AND any(label IN labels(n) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND any(label IN labels(m) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'RANGE'
                  AND any(label IN labels(n) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND any(label IN labels(m) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'SUBPROPERTY_OF'
                  AND any(label IN labels(n) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND any(label IN labels(m) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)
                WHERE any(label IN labels(n) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND NOT EXISTS {
                    MATCH (n)-[r]->(m)
                    WHERE type(r) IN $schema_relationship_types
                      AND any(label IN labels(m) WHERE label IN ['OntologyClass', 'Class', 'ObjectProperty', 'DatatypeProperty'])
                      AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                  }
                RETURN n, NULL AS r, NULL AS m
                ORDER BY coalesce(n.name, n.uri, '')
                LIMIT $isolated_limit
              }
              RETURN n, r, m
            }
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              CASE WHEN r IS NOT NULL THEN {
                elementId: elementId(r), type: type(r), properties: properties(r),
                start: elementId(startNode(r)), end: elementId(endNode(r))
              } ELSE NULL END AS r,
              CASE WHEN m IS NOT NULL THEN {
                elementId: elementId(m), labels: labels(m), properties: properties(m)
              } ELSE NULL END AS m
            """,
            {
                "prefix": prefix,
                "limit": safe_limit,
                "relationship_slice_limit": relationship_slice_limit,
                "isolated_limit": isolated_limit,
                "schema_relationship_types": cls.SCHEMA_RELATIONSHIP_TYPES,
            },
        )

    @classmethod
    def _hydrate_registered_ontology_schema(cls, prefix: str) -> bool:
        try:
            try:
                from backend.Services.ontology_upload_manager import OntologyUploadManager
            except Exception:
                from Services.ontology_upload_manager import OntologyUploadManager

            listed = OntologyUploadManager.list_ontologies()
            if listed.get("status") != "success":
                return False

            prefix_lookup = (prefix or "").strip().lower()
            matched = next(
                (
                    meta for meta in listed.get("ontologies", [])
                    if prefix_lookup in {
                        str(meta.get("prefix") or "").strip().lower(),
                        str(meta.get("ontology_prefix") or "").strip().lower(),
                    }
                ),
                None,
            )
            if not matched:
                return False

            meta_result = OntologyUploadManager.get_ontology(matched["ontology_id"])
            if meta_result.get("status") != "success":
                return False

            meta = meta_result["metadata"]
            file_path = Path(meta["file_path"])
            if not file_path.exists():
                return False

            file_content = file_path.read_bytes()
            rdf_graph, ttl_text, owl_metadata = OntologyUploadManager._generate_rdf_for_source(
                file_content=file_content,
                filename=file_path.name,
                file_type=meta["file_type"],
                generation_type=meta.get("generation_type", ""),
            )

            owl_file_path = ""
            if meta["file_type"] == "xsd":
                owl_path = file_path.with_suffix(".generated.ttl")
                owl_path.write_text(ttl_text, encoding="utf-8")
                owl_file_path = str(owl_path)
            elif file_path.suffix.lower() in {".ttl", ".rdf", ".owl"}:
                owl_file_path = str(file_path)

            result = cls._push_rdf_schema_to_neo4j(
                ontology_id=matched["ontology_id"],
                meta=meta,
                rdf_graph=rdf_graph,
                owl_file_path=owl_file_path,
            )
            if result.get("status") == "success":
                OntologyUploadManager._update_status(matched["ontology_id"], "pushed_to_neo4j", {
                    "neo4j_nodes_merged": result.get("nodes_merged", 0),
                    "neo4j_relationships_merged": result.get("relationships_merged", 0),
                    "owl_file_path": owl_file_path,
                    "owl_generation_metadata": owl_metadata,
                    "parsed_class_count": result.get("parsed_class_count", 0),
                    "parsed_object_property_count": result.get("parsed_object_property_count", 0),
                    "parsed_datatype_property_count": result.get("parsed_datatype_property_count", 0),
                    "parsed_subclass_relationship_count": result.get("parsed_subclass_relationship_count", 0),
                    "parsed_domain_relationship_count": result.get("parsed_domain_relationship_count", 0),
                    "parsed_range_relationship_count": result.get("parsed_range_relationship_count", 0),
                })
                logger.info(
                    "Hydrated ontology schema for prefix=%s from registry ontology_id=%s nodes=%s rels=%s",
                    prefix,
                    matched["ontology_id"],
                    result.get("nodes_merged", 0),
                    result.get("relationships_merged", 0),
                )
                return True
            logger.warning("Ontology schema hydration failed for prefix=%s: %s", prefix, result)
            return False
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            logger.warning("Ontology schema hydration error for prefix=%s: %s", prefix, exc)
            return False

    @classmethod
    def _augment_registered_ontology_subclass_edges(cls, prefix: str) -> bool:
        try:
            try:
                from backend.Services.ontology_upload_manager import OntologyUploadManager
            except Exception:
                from Services.ontology_upload_manager import OntologyUploadManager

            listed = OntologyUploadManager.list_ontologies()
            if listed.get("status") != "success":
                return False

            prefix_lookup = (prefix or "").strip().lower()
            matched = next(
                (
                    meta for meta in listed.get("ontologies", [])
                    if str(meta.get("file_type") or "").lower() == "xsd"
                    and prefix_lookup in {
                        str(meta.get("prefix") or "").strip().lower(),
                        str(meta.get("ontology_prefix") or "").strip().lower(),
                    }
                ),
                None,
            )
            if not matched:
                return False

            file_path = Path(matched.get("file_path") or "")
            if not file_path.exists():
                return False

            class_rows = cls._run(
                """
                MATCH (c:OntologyClass)
                WHERE c.prefix = $prefix OR c.ontology_prefix = $prefix
                RETURN c.name AS name, c.uri AS uri
                """,
                {"prefix": prefix},
            )
            class_uri_lookup = {
                str(row.get("name") or "").strip(): str(row.get("uri") or "").strip()
                for row in class_rows
                if row.get("name") and row.get("uri")
            }
            if not class_uri_lookup:
                return False

            subclass_rows = cls._extract_xsd_named_subclass_rows(file_path, class_uri_lookup)
            if not subclass_rows:
                return False

            result = cls._write(
                """
                UNWIND $rows AS row
                MATCH (child:OntologyClass {uri: row.child_uri, prefix: $prefix})
                MATCH (parent:OntologyClass {uri: row.parent_uri, prefix: $prefix})
                MERGE (child)-[r:SUBCLASS_OF]->(parent)
                ON CREATE SET
                  r.source = 'xsd-derived',
                  r.ontology_prefix = $prefix,
                  r.created_at = datetime()
                RETURN count(r) AS count
                """,
                {"rows": subclass_rows, "prefix": prefix},
            )
            created = (result or [{"count": 0}])[0].get("count", 0)
            logger.info(
                "Augmented named XSD subclass edges for prefix=%s rows=%s merged=%s",
                prefix,
                len(subclass_rows),
                created,
            )
            return created > 0
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            logger.warning("Failed to augment XSD subclass edges for prefix=%s: %s", prefix, exc)
            return False

    @classmethod
    def _push_rdf_schema_to_neo4j(
        cls,
        *,
        ontology_id: str,
        meta: Dict[str, Any],
        rdf_graph: Any,
        owl_file_path: str = "",
    ) -> Dict[str, Any]:
        try:
            try:
                from backend.Services.ontology_upload_manager import OntologyUploadManager
            except Exception:
                from Services.ontology_upload_manager import OntologyUploadManager

            from rdflib import URIRef
            from rdflib.namespace import RDF, RDFS, OWL

            prefix = meta["prefix"]
            ontology_name = meta["ontology_name"]
            version = meta.get("version", 1)
            labels = OntologyUploadManager._rdf_labels(rdf_graph)

            class_terms = {
                s for s in rdf_graph.subjects(RDF.type, OWL.Class)
                if isinstance(s, URIRef)
            }
            object_props = {
                s for s in rdf_graph.subjects(RDF.type, OWL.ObjectProperty)
                if isinstance(s, URIRef)
            }
            datatype_props = {
                s for s in rdf_graph.subjects(RDF.type, OWL.DatatypeProperty)
                if isinstance(s, URIRef)
            }

            class_rows = [
                {
                    "uri": OntologyUploadManager._term_id(term),
                    "name": labels.get(OntologyUploadManager._term_id(term)) or OntologyUploadManager._local_name(term),
                    "namespace": OntologyUploadManager._namespace(term),
                    "comment": str(next(rdf_graph.objects(term, RDFS.comment), "")),
                }
                for term in sorted(class_terms, key=str)
            ]
            object_rows = [
                {
                    "uri": OntologyUploadManager._term_id(term),
                    "name": labels.get(OntologyUploadManager._term_id(term)) or OntologyUploadManager._local_name(term),
                    "namespace": OntologyUploadManager._namespace(term),
                    "comment": str(next(rdf_graph.objects(term, RDFS.comment), "")),
                }
                for term in sorted(object_props, key=str)
            ]
            datatype_rows = [
                {
                    "uri": OntologyUploadManager._term_id(term),
                    "name": labels.get(OntologyUploadManager._term_id(term)) or OntologyUploadManager._local_name(term),
                    "namespace": OntologyUploadManager._namespace(term),
                    "comment": str(next(rdf_graph.objects(term, RDFS.comment), "")),
                }
                for term in sorted(datatype_props, key=str)
            ]
            class_uri_lookup = {
                row["name"]: row["uri"]
                for row in class_rows
                if row.get("name") and row.get("uri")
            }
            subclass_rows = [
                {"child_uri": OntologyUploadManager._term_id(s), "parent_uri": OntologyUploadManager._term_id(o)}
                for s, _, o in rdf_graph.triples((None, RDFS.subClassOf, None))
                if isinstance(s, URIRef) and isinstance(o, URIRef) and s in class_terms
            ]
            if str(meta.get("file_type") or "").lower() == "xsd":
                subclass_rows.extend(
                    cls._extract_xsd_named_subclass_rows(Path(meta["file_path"]), class_uri_lookup)
                )
                subclass_rows = list({
                    (row["child_uri"], row["parent_uri"]): row
                    for row in subclass_rows
                }.values())
            domain_rows = []
            range_rows = []
            for prop in sorted(object_props | datatype_props, key=str):
                prop_uri = OntologyUploadManager._term_id(prop)
                for domain in rdf_graph.objects(prop, RDFS.domain):
                    if isinstance(domain, URIRef):
                        domain_rows.append({"prop_uri": prop_uri, "class_uri": OntologyUploadManager._term_id(domain)})
                for range_term in rdf_graph.objects(prop, RDFS.range):
                    if isinstance(range_term, URIRef):
                        range_rows.append({"prop_uri": prop_uri, "range_uri": OntologyUploadManager._term_id(range_term)})

            def run_batch(cypher: str, rows: List[Dict[str, Any]]) -> int:
                if not rows:
                    return 0
                total = 0
                batch = 500
                for idx in range(0, len(rows), batch):
                    result = cls._write(
                        cypher,
                        {
                            "rows": rows[idx:idx + batch],
                            "prefix": prefix,
                            "ontology_id": ontology_id,
                            "ontology_name": ontology_name,
                            "version": version,
                            "owl_file_path": owl_file_path,
                        },
                    )
                    total += (result or [{"count": len(rows[idx:idx + batch])}])[0].get("count", len(rows[idx:idx + batch]))
                return total

            class_cypher = """
UNWIND $rows AS row
MERGE (c:OntologyClass {uri: row.uri, prefix: $prefix})
ON CREATE SET c.created_at = datetime()
SET c.name = row.name,
    c.concept_type = 'owl:Class',
    c.namespace = row.namespace,
    c.comment = row.comment,
    c.source_ontology = $ontology_id,
    c.ontology_name = $ontology_name,
    c.version = $version,
    c.ontology_prefix = $prefix,
    c.schema_type = 'schema',
    c.owl_file_path = $owl_file_path,
    c.updated_at = datetime()
RETURN count(c) AS count
"""
            object_prop_cypher = """
UNWIND $rows AS row
MERGE (p:ObjectProperty {uri: row.uri, prefix: $prefix})
ON CREATE SET p.created_at = datetime()
SET p.name = row.name,
    p.concept_type = 'owl:ObjectProperty',
    p.namespace = row.namespace,
    p.comment = row.comment,
    p.source_ontology = $ontology_id,
    p.ontology_name = $ontology_name,
    p.version = $version,
    p.ontology_prefix = $prefix,
    p.schema_type = 'schema',
    p.owl_file_path = $owl_file_path,
    p.updated_at = datetime()
RETURN count(p) AS count
"""
            datatype_prop_cypher = """
UNWIND $rows AS row
MERGE (p:DatatypeProperty {uri: row.uri, prefix: $prefix})
ON CREATE SET p.created_at = datetime()
SET p.name = row.name,
    p.concept_type = 'owl:DatatypeProperty',
    p.namespace = row.namespace,
    p.comment = row.comment,
    p.source_ontology = $ontology_id,
    p.ontology_name = $ontology_name,
    p.version = $version,
    p.ontology_prefix = $prefix,
    p.schema_type = 'schema',
    p.owl_file_path = $owl_file_path,
    p.updated_at = datetime()
RETURN count(p) AS count
"""
            subclass_cypher = """
UNWIND $rows AS row
MATCH (child:OntologyClass {uri: row.child_uri, prefix: $prefix})
MATCH (parent:OntologyClass {uri: row.parent_uri, prefix: $prefix})
MERGE (child)-[r:SUBCLASS_OF]->(parent)
ON CREATE SET
    r.source = 'schema',
    r.ontology_prefix = $prefix,
    r.created_at = datetime()
RETURN count(r) AS count
"""
            domain_cypher = """
UNWIND $rows AS row
MATCH (p {uri: row.prop_uri, prefix: $prefix})
MATCH (c:OntologyClass {uri: row.class_uri, prefix: $prefix})
WHERE p:ObjectProperty OR p:DatatypeProperty
MERGE (p)-[r:DOMAIN]->(c)
RETURN count(r) AS count
"""
            range_cypher = """
UNWIND $rows AS row
MATCH (p {uri: row.prop_uri, prefix: $prefix})
WHERE p:ObjectProperty OR p:DatatypeProperty
MATCH (c:OntologyClass {uri: row.range_uri, prefix: $prefix})
MERGE (p)-[r:RANGE]->(c)
RETURN count(r) AS count
"""

            classes_created = run_batch(class_cypher, class_rows)
            object_props_created = run_batch(object_prop_cypher, object_rows)
            datatype_props_created = run_batch(datatype_prop_cypher, datatype_rows)
            subclass_created = run_batch(subclass_cypher, subclass_rows)
            domain_created = run_batch(domain_cypher, domain_rows)
            range_created = run_batch(range_cypher, range_rows)
            relationships_created = subclass_created + domain_created + range_created

            return {
                "status": "success",
                "ontology_id": ontology_id,
                "version": version,
                "nodes_merged": classes_created + object_props_created + datatype_props_created,
                "relationships_merged": relationships_created,
                "parsed_class_count": len(class_rows),
                "parsed_object_property_count": len(object_rows),
                "parsed_datatype_property_count": len(datatype_rows),
                "parsed_subclass_relationship_count": len(subclass_rows),
                "parsed_domain_relationship_count": len(domain_rows),
                "parsed_range_relationship_count": len(range_rows),
            }
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            logger.warning("Official-driver RDF schema push failed for ontology_id=%s: %s", ontology_id, exc)
            return {"status": "error", "error": str(exc)}

    @classmethod
    def get_graph_overview(cls, limit: int = 1000) -> Dict[str, Any]:
        rows = cls._run(
            """
            MATCH (n)-[r]->(m)
            WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              {elementId: elementId(r), type: type(r), properties: properties(r),
               start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
              {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
            LIMIT $limit
            """,
            {"limit": max(1, min(int(limit), 5000))},
        )
        return cls.rows_to_graph(rows)

    @classmethod
    def get_virtual_ontology_view(cls, prefix: str, limit: int = 1000) -> Dict[str, Any]:
        rows = cls._ontology_view_rows(prefix, limit)
        if not rows and prefix:
            hydrated = cls._hydrate_registered_ontology_schema(prefix)
            if hydrated:
                rows = cls._ontology_view_rows(prefix, limit)
        elif prefix:
            has_subclass = any(row.get("r", {}).get("type") == "SUBCLASS_OF" for row in rows if row.get("r"))
            if not has_subclass:
                augmented = cls._augment_registered_ontology_subclass_edges(prefix)
                if augmented:
                    rows = cls._ontology_view_rows(prefix, limit)
        graph = cls.rows_to_graph(rows)
        graph["view"] = {"type": "ontology", "prefix": prefix}
        return graph

    @classmethod
    def get_contextual_subgraph(
        cls,
        *,
        search: str = "",
        ontology_prefix: str = "",
        import_id: str = "",
        limit: int = 400,
    ) -> Dict[str, Any]:
        query = """
        MATCH (seed)
        WHERE NOT (seed:DatasheetChunk OR seed:GraphChunk)
          AND (
            $search = '' OR
            any(label IN labels(seed) WHERE toLower(label) CONTAINS toLower($search)) OR
            any(key IN keys(seed) WHERE toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS toLower($search))
          )
          AND ($ontology_prefix = '' OR seed.ontology_prefix = $ontology_prefix OR seed.prefix = $ontology_prefix)
          AND ($import_id = '' OR seed.import_id = $import_id)
        WITH seed LIMIT $limit
        OPTIONAL MATCH (seed)-[r]-(adjacent)
        WHERE adjacent IS NULL OR NOT (adjacent:DatasheetChunk OR adjacent:GraphChunk)
        RETURN
          {elementId: elementId(seed), labels: labels(seed), properties: properties(seed)} AS n,
          CASE WHEN r IS NOT NULL THEN {
            elementId: elementId(r), type: type(r), properties: properties(r),
            start: elementId(startNode(r)), end: elementId(endNode(r))
          } ELSE NULL END AS r,
          CASE WHEN adjacent IS NOT NULL THEN {
            elementId: elementId(adjacent), labels: labels(adjacent), properties: properties(adjacent)
          } ELSE NULL END AS m
        """
        rows = cls._run(
            query,
            {
                "search": search or "",
                "ontology_prefix": ontology_prefix or "",
                "import_id": import_id or "",
                "limit": max(1, min(int(limit), 2000)),
            },
        )
        graph = cls.rows_to_graph(rows)
        graph["view"] = {
            "type": "contextual-subgraph",
            "search": search or "",
            "ontology_prefix": ontology_prefix or "",
            "import_id": import_id or "",
        }
        return graph
