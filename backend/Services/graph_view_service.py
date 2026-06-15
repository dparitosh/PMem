"""Official-driver graph view services for visualization and contextual subgraphs."""

from __future__ import annotations

import hashlib
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


def _fragment(value: Any) -> str:
    raw = str(value or "")
    if "#" in raw:
        return raw.rsplit("#", 1)[-1]
    if "/" in raw:
        return raw.rstrip("/").rsplit("/", 1)[-1]
    return raw


def _first_text_value(properties: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = properties.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


class GraphViewService:
    """Read-only graph view generation using the official Neo4j driver."""

    SCHEMA_RELATIONSHIP_TYPES = [
        "SUBCLASS_OF",
        "DOMAIN",
        "RANGE",
        "SUBPROPERTY_OF",
        "EQUIVALENT_CLASS",
        "DISJOINT_WITH",
        "INVERSE_OF",
        "ON_PROPERTY",
        "SOME_VALUES_FROM",
        "ALL_VALUES_FROM",
        "HAS_VALUE",
        "CLASS_RESTRICTION",
    ]

    SCHEMA_NODE_LABELS = [
        "OntologyClass",
        "Class",
        "ObjectProperty",
        "DatatypeProperty",
        "Restriction",
        "OntologyRestriction",
        "Datatype",
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

    @classmethod
    def _resolve_ontology_prefix(cls, value: str) -> str:
        """Resolve registry ontology ids to graph prefixes when callers pass either form."""
        token = str(value or "").strip()
        if not token or token.upper() == "ALL":
            return token

        rows = cls._run(
            """
            MATCH (n)
            WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
              AND (
                n.prefix = $token OR
                n.ontology_prefix = $token OR
                n.source_ontology = $token OR
                n.ontology_id = $token OR
                n.id = $token
              )
            WITH coalesce(n.prefix, n.ontology_prefix) AS prefix, count(n) AS node_count
            WHERE prefix IS NOT NULL AND prefix <> ''
            RETURN prefix
            ORDER BY node_count DESC, prefix ASC
            LIMIT 1
            """,
            {"token": token},
        )
        return (rows[0].get("prefix") if rows else None) or token

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

        def sort_key(item: Dict[str, Any]) -> tuple:
            props = item.get("properties") or {}
            labels = item.get("labels") or []
            return (
                str(props.get("ontology_prefix") or props.get("prefix") or ""),
                str(labels[0] if labels else ""),
                str(props.get("name") or props.get("title") or props.get("code") or props.get("label") or ""),
                str(item.get("elementId") or ""),
            )

        node_list = sorted(nodes.values(), key=sort_key)
        rel_list = sorted(
            relationships.values(),
            key=lambda item: (
                str(item.get("type") or ""),
                str((item.get("properties") or {}).get("ontology_prefix") or (item.get("properties") or {}).get("prefix") or ""),
                str(item.get("start") or ""),
                str(item.get("end") or ""),
                str(item.get("elementId") or ""),
            ),
        )

        return {
            "nodes": node_list,
            "relationships": rel_list,
            "counts": {
                "nodes": len(node_list),
                "relationships": len(rel_list),
            },
        }

    @staticmethod
    def _is_metadata_like_node(node: Dict[str, Any]) -> bool:
        props = node.get("properties") or {}
        name = _first_text_value(
            props,
            (
                "name",
                "title",
                "label",
                "code",
                "display_name",
                "displayName",
                "id",
                "uid",
            ),
        ).lower()
        if not name.startswith("id"):
            return False

        labels = [str(label or "").lower() for label in (node.get("labels") or [])]
        return not any("part" in label for label in labels)

    @staticmethod
    def _is_part_node(node: Dict[str, Any]) -> bool:
        labels = [str(label or "").lower() for label in (node.get("labels") or [])]
        return any("part" in label for label in labels)

    @classmethod
    def _filter_graph_nodes(
        cls,
        graph: Dict[str, Any],
        *,
        prefer_part_nodes: bool = False,
    ) -> Dict[str, Any]:
        nodes = [node for node in (graph.get("nodes") or []) if node.get("elementId")]
        relationships = [rel for rel in (graph.get("relationships") or []) if rel.get("elementId")]

        filtered_nodes = [node for node in nodes if not cls._is_metadata_like_node(node)]
        if prefer_part_nodes:
            part_nodes = [node for node in filtered_nodes if cls._is_part_node(node)]
            if part_nodes:
                filtered_nodes = part_nodes

        keep_ids = {node["elementId"] for node in filtered_nodes}
        filtered_relationships = [
            rel
            for rel in relationships
            if rel.get("start") in keep_ids and rel.get("end") in keep_ids
        ]

        return {
            "nodes": sorted(
                filtered_nodes,
                key=lambda item: (
                    str((item.get("properties") or {}).get("ontology_prefix") or (item.get("properties") or {}).get("prefix") or ""),
                    str((item.get("labels") or [""])[0] if item.get("labels") else ""),
                    str((item.get("properties") or {}).get("name") or (item.get("properties") or {}).get("title") or (item.get("properties") or {}).get("label") or ""),
                    str(item.get("elementId") or ""),
                ),
            ),
            "relationships": sorted(
                filtered_relationships,
                key=lambda item: (
                    str(item.get("type") or ""),
                    str((item.get("properties") or {}).get("ontology_prefix") or (item.get("properties") or {}).get("prefix") or ""),
                    str(item.get("start") or ""),
                    str(item.get("end") or ""),
                    str(item.get("elementId") or ""),
                ),
            ),
            "counts": {
                "nodes": len(filtered_nodes),
                "relationships": len(filtered_relationships),
            },
        }

    @classmethod
    def _reasoning_projection_graph(cls, prefix: str) -> Dict[str, Any]:
        try:
            try:
                from backend.Services.ontology_taxonomy_service import OntologyTaxonomyService
            except Exception:
                from Services.ontology_taxonomy_service import OntologyTaxonomyService

            reasoning = OntologyTaxonomyService.get_reasoning(prefix)
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            logger.warning("Reasoning projection failed for prefix=%s: %s", prefix, exc)
            return {"nodes": [], "relationships": [], "counts": {"nodes": 0, "relationships": 0}}

        nodes: Dict[str, Dict[str, Any]] = {}
        relationships: Dict[str, Dict[str, Any]] = {}

        def ensure_node(
            *,
            iri: str,
            label: str = "",
            node_labels: Optional[List[str]] = None,
            properties: Optional[Dict[str, Any]] = None,
        ) -> None:
            if not iri:
                return
            payload = {
                "elementId": iri,
                "labels": node_labels or ["OntologyClass"],
                "properties": {
                    "uri": iri,
                    "name": label or _fragment(iri),
                    "label": label or _fragment(iri),
                    "prefix": prefix,
                    "ontology_prefix": prefix,
                    **(properties or {}),
                },
            }
            existing = nodes.get(iri)
            if not existing:
                nodes[iri] = payload
                return
            merged_labels = sorted(set((existing.get("labels") or []) + (payload.get("labels") or [])))
            existing["labels"] = merged_labels
            existing_props = existing.get("properties") or {}
            incoming_props = payload.get("properties") or {}
            for key, value in incoming_props.items():
                if value not in ("", None):
                    existing_props[key] = value
            existing["properties"] = existing_props

        def ensure_ref_node(ref: Dict[str, Any], fallback_labels: Optional[List[str]] = None) -> str:
            iri = str(ref.get("iri") or ref.get("uri") or "").strip()
            if not iri:
                return ""
            label = str(ref.get("label") or ref.get("name") or _fragment(iri)).strip()
            if iri.startswith("http://www.w3.org/2001/XMLSchema#"):
                ensure_node(
                    iri=iri,
                    label=label,
                    node_labels=["Datatype"],
                    properties={"namespace": "http://www.w3.org/2001/XMLSchema#"},
                )
            else:
                ensure_node(
                    iri=iri,
                    label=label,
                    node_labels=fallback_labels or ["OntologyClass"],
                )
            return iri

        def ensure_relationship(rel_type: str, start: str, end: str, properties: Optional[Dict[str, Any]] = None) -> None:
            if not start or not end:
                return
            rel_id = f"{rel_type}:{start}:{end}"
            relationships[rel_id] = {
                "elementId": rel_id,
                "type": rel_type,
                "start": start,
                "end": end,
                "properties": {"ontology_prefix": prefix, **(properties or {})},
            }

        for cls_row in reasoning.get("classes", []):
            iri = str(cls_row.get("iri") or cls_row.get("uri") or "").strip()
            ensure_node(
                iri=iri,
                label=str(cls_row.get("label") or _fragment(iri)).strip(),
                node_labels=["OntologyClass"],
                properties={
                    "comment": cls_row.get("definition") or "",
                },
            )

        for prop_row in reasoning.get("object_properties", []):
            iri = str(prop_row.get("iri") or prop_row.get("uri") or "").strip()
            ensure_node(
                iri=iri,
                label=str(prop_row.get("label") or _fragment(iri)).strip(),
                node_labels=["ObjectProperty"],
                properties={"comment": prop_row.get("definition") or ""},
            )
            for domain_ref in prop_row.get("domain", []):
                target = ensure_ref_node(domain_ref, ["OntologyClass"])
                ensure_relationship("DOMAIN", iri, target)
            for range_ref in prop_row.get("range", []):
                target = ensure_ref_node(range_ref, ["OntologyClass"])
                ensure_relationship("RANGE", iri, target)

        for prop_row in reasoning.get("datatype_properties", []):
            iri = str(prop_row.get("iri") or prop_row.get("uri") or "").strip()
            ensure_node(
                iri=iri,
                label=str(prop_row.get("label") or _fragment(iri)).strip(),
                node_labels=["DatatypeProperty"],
                properties={"comment": prop_row.get("definition") or ""},
            )
            for domain_ref in prop_row.get("domain", []):
                target = ensure_ref_node(domain_ref, ["OntologyClass"])
                ensure_relationship("DOMAIN", iri, target)
            for range_ref in prop_row.get("range", []):
                target = ensure_ref_node(range_ref, ["Datatype"])
                ensure_relationship("RANGE", iri, target)

        for edge in reasoning.get("subclass_edges", []):
            child = str(edge.get("source") or "").strip()
            parent = str(edge.get("target") or "").strip()
            ensure_ref_node({"iri": child, "label": edge.get("source_label")}, ["OntologyClass"])
            ensure_ref_node({"iri": parent, "label": edge.get("target_label")}, ["OntologyClass"])
            ensure_relationship("SUBCLASS_OF", child, parent)

        graph = {
            "nodes": sorted(nodes.values(), key=lambda item: (
                str((item.get("labels") or [""])[0]),
                str((item.get("properties") or {}).get("name") or ""),
                str(item.get("elementId") or ""),
            )),
            "relationships": sorted(relationships.values(), key=lambda item: (
                str(item.get("type") or ""),
                str(item.get("start") or ""),
                str(item.get("end") or ""),
            )),
        }
        graph["counts"] = {
            "nodes": len(graph["nodes"]),
            "relationships": len(graph["relationships"]),
        }
        graph["view"] = {"type": "ontology-reasoning", "prefix": prefix}
        return graph

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
                  AND any(label IN labels(n) WHERE label IN $schema_node_labels)
                  AND any(label IN labels(m) WHERE label IN $schema_node_labels)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'DOMAIN'
                  AND any(label IN labels(n) WHERE label IN $schema_node_labels)
                  AND any(label IN labels(m) WHERE label IN $schema_node_labels)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'RANGE'
                  AND any(label IN labels(n) WHERE label IN $schema_node_labels)
                  AND any(label IN labels(m) WHERE label IN $schema_node_labels)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) = 'SUBPROPERTY_OF'
                  AND any(label IN labels(n) WHERE label IN $schema_node_labels)
                  AND any(label IN labels(m) WHERE label IN $schema_node_labels)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)-[r]->(m)
                WHERE type(r) IN ['EQUIVALENT_CLASS', 'DISJOINT_WITH', 'INVERSE_OF', 'ON_PROPERTY', 'SOME_VALUES_FROM', 'ALL_VALUES_FROM', 'HAS_VALUE', 'CLASS_RESTRICTION']
                  AND any(label IN labels(n) WHERE label IN $schema_node_labels)
                  AND any(label IN labels(m) WHERE label IN $schema_node_labels)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND (m.prefix = $prefix OR m.ontology_prefix = $prefix)
                RETURN n, r, m
                ORDER BY coalesce(n.name, n.uri, ''), coalesce(m.name, m.uri, '')
                LIMIT $relationship_slice_limit
              UNION
                MATCH (n)
                WHERE any(label IN labels(n) WHERE label IN $schema_node_labels)
                  AND (n.prefix = $prefix OR n.ontology_prefix = $prefix)
                  AND NOT EXISTS {
                    MATCH (n)-[r]->(m)
                    WHERE type(r) IN $schema_relationship_types
                      AND any(label IN labels(m) WHERE label IN $schema_node_labels)
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
                "schema_node_labels": cls.SCHEMA_NODE_LABELS,
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

            from rdflib import BNode, URIRef
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

            def rdf_term_id(term: Any) -> str:
                if isinstance(term, URIRef):
                    return OntologyUploadManager._term_id(term)
                if isinstance(term, BNode):
                    digest = hashlib.sha1(str(term).encode("utf-8")).hexdigest()[:16]
                    return f"urn:depo:{prefix}:restriction:{digest}"
                return str(term)

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
            datatype_rows_by_uri: Dict[str, Dict[str, Any]] = {}
            for prop in sorted(object_props | datatype_props, key=str):
                prop_uri = OntologyUploadManager._term_id(prop)
                for domain in rdf_graph.objects(prop, RDFS.domain):
                    if isinstance(domain, URIRef):
                        domain_rows.append({"prop_uri": prop_uri, "class_uri": OntologyUploadManager._term_id(domain)})
                for range_term in rdf_graph.objects(prop, RDFS.range):
                    if isinstance(range_term, URIRef):
                        range_uri = OntologyUploadManager._term_id(range_term)
                        if range_term not in class_terms:
                            datatype_rows_by_uri[range_uri] = {
                                "uri": range_uri,
                                "name": labels.get(range_uri) or OntologyUploadManager._local_name(range_term),
                                "namespace": OntologyUploadManager._namespace(range_term),
                                "comment": str(next(rdf_graph.objects(range_term, RDFS.comment), "")),
                            }
                        range_rows.append({"prop_uri": prop_uri, "range_uri": range_uri})

            inverse_rows = [
                {
                    "prop_uri": OntologyUploadManager._term_id(s),
                    "inverse_uri": OntologyUploadManager._term_id(o),
                }
                for s, _, o in rdf_graph.triples((None, OWL.inverseOf, None))
                if isinstance(s, URIRef) and isinstance(o, URIRef)
            ]
            equivalent_rows = [
                {
                    "left_uri": OntologyUploadManager._term_id(s),
                    "right_uri": OntologyUploadManager._term_id(o),
                }
                for s, _, o in rdf_graph.triples((None, OWL.equivalentClass, None))
                if isinstance(s, URIRef) and isinstance(o, URIRef)
            ]
            disjoint_rows = [
                {
                    "left_uri": OntologyUploadManager._term_id(s),
                    "right_uri": OntologyUploadManager._term_id(o),
                }
                for s, _, o in rdf_graph.triples((None, OWL.disjointWith, None))
                if isinstance(s, URIRef) and isinstance(o, URIRef)
            ]

            property_characteristics = []
            for prop in sorted(object_props | datatype_props, key=str):
                flags = {
                    "functional": (prop, RDF.type, OWL.FunctionalProperty) in rdf_graph,
                    "inverse_functional": (prop, RDF.type, OWL.InverseFunctionalProperty) in rdf_graph,
                    "transitive": (prop, RDF.type, OWL.TransitiveProperty) in rdf_graph,
                    "symmetric": (prop, RDF.type, OWL.SymmetricProperty) in rdf_graph,
                }
                if any(flags.values()):
                    property_characteristics.append({
                        "uri": OntologyUploadManager._term_id(prop),
                        **flags,
                    })

            restriction_rows = []
            for cls_term, _, restriction in rdf_graph.triples((None, RDFS.subClassOf, None)):
                if not isinstance(cls_term, URIRef) or (restriction, RDF.type, OWL.Restriction) not in rdf_graph:
                    continue
                restriction_uri = rdf_term_id(restriction)
                on_property = next(rdf_graph.objects(restriction, OWL.onProperty), None)
                row = {
                    "class_uri": OntologyUploadManager._term_id(cls_term),
                    "restriction_uri": restriction_uri,
                    "name": f"{OntologyUploadManager._local_name(cls_term)} restriction",
                    "on_property_uri": rdf_term_id(on_property) if on_property else "",
                    "some_values_from_uri": "",
                    "all_values_from_uri": "",
                    "has_value_uri": "",
                    "min_cardinality": "",
                    "max_cardinality": "",
                    "cardinality": "",
                }
                for predicate, key in (
                    (OWL.someValuesFrom, "some_values_from_uri"),
                    (OWL.allValuesFrom, "all_values_from_uri"),
                    (OWL.hasValue, "has_value_uri"),
                ):
                    target = next(rdf_graph.objects(restriction, predicate), None)
                    if isinstance(target, URIRef):
                        row[key] = rdf_term_id(target)
                for predicate, key in (
                    (OWL.minCardinality, "min_cardinality"),
                    (OWL.maxCardinality, "max_cardinality"),
                    (OWL.cardinality, "cardinality"),
                ):
                    value = next(rdf_graph.objects(restriction, predicate), None)
                    if value is not None:
                        row[key] = str(value)
                restriction_rows.append(row)

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
            datatype_cypher = """
UNWIND $rows AS row
MERGE (d:Datatype {uri: row.uri, prefix: $prefix})
ON CREATE SET d.created_at = datetime()
SET d.name = row.name,
    d.concept_type = 'rdfs:Datatype',
    d.namespace = row.namespace,
    d.comment = row.comment,
    d.source_ontology = $ontology_id,
    d.ontology_name = $ontology_name,
    d.version = $version,
    d.ontology_prefix = $prefix,
    d.schema_type = 'schema',
    d.updated_at = datetime()
RETURN count(d) AS count
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
MATCH (c {uri: row.range_uri, prefix: $prefix})
WHERE c:OntologyClass OR c:Datatype
MERGE (p)-[r:RANGE]->(c)
RETURN count(r) AS count
"""
            inverse_cypher = """
UNWIND $rows AS row
MATCH (p {uri: row.prop_uri, prefix: $prefix})
MATCH (i {uri: row.inverse_uri, prefix: $prefix})
WHERE (p:ObjectProperty OR p:DatatypeProperty) AND (i:ObjectProperty OR i:DatatypeProperty)
MERGE (p)-[r:INVERSE_OF]->(i)
RETURN count(r) AS count
"""
            class_relation_cypher = """
UNWIND $rows AS row
MATCH (left:OntologyClass {uri: row.left_uri, prefix: $prefix})
MATCH (right:OntologyClass {uri: row.right_uri, prefix: $prefix})
MERGE (left)-[r:RELATION_TYPE]->(right)
RETURN count(r) AS count
"""
            equivalent_cypher = class_relation_cypher.replace("RELATION_TYPE", "EQUIVALENT_CLASS")
            disjoint_cypher = class_relation_cypher.replace("RELATION_TYPE", "DISJOINT_WITH")
            property_characteristics_cypher = """
UNWIND $rows AS row
MATCH (p {uri: row.uri, prefix: $prefix})
WHERE p:ObjectProperty OR p:DatatypeProperty
SET p.functional = row.functional,
    p.inverse_functional = row.inverse_functional,
    p.transitive = row.transitive,
    p.symmetric = row.symmetric,
    p.updated_at = datetime()
RETURN count(p) AS count
"""
            restriction_cypher = """
UNWIND $rows AS row
MATCH (c:OntologyClass {uri: row.class_uri, prefix: $prefix})
MERGE (res:Restriction {uri: row.restriction_uri, prefix: $prefix})
ON CREATE SET res.created_at = datetime()
SET res.name = row.name,
    res.concept_type = 'owl:Restriction',
    res.on_property_uri = row.on_property_uri,
    res.some_values_from_uri = row.some_values_from_uri,
    res.all_values_from_uri = row.all_values_from_uri,
    res.has_value_uri = row.has_value_uri,
    res.min_cardinality = row.min_cardinality,
    res.max_cardinality = row.max_cardinality,
    res.cardinality = row.cardinality,
    res.source_ontology = $ontology_id,
    res.ontology_name = $ontology_name,
    res.version = $version,
    res.ontology_prefix = $prefix,
    res.schema_type = 'schema',
    res.updated_at = datetime()
MERGE (c)-[:CLASS_RESTRICTION]->(res)
WITH row, res
OPTIONAL MATCH (p {uri: row.on_property_uri, prefix: $prefix})
WHERE p:ObjectProperty OR p:DatatypeProperty
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (res)-[:ON_PROPERTY]->(p))
WITH row, res
OPTIONAL MATCH (some {uri: row.some_values_from_uri, prefix: $prefix})
WHERE some:OntologyClass OR some:Datatype
FOREACH (_ IN CASE WHEN some IS NULL THEN [] ELSE [1] END | MERGE (res)-[:SOME_VALUES_FROM]->(some))
WITH row, res
OPTIONAL MATCH (allv {uri: row.all_values_from_uri, prefix: $prefix})
WHERE allv:OntologyClass OR allv:Datatype
FOREACH (_ IN CASE WHEN allv IS NULL THEN [] ELSE [1] END | MERGE (res)-[:ALL_VALUES_FROM]->(allv))
RETURN count(res) AS count
"""

            classes_created = run_batch(class_cypher, class_rows)
            object_props_created = run_batch(object_prop_cypher, object_rows)
            datatype_props_created = run_batch(datatype_prop_cypher, datatype_rows)
            datatypes_created = run_batch(datatype_cypher, list(datatype_rows_by_uri.values()))
            subclass_created = run_batch(subclass_cypher, subclass_rows)
            domain_created = run_batch(domain_cypher, domain_rows)
            range_created = run_batch(range_cypher, range_rows)
            inverse_created = run_batch(inverse_cypher, inverse_rows)
            equivalent_created = run_batch(equivalent_cypher, equivalent_rows)
            disjoint_created = run_batch(disjoint_cypher, disjoint_rows)
            run_batch(property_characteristics_cypher, property_characteristics)
            restrictions_created = run_batch(restriction_cypher, restriction_rows)
            relationships_created = (
                subclass_created + domain_created + range_created + inverse_created +
                equivalent_created + disjoint_created + restrictions_created
            )

            return {
                "status": "success",
                "ontology_id": ontology_id,
                "version": version,
                "nodes_merged": classes_created + object_props_created + datatype_props_created + datatypes_created + restrictions_created,
                "relationships_merged": relationships_created,
                "parsed_class_count": len(class_rows),
                "parsed_object_property_count": len(object_rows),
                "parsed_datatype_property_count": len(datatype_rows),
                "parsed_datatype_count": len(datatype_rows_by_uri),
                "parsed_restriction_count": len(restriction_rows),
                "parsed_subclass_relationship_count": len(subclass_rows),
                "parsed_domain_relationship_count": len(domain_rows),
                "parsed_range_relationship_count": len(range_rows),
                "parsed_inverse_relationship_count": len(inverse_rows),
                "parsed_equivalent_class_relationship_count": len(equivalent_rows),
                "parsed_disjoint_relationship_count": len(disjoint_rows),
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
            WITH n, r, m
            ORDER BY
              coalesce(n.ontology_prefix, n.prefix, '') ASC,
              coalesce(n.name, n.title, n.code, labels(n)[0], elementId(n)) ASC,
              type(r) ASC,
              coalesce(m.ontology_prefix, m.prefix, '') ASC,
              coalesce(m.name, m.title, m.code, labels(m)[0], elementId(m)) ASC
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              {elementId: elementId(r), type: type(r), properties: properties(r),
               start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
              {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
            LIMIT $limit
            """,
            {"limit": max(1, min(int(limit), 5000))},
        )
        return cls._filter_graph_nodes(cls.rows_to_graph(rows))

    @classmethod
    def get_virtual_ontology_view(cls, prefix: str, limit: int = 1000) -> Dict[str, Any]:
        prefix = cls._resolve_ontology_prefix(prefix)
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
        if prefix:
            graph_rel_types = {rel.get("type") for rel in graph.get("relationships", [])}
            graph_property_nodes = sum(
                1
                for node in graph.get("nodes", [])
                if "ObjectProperty" in (node.get("labels") or []) or "DatatypeProperty" in (node.get("labels") or [])
            )
            if graph_property_nodes == 0 or not ({"DOMAIN", "RANGE", "SUBCLASS_OF"} & graph_rel_types):
                reasoning_graph = cls._reasoning_projection_graph(prefix)
                if reasoning_graph.get("counts", {}).get("nodes", 0) > graph.get("counts", {}).get("nodes", 0):
                    graph = reasoning_graph
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
        expand_neighbors: bool = False,
        search_mode: str = "best",
    ) -> Dict[str, Any]:
        ontology_prefix = cls._resolve_ontology_prefix(ontology_prefix) if ontology_prefix else ""
        search_mode = str(search_mode or "best").strip().lower()
        is_broader_search = search_mode == "broader"

        part_query = """
        CALL () {
          WITH toLower(trim($search)) AS search_term, $ontology_prefix AS ontology_prefix, $import_id AS import_id
          MATCH (seed)
          WHERE NOT (seed:DatasheetChunk OR seed:GraphChunk)
            AND any(label IN labels(seed) WHERE toLower(label) CONTAINS 'part')
            AND (
              search_term = '' OR
              any(key IN keys(seed) WHERE toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS search_term)
            )
            AND (
              ontology_prefix = '' OR
              seed.ontology_prefix = $ontology_prefix OR seed.prefix = $ontology_prefix
            )
            AND (import_id = '' OR seed.import_id = import_id)
          WITH seed, search_term,
            CASE
              WHEN search_term = '' THEN 0
              WHEN toLower(coalesce(toStringOrNull(seed.id), '')) = search_term THEN 1000
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['uid']), '')) = search_term THEN 990
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['instance_id']), '')) = search_term THEN 980
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['identifier']), '')) = search_term THEN 970
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['name']), '')) = search_term THEN 960
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['title']), '')) = search_term THEN 950
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['code']), '')) = search_term THEN 940
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['label']), '')) = search_term THEN 930
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['display_name']), '')) = search_term THEN 920
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['displayName']), '')) = search_term THEN 920
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['external_id']), '')) = search_term THEN 910
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['externalId']), '')) = search_term THEN 910
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['source_filename']), '')) = search_term THEN 905
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['idref']), '')) = search_term THEN 900
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['href']), '')) = search_term THEN 900
              WHEN any(value IN [
                properties(seed)['id'],
                properties(seed)['uid'],
                properties(seed)['instance_id'],
                properties(seed)['identifier'],
                properties(seed)['name'],
                properties(seed)['title'],
                properties(seed)['code'],
                properties(seed)['label'],
                properties(seed)['display_name'],
                properties(seed)['displayName'],
                properties(seed)['external_id'],
                properties(seed)['externalId'],
                properties(seed)['source_filename'],
                properties(seed)['idref'],
                properties(seed)['href']
              ] WHERE toLower(coalesce(toStringOrNull(value), '')) STARTS WITH search_term) THEN 800
              WHEN any(value IN [
                properties(seed)['id'],
                properties(seed)['uid'],
                properties(seed)['instance_id'],
                properties(seed)['identifier'],
                properties(seed)['name'],
                properties(seed)['title'],
                properties(seed)['code'],
                properties(seed)['label'],
                properties(seed)['display_name'],
                properties(seed)['displayName'],
                properties(seed)['external_id'],
                properties(seed)['externalId'],
                properties(seed)['source_filename'],
                properties(seed)['idref'],
                properties(seed)['href']
              ] WHERE toLower(coalesce(toStringOrNull(value), '')) CONTAINS search_term) THEN 500
              WHEN any(label IN labels(seed) WHERE toLower(label) CONTAINS search_term) THEN 300
              WHEN any(key IN keys(seed) WHERE toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS search_term) THEN 100
              ELSE 0
            END AS score
          WHERE search_term = '' OR score > 0
          RETURN seed, score
          ORDER BY score DESC, toLower(coalesce(
            properties(seed)['name'],
            properties(seed)['title'],
            properties(seed)['label'],
            properties(seed)['code'],
            properties(seed)['id'],
            properties(seed)['uid'],
            ''
          )) ASC, elementId(seed) ASC
          LIMIT CASE WHEN trim($search) = '' OR $search_mode = 'broader' THEN toInteger($limit) ELSE 1 END
        }
        RETURN
          {elementId: elementId(seed), labels: labels(seed), properties: properties(seed)} AS n,
          NULL AS r,
          NULL AS m
        """
        part_rows = cls._run(
            part_query,
            {
                "search": search or "",
                "ontology_prefix": ontology_prefix or "",
                "import_id": import_id or "",
                "limit": max(1, min(int(limit), 2000)),
                "search_mode": search_mode,
            },
        )
        if part_rows and not is_broader_search:
            graph = cls._filter_graph_nodes(cls.rows_to_graph(part_rows), prefer_part_nodes=True)
            graph["view"] = {
                "type": "contextual-subgraph",
                "search": search or "",
                "ontology_prefix": ontology_prefix or "",
                "import_id": import_id or "",
            }
            return graph

        query = """
        CALL () {
          WITH toLower(trim($search)) AS search_term, $ontology_prefix AS ontology_prefix, $import_id AS import_id
          MATCH (seed)
          WHERE NOT (seed:DatasheetChunk OR seed:GraphChunk)
            AND (
              search_term = '' OR
              any(label IN labels(seed) WHERE toLower(label) CONTAINS search_term) OR
              any(key IN keys(seed) WHERE toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS search_term)
            )
            AND (
              ontology_prefix = '' OR
              seed.ontology_prefix = $ontology_prefix OR seed.prefix = $ontology_prefix OR
              EXISTS {
                MATCH (seed)-[typed_rel]->(cls)
                WHERE type(typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (cls.ontology_prefix = ontology_prefix OR cls.prefix = ontology_prefix)
              }
            )
            AND (import_id = '' OR seed.import_id = import_id)
          WITH seed, search_term,
            CASE
              WHEN search_term = '' THEN 0
              WHEN toLower(coalesce(toStringOrNull(seed.id), '')) = search_term THEN 1000
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['uid']), '')) = search_term THEN 990
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['instance_id']), '')) = search_term THEN 980
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['identifier']), '')) = search_term THEN 970
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['name']), '')) = search_term THEN 960
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['title']), '')) = search_term THEN 950
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['code']), '')) = search_term THEN 940
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['label']), '')) = search_term THEN 930
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['display_name']), '')) = search_term THEN 920
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['displayName']), '')) = search_term THEN 920
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['external_id']), '')) = search_term THEN 910
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['externalId']), '')) = search_term THEN 910
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['source_filename']), '')) = search_term THEN 905
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['idref']), '')) = search_term THEN 900
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['href']), '')) = search_term THEN 900
              WHEN any(value IN [
                properties(seed)['id'],
                properties(seed)['uid'],
                properties(seed)['instance_id'],
                properties(seed)['identifier'],
                properties(seed)['name'],
                properties(seed)['title'],
                properties(seed)['code'],
                properties(seed)['label'],
                properties(seed)['display_name'],
                properties(seed)['displayName'],
                properties(seed)['external_id'],
                properties(seed)['externalId'],
                properties(seed)['source_filename'],
                properties(seed)['idref'],
                properties(seed)['href']
              ] WHERE toLower(coalesce(toStringOrNull(value), '')) STARTS WITH search_term) THEN 800
              WHEN any(value IN [
                properties(seed)['id'],
                properties(seed)['uid'],
                properties(seed)['instance_id'],
                properties(seed)['identifier'],
                properties(seed)['name'],
                properties(seed)['title'],
                properties(seed)['code'],
                properties(seed)['label'],
                properties(seed)['display_name'],
                properties(seed)['displayName'],
                properties(seed)['external_id'],
                properties(seed)['externalId'],
                properties(seed)['source_filename'],
                properties(seed)['idref'],
                properties(seed)['href']
              ] WHERE toLower(coalesce(toStringOrNull(value), '')) CONTAINS search_term) THEN 500
              WHEN any(label IN labels(seed) WHERE toLower(label) CONTAINS search_term) THEN 300
              WHEN any(key IN keys(seed) WHERE toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS search_term) THEN 100
              ELSE 0
            END AS score
          WHERE search_term = '' OR score > 0
          RETURN seed, score
          ORDER BY score DESC, toLower(coalesce(
            properties(seed)['name'],
            properties(seed)['title'],
            properties(seed)['label'],
            properties(seed)['code'],
            properties(seed)['id'],
            properties(seed)['uid'],
            ''
          )) ASC, elementId(seed) ASC
          LIMIT CASE WHEN trim($search) = '' OR $search_mode = 'broader' THEN toInteger($limit) ELSE 1 END
        UNION
          WITH toLower(trim($search)) AS search_term, $ontology_prefix AS ontology_prefix, $import_id AS import_id
          MATCH (a)-[matched_rel]-(b)
          WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk)
            AND (
              search_term = '' OR
              toLower(type(matched_rel)) CONTAINS search_term OR
              any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) CONTAINS search_term)
            )
            AND (
              ontology_prefix = '' OR
              a.ontology_prefix = ontology_prefix OR a.prefix = ontology_prefix OR
              b.ontology_prefix = ontology_prefix OR b.prefix = ontology_prefix OR
              EXISTS {
                MATCH (a)-[a_typed_rel]->(a_cls)
                WHERE type(a_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (a_cls.ontology_prefix = ontology_prefix OR a_cls.prefix = ontology_prefix)
              } OR
              EXISTS {
                MATCH (b)-[b_typed_rel]->(b_cls)
                WHERE type(b_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (b_cls.ontology_prefix = ontology_prefix OR b_cls.prefix = ontology_prefix)
              }
            )
            AND (import_id = '' OR a.import_id = import_id OR b.import_id = import_id)
          WITH a AS seed, search_term,
            CASE
              WHEN search_term = '' THEN 0
              WHEN toLower(type(matched_rel)) = search_term THEN 850
              WHEN toLower(type(matched_rel)) STARTS WITH search_term THEN 650
              WHEN toLower(type(matched_rel)) CONTAINS search_term THEN 450
              WHEN any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) = search_term) THEN 700
              WHEN any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) STARTS WITH search_term) THEN 500
              WHEN any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) CONTAINS search_term) THEN 250
              ELSE 0
            END AS score
          WHERE search_term = '' OR score > 0
          RETURN seed, score
          ORDER BY score DESC, toLower(coalesce(
            properties(seed)['name'],
            properties(seed)['title'],
            properties(seed)['label'],
            properties(seed)['code'],
            properties(seed)['id'],
            properties(seed)['uid'],
            ''
          )) ASC, elementId(seed) ASC
          LIMIT CASE WHEN trim($search) = '' OR $search_mode = 'broader' THEN toInteger($limit) ELSE 1 END
        UNION
          WITH toLower(trim($search)) AS search_term, $ontology_prefix AS ontology_prefix, $import_id AS import_id
          MATCH (a)-[matched_rel]-(b)
          WHERE NOT (a:DatasheetChunk OR a:GraphChunk OR b:DatasheetChunk OR b:GraphChunk)
            AND (
              search_term = '' OR
              toLower(type(matched_rel)) CONTAINS search_term OR
              any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) CONTAINS search_term)
            )
            AND (
              ontology_prefix = '' OR
              a.ontology_prefix = ontology_prefix OR a.prefix = ontology_prefix OR
              b.ontology_prefix = ontology_prefix OR b.prefix = ontology_prefix OR
              EXISTS {
                MATCH (a)-[a_typed_rel]->(a_cls)
                WHERE type(a_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (a_cls.ontology_prefix = ontology_prefix OR a_cls.prefix = ontology_prefix)
              } OR
              EXISTS {
                MATCH (b)-[b_typed_rel]->(b_cls)
                WHERE type(b_typed_rel) IN ['INSTANCE_OF', 'TYPED_BY', 'CLASSIFIED_AS']
                  AND (b_cls.ontology_prefix = ontology_prefix OR b_cls.prefix = ontology_prefix)
              }
            )
            AND (import_id = '' OR a.import_id = import_id OR b.import_id = import_id)
          WITH b AS seed, search_term,
            CASE
              WHEN search_term = '' THEN 0
              WHEN toLower(type(matched_rel)) = search_term THEN 850
              WHEN toLower(type(matched_rel)) STARTS WITH search_term THEN 650
              WHEN toLower(type(matched_rel)) CONTAINS search_term THEN 450
              WHEN any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) = search_term) THEN 700
              WHEN any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) STARTS WITH search_term) THEN 500
              WHEN any(key IN keys(matched_rel) WHERE toLower(coalesce(toStringOrNull(matched_rel[key]), '')) CONTAINS search_term) THEN 250
              ELSE 0
            END AS score
          WHERE search_term = '' OR score > 0
          RETURN seed, score
          ORDER BY score DESC, toLower(coalesce(
            properties(seed)['name'],
            properties(seed)['title'],
            properties(seed)['label'],
            properties(seed)['code'],
            properties(seed)['id'],
            properties(seed)['uid'],
            ''
          )) ASC, elementId(seed) ASC
          LIMIT CASE WHEN trim($search) = '' OR $search_mode = 'broader' THEN toInteger($limit) ELSE 1 END
        }
        WITH seed, max(score) AS score
        ORDER BY score DESC, toLower(coalesce(
          properties(seed)['name'],
          properties(seed)['title'],
          properties(seed)['label'],
          properties(seed)['code'],
          properties(seed)['id'],
          properties(seed)['uid'],
          ''
        )) ASC, elementId(seed) ASC
          LIMIT CASE WHEN trim($search) = '' OR $search_mode = 'broader' THEN toInteger($limit) ELSE 1 END
        """
        if expand_neighbors:
            query += """
        OPTIONAL MATCH (seed)-[r]-(adjacent)
        WHERE adjacent IS NULL OR NOT (adjacent:DatasheetChunk OR adjacent:GraphChunk)
        WITH seed, r, adjacent
        LIMIT CASE WHEN trim($search) = '' THEN toInteger($limit) ELSE 80 END
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
        else:
            query += """
        RETURN
          {elementId: elementId(seed), labels: labels(seed), properties: properties(seed)} AS n,
          NULL AS r,
          NULL AS m
        """
        rows = cls._run(
            query,
            {
                "search": search or "",
                "ontology_prefix": ontology_prefix or "",
                "import_id": import_id or "",
                "limit": max(1, min(int(limit), 2000)),
                "expand_neighbors": bool(expand_neighbors),
                "search_mode": search_mode,
            },
        )
        graph = cls._filter_graph_nodes(cls.rows_to_graph(rows), prefer_part_nodes=True)
        graph["view"] = {
            "type": "contextual-subgraph",
            "search": search or "",
            "ontology_prefix": ontology_prefix or "",
            "import_id": import_id or "",
        }
        return graph
