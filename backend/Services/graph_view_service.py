"""Official-driver graph view services for visualization and contextual subgraphs."""

from __future__ import annotations

import hashlib
import logging
import re
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

    INSTANCE_NODE_LABELS = [
        "Individual",
        "Product",
        "ProductRevision",
        "Part",
        # STEP/AP242 Part21 and Part28/STPX labels are often uppercase.
        "PRODUCT",
        "PRODUCT_DEFINITION",
        "PRODUCT_DEFINITION_FORMATION",
        "PRODUCT_DEFINITION_SHAPE",
        "SHAPE_REPRESENTATION",
        "SHAPE_ASPECT",
        "SHAPE_ASPECT_RELATIONSHIP",
        "SHAPE_DEFINITION_REPRESENTATION",
        "FEATURE_COMPONENT_DEFINITION",
        "INSTANCED_FEATURE",
        "FEATURE_PATTERN",
        "ADVANCED_BREP_SHAPE_REPRESENTATION",
        "PART",
        "PART_VERSION",
        "PART_VIEW",
        "VIEW",
        "VIEWS",
        "GEOMETRIC_MODEL",
        "OCCURRENCE",
        "VIEW_OCCURRENCE_RELATIONSHIP",
        "PLACEMENT",
        "CARTESIAN_TRANSFORMATION",
        "ROTATION_MATRIX",
        "TRANSLATION_VECTOR",
        "GEOMETRIC_TOLERANCE",
        "PLUS_MINUS_TOLERANCE",
        "TOLERANCE_VALUE",
        "DATUM_FEATURE",
        "DATUM_TARGET",
        "DATUM_REFERENCE",
        "DIMENSIONAL_SIZE",
        "DIMENSIONAL_LOCATION",
        "ANGULAR_LOCATION",
        "ANNOTATION_TEXT_OCCURRENCE",
        "DRAUGHTING_CALLOUT",
        "PRESENTATION_STYLE_ASSIGNMENT",
        "TEXT_LITERAL",
        "LEADER_CURVE",
        "STYLED_ITEM",
        "SURFACE_TEXTURE_REPRESENTATION",
        "Requirement",
        "RequirementRevision",
        "Occurrence",
        "InstanceGraph",
        "ProductInstance",
        "ProcessInstance",
        "Document",
        "Site",
    ]

    INSTANCE_SEMANTIC_ROLES = [
        "entity",
        "product",
        "shape",
        "feature",
        "representation",
        "topology",
        "geometry",
        "dimension_tolerance",
        "geometric_tolerance",
        "datum",
        "dimension",
        "annotation",
        "surface_finish",
    ]

    RELATIONSHIP_NODE_LABELS = [
        "GeneralRelation",
        "Connection",
        "ConnectionInstance",
        "ConnectionRevision",
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
    def _normalize_search_term(value: str) -> str:
        normalized = re.sub(r"\*+", "", str(value or "")).strip().lower()
        return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", normalized)

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
        labels = {str(label or "").lower() for label in (node.get("labels") or [])}
        element_type = str(props.get("element_type") or "").strip().lower()
        semantic_role = str(props.get("semantic_role") or "").strip().lower()
        is_cad_business_object = bool(props.get("is_cad_business_object"))
        display_name = _first_text_value(
            props,
            ("name", "title", "label", "display_name", "displayName", "id", "uid"),
        ).strip()
        metadata_markers = {
            "userdata",
            "form",
            "accessintent",
            "associatedattachment",
            "applicationref",
            "plaintext",
            "description",
            "uservalue",
        }

        if semantic_role == "entity":
            return False
        if is_cad_business_object:
            return False
        if semantic_role in GraphViewService.INSTANCE_SEMANTIC_ROLES and not GraphViewService._is_schema_node(node):
            return False
        if labels.intersection({label.lower() for label in GraphViewService.RELATIONSHIP_NODE_LABELS}):
            return True
        if semantic_role in {"metadata", "structural", "relationship"}:
            return True
        if element_type in metadata_markers:
            return True
        if re.fullmatch(r"id\d+", display_name, flags=re.IGNORECASE):
            return True
        return bool(labels.intersection(metadata_markers))

    @staticmethod
    def _is_part_node(node: Dict[str, Any]) -> bool:
        labels = [str(label or "").lower() for label in (node.get("labels") or [])]
        return any("part" in label for label in labels)

    @staticmethod
    def _is_individual_node(node: Dict[str, Any]) -> bool:
        labels = {str(label or "") for label in (node.get("labels") or [])}
        props = node.get("properties") or {}
        semantic_role = str(props.get("semantic_role") or "").strip().lower()
        is_cad_business_object = bool(props.get("is_cad_business_object"))
        if labels.intersection(set(GraphViewService.RELATIONSHIP_NODE_LABELS)) or semantic_role == 'relationship':
            return False
        if labels and labels.intersection(GraphViewService.INSTANCE_NODE_LABELS):
            return True
        if is_cad_business_object and not GraphViewService._is_schema_node(node):
            return True
        if semantic_role in GraphViewService.INSTANCE_SEMANTIC_ROLES and not GraphViewService._is_schema_node(node):
            return True
        return False

    @classmethod
    def _is_schema_node(cls, node: Dict[str, Any]) -> bool:
        labels = {str(label or "") for label in (node.get("labels") or [])}
        return bool(labels.intersection(cls.SCHEMA_NODE_LABELS))

    @classmethod
    def _filter_graph_nodes(
        cls,
        graph: Dict[str, Any],
        *,
        prefer_part_nodes: bool = False,
        only_individual_nodes: bool = False,
    ) -> Dict[str, Any]:
        nodes = [node for node in (graph.get("nodes") or []) if node.get("elementId")]
        relationships = [rel for rel in (graph.get("relationships") or []) if rel.get("elementId")]

        filtered_nodes = [node for node in nodes if not cls._is_metadata_like_node(node)]
        if only_individual_nodes:
            filtered_nodes = [node for node in filtered_nodes if cls._is_individual_node(node)]
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
                from backend.Services.ontology_reasoning_service import OntologyReasoningService
            except Exception:
                from Services.ontology_reasoning_service import OntologyReasoningService

            reasoning = OntologyReasoningService.get_reasoning(prefix)
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
            CALL () {
              MATCH (n)-[r]->(m)
              WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
                AND NOT any(label IN labels(n) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(m) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(n) WHERE label IN $relationship_node_labels)
                AND NOT any(label IN labels(m) WHERE label IN $relationship_node_labels)
                AND (
                  any(label IN labels(n) WHERE label IN $instance_node_labels)
                  OR coalesce(n.is_cad_business_object, false) = true
                  OR coalesce(n.semantic_role, '') IN $semantic_instance_roles
                )
                AND (
                  any(label IN labels(m) WHERE label IN $instance_node_labels)
                  OR coalesce(m.is_cad_business_object, false) = true
                  OR coalesce(m.semantic_role, '') IN $semantic_instance_roles
                )
              RETURN n, r, m
              LIMIT $direct_limit
              UNION
              MATCH (n)--(bridge)--(m)
              WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
                AND any(label IN labels(bridge) WHERE label IN $relationship_node_labels)
                AND NOT any(label IN labels(n) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(m) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(n) WHERE label IN $relationship_node_labels)
                AND NOT any(label IN labels(m) WHERE label IN $relationship_node_labels)
                AND elementId(n) < elementId(m)
                AND (
                  any(label IN labels(n) WHERE label IN $instance_node_labels)
                  OR coalesce(n.is_cad_business_object, false) = true
                  OR coalesce(n.semantic_role, '') IN $semantic_instance_roles
                )
                AND (
                  any(label IN labels(m) WHERE label IN $instance_node_labels)
                  OR coalesce(m.is_cad_business_object, false) = true
                  OR coalesce(m.semantic_role, '') IN $semantic_instance_roles
                )
              WITH n, bridge, m
              RETURN n,
                {
                  elementId: 'bridge:' + elementId(bridge) + ':' + elementId(n) + ':' + elementId(m),
                  type: coalesce(properties(bridge)['element_type'], properties(bridge)['relationship_type'], properties(bridge)['name'], labels(bridge)[0], 'RELATED'),
                  properties: properties(bridge),
                  start: elementId(n),
                  end: elementId(m)
                } AS r,
                m
              LIMIT $bridge_limit
            }
            WITH n, r, m
            ORDER BY
              CASE WHEN coalesce(n.semantic_role, '') IN $semantic_instance_roles THEN 0 ELSE 1 END ASC,
              coalesce(n.ontology_prefix, n.prefix, '') ASC,
              coalesce(n.name, n.title, properties(n)['code'], labels(n)[0], elementId(n)) ASC,
              coalesce(r.type, '') ASC,
              coalesce(m.ontology_prefix, m.prefix, '') ASC,
              coalesce(m.name, m.title, properties(m)['code'], labels(m)[0], elementId(m)) ASC
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              r,
              {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
            LIMIT $limit
            """,
            {
                "limit": max(1, min(int(limit), 5000)),
                "direct_limit": max(1, min(int(limit), 5000)) // 2,
                "bridge_limit": max(1, min(int(limit), 5000)),
                "schema_node_labels": cls.SCHEMA_NODE_LABELS,
                "instance_node_labels": cls.INSTANCE_NODE_LABELS,
                "semantic_instance_roles": cls.INSTANCE_SEMANTIC_ROLES,
                "relationship_node_labels": cls.RELATIONSHIP_NODE_LABELS,
            },
        )
        graph = cls._filter_graph_nodes(cls.rows_to_graph(rows), only_individual_nodes=True)
        graph["view"] = {"type": "overview", "scope": "business-instances"}
        return graph

    @staticmethod
    def _list_property(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "").strip()]
        text = str(value or "").strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                import json
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if str(item or "").strip()]
            except Exception:
                pass
        return [part.strip() for part in re.split(r"[,;|]", text) if part.strip()]

    @classmethod
    def _architecture_representations(cls, graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build selectable ArchiMate diagram/view representations.

        Preferred source is explicit View nodes plus VIEW_CONTAINS edges. Older
        imports may only carry primary_view_id metadata on elements/relations,
        so that metadata is kept as a fallback.
        """
        by_view: Dict[str, Dict[str, Any]] = {}
        element_to_archimate_id: Dict[str, str] = {}
        archimate_to_element: Dict[str, str] = {}
        relationship_to_archimate_id: Dict[str, str] = {}
        archimate_rel_to_element: Dict[str, str] = {}

        for node in graph.get("nodes") or []:
            element_id = str(node.get("elementId") or "")
            props = node.get("properties") or {}
            archimate_id = str(props.get("archimate_id") or props.get("id") or "")
            if element_id and archimate_id:
                element_to_archimate_id[element_id] = archimate_id
                archimate_to_element.setdefault(archimate_id, element_id)
            node_type = str(props.get("element_type") or props.get("archimate_type") or "")
            labels = {str(label or "") for label in (node.get("labels") or [])}
            if node_type == "View" or "View" in labels:
                view_id = archimate_id or element_id
                if view_id:
                    by_view.setdefault(view_id, {
                        "id": view_id,
                        "name": str(props.get("name") or props.get("label") or view_id),
                        "type": "ArchiMate View",
                        "nodeIds": [],
                        "relationshipIds": [],
                    })

        for rel in graph.get("relationships") or []:
            rel_element_id = str(rel.get("elementId") or "")
            props = rel.get("properties") or {}
            archimate_id = str(props.get("archimate_id") or props.get("id") or "")
            if rel_element_id and archimate_id:
                relationship_to_archimate_id[rel_element_id] = archimate_id
                archimate_rel_to_element.setdefault(archimate_id, rel_element_id)

        for rel in graph.get("relationships") or []:
            rel_type = str(rel.get("type") or "")
            props = rel.get("properties") or {}
            if rel_type == "VIEW_CONTAINS":
                view_element = str(rel.get("start") or "")
                target_element = str(rel.get("end") or "")
                view_id = element_to_archimate_id.get(view_element, view_element)
                if not view_id or not target_element:
                    continue
                entry = by_view.setdefault(view_id, {
                    "id": view_id,
                    "name": view_id,
                    "type": "ArchiMate View",
                    "nodeIds": [],
                    "relationshipIds": [],
                })
                if target_element not in entry["nodeIds"]:
                    entry["nodeIds"].append(target_element)
                continue

            for view_id in cls._list_property(props.get("archimate_view_ids") or props.get("primary_view_id")):
                entry = by_view.setdefault(view_id, {
                    "id": view_id,
                    "name": str(props.get("primary_view_name") or view_id),
                    "type": "ArchiMate View",
                    "nodeIds": [],
                    "relationshipIds": [],
                })
                rel_id = str(rel.get("elementId") or "")
                if rel_id and rel_id not in entry["relationshipIds"]:
                    entry["relationshipIds"].append(rel_id)
                for endpoint in (rel.get("start"), rel.get("end")):
                    if endpoint and endpoint not in entry["nodeIds"]:
                        entry["nodeIds"].append(endpoint)

        for node in graph.get("nodes") or []:
            props = node.get("properties") or {}
            for view_id in cls._list_property(props.get("archimate_view_ids") or props.get("primary_view_id")):
                entry = by_view.setdefault(view_id, {
                    "id": view_id,
                    "name": str(props.get("primary_view_name") or view_id),
                    "type": "ArchiMate View",
                    "nodeIds": [],
                    "relationshipIds": [],
                })
                node_id = str(node.get("elementId") or "")
                if node_id and node_id not in entry["nodeIds"]:
                    entry["nodeIds"].append(node_id)

        for entry in by_view.values():
            node_set = set(entry.get("nodeIds") or [])
            for rel in graph.get("relationships") or []:
                rel_id = str(rel.get("elementId") or "")
                if rel.get("start") in node_set and rel.get("end") in node_set and str(rel.get("type") or "") != "VIEW_CONTAINS":
                    if rel_id and rel_id not in entry["relationshipIds"]:
                        entry["relationshipIds"].append(rel_id)

        return sorted(
            by_view.values(),
            key=lambda item: (-len(item.get("nodeIds") or []), str(item.get("name") or item.get("id") or "")),
        )

    @classmethod
    def get_architecture_process_view(cls, prefix: str = "archimate", limit: int = 1000) -> Dict[str, Any]:
        """Return connected architecture/process model nodes for an imported ArchiMate graph."""
        prefix = str(prefix or "archimate").strip() or "archimate"
        rows = cls._run(
            """
            CALL () {
              MATCH (n)-[r]->(m)
              WITH n, r, m, properties(n) AS np, properties(m) AS mp
              WHERE NOT (n:DatasheetChunk OR n:GraphChunk OR m:DatasheetChunk OR m:GraphChunk)
                AND NOT any(label IN labels(n) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(m) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(n) WHERE label IN $relationship_node_labels)
                AND NOT any(label IN labels(m) WHERE label IN $relationship_node_labels)
                AND coalesce(np['ontology_prefix'], np['prefix'], np['source_format'], '') = $prefix
                AND coalesce(mp['ontology_prefix'], mp['prefix'], mp['source_format'], '') = $prefix
              RETURN n, r, m, np, mp
              ORDER BY
                coalesce(np['model_name'], '') ASC,
                coalesce(np['name'], np['label'], labels(n)[0], elementId(n)) ASC,
                type(r) ASC,
                coalesce(mp['name'], mp['label'], labels(m)[0], elementId(m)) ASC
              LIMIT $limit
              UNION
              MATCH (n)
              WITH n, properties(n) AS np
              WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
                AND NOT any(label IN labels(n) WHERE label IN $schema_node_labels)
                AND NOT any(label IN labels(n) WHERE label IN $relationship_node_labels)
                AND coalesce(np['ontology_prefix'], np['prefix'], np['source_format'], '') = $prefix
                AND NOT (n)--()
              RETURN n, null AS r, null AS m, np, {} AS mp
              ORDER BY coalesce(np['name'], np['label'], labels(n)[0], elementId(n)) ASC
              LIMIT $limit
            }
            RETURN
              {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
              CASE WHEN r IS NULL THEN null ELSE {elementId: elementId(r), type: type(r), properties: properties(r), start: elementId(startNode(r)), end: elementId(endNode(r))} END AS r,
              CASE WHEN m IS NULL THEN null ELSE {elementId: elementId(m), labels: labels(m), properties: properties(m)} END AS m
            """,
            {
                "prefix": prefix,
                "limit": max(1, min(int(limit), 5000)),
                "schema_node_labels": cls.SCHEMA_NODE_LABELS,
                "relationship_node_labels": cls.RELATIONSHIP_NODE_LABELS,
            },
        )
        graph = cls._filter_graph_nodes(cls.rows_to_graph(rows))
        graph["representations"] = cls._architecture_representations(graph)
        graph["view"] = {"type": "architecture-process", "prefix": prefix, "representation_count": len(graph["representations"])}
        return graph

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
        search_limit = max(1, min(int(limit), 2000))
        raw_search = str(search or "")
        normalized_search = cls._normalize_search_term(raw_search)
        wildcard_prefix_search = "*" in raw_search

        if not normalized_search:
            return {
                "nodes": [],
                "relationships": [],
                "counts": {"nodes": 0, "relationships": 0},
                "view": {
                    "type": "contextual-subgraph",
                    "search": raw_search,
                    "ontology_prefix": ontology_prefix or "",
                    "import_id": import_id or "",
                },
            }

        neighbor_match = """
        CALL (seed) {
          OPTIONAL MATCH (seed)-[direct_rel]-(direct_adjacent)
          WHERE direct_adjacent IS NULL OR (
            NOT (direct_adjacent:DatasheetChunk OR direct_adjacent:GraphChunk)
            AND NOT any(label IN labels(direct_adjacent) WHERE label IN $relationship_node_labels)
            AND (
              any(label IN labels(direct_adjacent) WHERE label IN $instance_node_labels)
              OR coalesce(direct_adjacent.is_cad_business_object, false) = true
              OR coalesce(direct_adjacent.semantic_role, '') IN $semantic_instance_roles
            )
          )
          RETURN direct_rel AS r, direct_adjacent AS adjacent, NULL AS r_payload
          UNION
          MATCH (seed)--(bridge)--(bridge_adjacent)
          WHERE NOT (bridge:DatasheetChunk OR bridge:GraphChunk OR bridge_adjacent:DatasheetChunk OR bridge_adjacent:GraphChunk)
            AND any(label IN labels(bridge) WHERE label IN $relationship_node_labels)
            AND NOT any(label IN labels(bridge_adjacent) WHERE label IN $relationship_node_labels)
            AND (
              any(label IN labels(bridge_adjacent) WHERE label IN $instance_node_labels)
              OR coalesce(bridge_adjacent.is_cad_business_object, false) = true
              OR coalesce(bridge_adjacent.semantic_role, '') IN $semantic_instance_roles
            )
          RETURN NULL AS r,
          bridge_adjacent AS adjacent,
          {
            elementId: 'bridge:' + elementId(bridge) + ':' + elementId(seed) + ':' + elementId(bridge_adjacent),
            type: coalesce(properties(bridge)['element_type'], properties(bridge)['relationship_type'], properties(bridge)['name'], labels(bridge)[0], 'RELATED'),
            properties: properties(bridge),
            start: elementId(seed),
            end: elementId(bridge_adjacent)
          } AS r_payload
        }
        WITH seed, r, adjacent, r_payload
        """ if expand_neighbors else """
        WITH seed, NULL AS r, NULL AS adjacent, NULL AS r_payload
        """

        query = """
        CALL () {
          WITH toLower(trim($search)) AS search_term,
               $ontology_prefix AS ontology_prefix,
               $import_id AS import_id,
               $wildcard_prefix_search AS wildcard_prefix_search
        MATCH (seed)
        WHERE NOT (seed:DatasheetChunk OR seed:GraphChunk)
            AND (
              any(label IN labels(seed) WHERE label IN $instance_node_labels)
              OR coalesce(seed.is_cad_business_object, false) = true
              OR coalesce(seed.semantic_role, '') IN $semantic_instance_roles
            )
            AND NOT any(label IN labels(seed) WHERE label IN $relationship_node_labels)
            AND (
              search_term = '' OR
              CASE
                WHEN wildcard_prefix_search THEN
                  toLower(elementId(seed)) STARTS WITH search_term OR
                  any(value IN [
                    properties(seed)['id'],
                    properties(seed)['uid'],
                    properties(seed)['instance_id'],
                    properties(seed)['identifier'],
                    properties(seed)['catalogue_id'],
                    properties(seed)['requirement_id'],
                    properties(seed)['requirement_ref'],
                    properties(seed)['code'],
                    properties(seed)['external_id'],
                    properties(seed)['externalId']
                  ] WHERE toLower(coalesce(toStringOrNull(value), '')) STARTS WITH search_term)
                ELSE
                  toLower(elementId(seed)) CONTAINS search_term OR
                  any(key IN keys(seed) WHERE
                    toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS search_term
                  )
              END
            )
            AND (
              ontology_prefix = '' OR
              seed.ontology_prefix = ontology_prefix OR
              seed.prefix = ontology_prefix OR
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
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['catalogue_id']), '')) = search_term THEN 1300
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['requirement_id']), '')) = search_term THEN 1290
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['requirement_ref']), '')) = search_term THEN 1280
              WHEN toLower(elementId(seed)) = search_term THEN 1010
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
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['part_type']), '')) = search_term THEN 890
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['element_type']), '')) = search_term THEN 880
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['catalogue_id']), '')) STARTS WITH search_term THEN 1270
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['requirement_id']), '')) STARTS WITH search_term THEN 1260
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['requirement_ref']), '')) STARTS WITH search_term THEN 1250
              WHEN any(value IN [
                properties(seed)['id'],
                properties(seed)['uid'],
                properties(seed)['instance_id'],
                properties(seed)['identifier'],
                properties(seed)['catalogue_id'],
                properties(seed)['requirement_id'],
                properties(seed)['requirement_ref'],
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
                properties(seed)['href'],
                properties(seed)['part_type'],
                properties(seed)['element_type']
              ] WHERE toLower(coalesce(toStringOrNull(value), '')) STARTS WITH search_term) THEN 800
              WHEN any(value IN [
                properties(seed)['id'],
                properties(seed)['uid'],
                properties(seed)['instance_id'],
                properties(seed)['identifier'],
                properties(seed)['catalogue_id'],
                properties(seed)['requirement_id'],
                properties(seed)['requirement_ref'],
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
                properties(seed)['href'],
                properties(seed)['part_type'],
                properties(seed)['element_type']
              ] WHERE toLower(coalesce(toStringOrNull(value), '')) CONTAINS search_term) THEN 500
              WHEN toLower(elementId(seed)) STARTS WITH search_term THEN 450
              WHEN toLower(elementId(seed)) CONTAINS search_term THEN 400
              WHEN any(key IN keys(seed) WHERE toLower(coalesce(toStringOrNull(seed[key]), '')) CONTAINS search_term) THEN 100
              ELSE 0
            END AS score
          WHERE search_term = '' OR score > 0
          RETURN DISTINCT seed AS seed, score AS score, search_term AS search_term
          ORDER BY score DESC,
            CASE
              WHEN any(label IN labels(seed) WHERE label IN ['Requirement', 'RequirementRevision']) THEN 4
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['catalogue_id']), '')) STARTS WITH search_term THEN 4
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['requirement_id']), '')) STARTS WITH search_term THEN 4
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['requirement_ref']), '')) STARTS WITH search_term THEN 4
              WHEN any(label IN labels(seed) WHERE label IN ['Part', 'Product', 'ProductRevision']) THEN 3
              WHEN toLower(coalesce(toStringOrNull(properties(seed)['part_type']), '')) CONTAINS 'requirement' THEN 2
              WHEN coalesce(seed.is_cad_business_object, false) = true THEN 2
              WHEN coalesce(seed.semantic_role, '') IN $semantic_instance_roles THEN 1
              ELSE 0
            END DESC,
            toLower(coalesce(
            properties(seed)['name'],
            properties(seed)['title'],
            properties(seed)['label'],
            properties(seed)['code'],
            properties(seed)['id'],
            properties(seed)['uid'],
            ''
          )) ASC, elementId(seed) ASC
          LIMIT CASE
            WHEN $expand_neighbors THEN 1
            WHEN $search_mode = 'broader' THEN toInteger($limit)
            ELSE 1
          END
        }
        WITH collect(DISTINCT seed) AS seeds
        UNWIND seeds AS seed
        __NEIGHBOR_MATCH__
        LIMIT CASE WHEN trim($search) = '' THEN toInteger($limit) ELSE 80 END
        RETURN
          {
            elementId: elementId(seed),
            labels: labels(seed),
            properties: properties(seed),
            can_traverse: EXISTS {
              MATCH (seed)-[]-(candidate)
              WHERE NOT (candidate:DatasheetChunk OR candidate:GraphChunk)
                AND (
                  any(label IN labels(candidate) WHERE label IN $instance_node_labels)
                  OR coalesce(candidate.is_cad_business_object, false) = true
                  OR coalesce(candidate.semantic_role, '') IN $semantic_instance_roles
                )
            }
          } AS n,
          CASE
            WHEN r_payload IS NOT NULL THEN r_payload
            WHEN r IS NOT NULL THEN {
            elementId: elementId(r), type: type(r), properties: properties(r),
            start: elementId(startNode(r)), end: elementId(endNode(r))
            }
            ELSE NULL
          END AS r,
          CASE WHEN adjacent IS NOT NULL THEN {
            elementId: elementId(adjacent),
            labels: labels(adjacent),
            properties: properties(adjacent),
            can_traverse: CASE
              WHEN any(label IN labels(adjacent) WHERE label IN $instance_node_labels)
                OR coalesce(adjacent.is_cad_business_object, false) = true
                OR coalesce(adjacent.semantic_role, '') IN $semantic_instance_roles THEN EXISTS {
                MATCH (adjacent)-[]-(candidate)
                WHERE NOT (candidate:DatasheetChunk OR candidate:GraphChunk)
                  AND (
                    any(label IN labels(candidate) WHERE label IN $instance_node_labels)
                    OR coalesce(candidate.is_cad_business_object, false) = true
                    OR coalesce(candidate.semantic_role, '') IN $semantic_instance_roles
                  )
              }
              ELSE false
            END
          } ELSE NULL END AS m
        """.replace("__NEIGHBOR_MATCH__", neighbor_match)
        rows = cls._run(
            query,
            {
                "search": normalized_search,
                "ontology_prefix": ontology_prefix or "",
                "import_id": import_id or "",
                "limit": search_limit,
                "expand_neighbors": bool(expand_neighbors),
                "wildcard_prefix_search": bool(wildcard_prefix_search),
                "search_mode": search_mode,
                "schema_node_labels": cls.SCHEMA_NODE_LABELS,
                "instance_node_labels": cls.INSTANCE_NODE_LABELS,
                "semantic_instance_roles": cls.INSTANCE_SEMANTIC_ROLES,
                "relationship_node_labels": cls.RELATIONSHIP_NODE_LABELS,
            },
        )
        graph = cls._filter_graph_nodes(cls.rows_to_graph(rows), only_individual_nodes=True)
        root_node = (graph.get("nodes") or [None])[0]
        graph["view"] = {
            "type": "contextual-subgraph",
            "search": raw_search,
            "ontology_prefix": ontology_prefix or "",
            "import_id": import_id or "",
            "root_node_id": root_node.get("elementId") if root_node else None,
        }
        graph["root"] = root_node
        return graph

    @classmethod
    def get_traversal_slice(
        cls,
        *,
        node_id: str,
        limit: int = 120,
        depth: int = 1,
    ) -> Dict[str, Any]:
        row_limit = max(20, min(int(limit or 120), 300))
        traversal_depth = 2 if int(depth or 1) >= 2 else 1
        node_projection = """
          {
            elementId: elementId($node_var),
            labels: labels($node_var),
            properties: properties($node_var),
            can_traverse: EXISTS {
              MATCH ($node_var)-[]-(candidate)
              WHERE NOT (candidate:DatasheetChunk OR candidate:GraphChunk)
                AND (
                  any(label IN labels(candidate) WHERE label IN $instance_node_labels)
                  OR coalesce(candidate.is_cad_business_object, false) = true
                  OR coalesce(candidate.semantic_role, '') IN $semantic_instance_roles
                )
            }
          }
        """.strip()
        target_projection = """
          {
            elementId: elementId($node_var),
            labels: labels($node_var),
            properties: properties($node_var),
            can_traverse: CASE
              WHEN any(label IN labels($node_var) WHERE label IN $instance_node_labels)
                OR coalesce($node_var.is_cad_business_object, false) = true
                OR coalesce($node_var.semantic_role, '') IN $semantic_instance_roles THEN EXISTS {
                MATCH ($node_var)-[]-(candidate)
                WHERE NOT (candidate:DatasheetChunk OR candidate:GraphChunk)
                  AND (
                    any(label IN labels(candidate) WHERE label IN $instance_node_labels)
                    OR coalesce(candidate.is_cad_business_object, false) = true
                    OR coalesce(candidate.semantic_role, '') IN $semantic_instance_roles
                  )
              }
              ELSE false
            END
          }
        """.strip()
        if traversal_depth >= 2:
            query = """
            CALL {
              MATCH (seed)
              WHERE elementId(seed) = $node_id
                AND NOT (seed:DatasheetChunk OR seed:GraphChunk)
              OPTIONAL MATCH (seed)-[r]-(adjacent)
              WHERE adjacent IS NULL OR (
                NOT (adjacent:DatasheetChunk OR adjacent:GraphChunk)
                AND (
                  any(label IN labels(adjacent) WHERE label IN $instance_node_labels)
                  OR coalesce(adjacent.is_cad_business_object, false) = true
                  OR coalesce(adjacent.semantic_role, '') IN $semantic_instance_roles
                )
              )
              RETURN seed AS source_node, r AS rel, adjacent AS target_node
              UNION
              MATCH (seed)
              WHERE elementId(seed) = $node_id
                AND NOT (seed:DatasheetChunk OR seed:GraphChunk)
              MATCH (seed)-[r1]-(mid)-[r2]-(adjacent)
              WHERE NOT (mid:DatasheetChunk OR mid:GraphChunk)
                AND NOT (adjacent:DatasheetChunk OR adjacent:GraphChunk)
                AND (
                  any(label IN labels(mid) WHERE label IN $instance_node_labels)
                  OR coalesce(mid.is_cad_business_object, false) = true
                  OR coalesce(mid.semantic_role, '') IN $semantic_instance_roles
                )
                AND (
                  any(label IN labels(adjacent) WHERE label IN $instance_node_labels)
                  OR coalesce(adjacent.is_cad_business_object, false) = true
                  OR coalesce(adjacent.semantic_role, '') IN $semantic_instance_roles
                )
              RETURN mid AS source_node, r2 AS rel, adjacent AS target_node
            }
            RETURN
              __SOURCE_PROJECTION__ AS n,
              CASE WHEN rel IS NOT NULL THEN {
                elementId: elementId(rel), type: type(rel), properties: properties(rel),
                start: elementId(startNode(rel)), end: elementId(endNode(rel))
              } ELSE NULL END AS r,
              CASE WHEN target_node IS NOT NULL THEN __TARGET_PROJECTION__ ELSE NULL END AS m
            LIMIT $direct_limit
            """
            query = query.replace("__SOURCE_PROJECTION__", node_projection.replace("$node_var", "source_node"))
            query = query.replace("__TARGET_PROJECTION__", target_projection.replace("$node_var", "target_node"))
        else:
            query = """
            CALL {
              MATCH (seed)
              WHERE elementId(seed) = $node_id
                AND NOT (seed:DatasheetChunk OR seed:GraphChunk)
              OPTIONAL MATCH (seed)-[direct_rel]-(adjacent)
              WHERE adjacent IS NULL OR (
                NOT (adjacent:DatasheetChunk OR adjacent:GraphChunk)
                AND NOT any(label IN labels(adjacent) WHERE label IN $relationship_node_labels)
                AND (
                  any(label IN labels(adjacent) WHERE label IN $instance_node_labels)
                  OR coalesce(adjacent.is_cad_business_object, false) = true
                  OR coalesce(adjacent.semantic_role, '') IN $semantic_instance_roles
                )
              )
              RETURN seed AS source_node,
                CASE WHEN direct_rel IS NOT NULL THEN {
                  elementId: elementId(direct_rel), type: type(direct_rel), properties: properties(direct_rel),
                  start: elementId(startNode(direct_rel)), end: elementId(endNode(direct_rel))
                } ELSE NULL END AS rel,
                adjacent AS target_node
              UNION
              MATCH (seed)
              WHERE elementId(seed) = $node_id
                AND NOT (seed:DatasheetChunk OR seed:GraphChunk)
              MATCH (seed)--(bridge)--(adjacent)
              WHERE NOT (bridge:DatasheetChunk OR bridge:GraphChunk OR adjacent:DatasheetChunk OR adjacent:GraphChunk)
                AND any(label IN labels(bridge) WHERE label IN $relationship_node_labels)
                AND NOT any(label IN labels(adjacent) WHERE label IN $relationship_node_labels)
                AND (
                  any(label IN labels(adjacent) WHERE label IN $instance_node_labels)
                  OR coalesce(adjacent.is_cad_business_object, false) = true
                  OR coalesce(adjacent.semantic_role, '') IN $semantic_instance_roles
                )
              RETURN seed AS source_node,
                {
                  elementId: 'bridge:' + elementId(bridge) + ':' + elementId(seed) + ':' + elementId(adjacent),
                  type: coalesce(properties(bridge)['element_type'], properties(bridge)['relationship_type'], properties(bridge)['name'], labels(bridge)[0], 'RELATED'),
                  properties: properties(bridge),
                  start: elementId(seed),
                  end: elementId(adjacent)
                } AS rel,
                adjacent AS target_node
              UNION
              MATCH (seed)
              WHERE elementId(seed) = $node_id
                AND NOT (seed:DatasheetChunk OR seed:GraphChunk)
              MATCH path = (seed)-[*2..4]-(adjacent)
              WHERE NOT (adjacent:DatasheetChunk OR adjacent:GraphChunk)
                AND NOT any(label IN labels(adjacent) WHERE label IN $relationship_node_labels)
                AND NOT any(label IN labels(adjacent) WHERE label IN $schema_node_labels)
                AND (
                  any(label IN labels(adjacent) WHERE label IN $instance_node_labels)
                  OR coalesce(adjacent.is_cad_business_object, false) = true
                  OR coalesce(adjacent.semantic_role, '') IN $semantic_instance_roles
                )
                AND NOT coalesce(
                  adjacent.name,
                  adjacent.title,
                  adjacent.label,
                  properties(adjacent)['display_name'],
                  properties(adjacent)['displayName'],
                  adjacent.id,
                  properties(adjacent)['uid'],
                  ''
                ) =~ '(?i)^id\\d+$'
                AND all(node IN nodes(path) WHERE NOT (node:DatasheetChunk OR node:GraphChunk))
                AND any(node IN nodes(path)[1..-1] WHERE
                  any(label IN labels(node) WHERE label IN $relationship_node_labels)
                  OR coalesce(
                    node.name,
                    node.title,
                    node.label,
                    properties(node)['display_name'],
                    properties(node)['displayName'],
                    node.id,
                    properties(node)['uid'],
                    ''
                  ) =~ '(?i)^id\\d+$'
                )
              WITH seed, adjacent, path
              ORDER BY length(path) ASC, elementId(adjacent) ASC
              WITH seed, adjacent, collect(path)[0] AS path
              WITH seed, adjacent, relationships(path) AS rels, nodes(path) AS path_nodes
              RETURN seed AS source_node,
                {
                  elementId: 'path:' + elementId(seed) + ':' + elementId(adjacent) + ':' + reduce(signature = '', rel IN rels | signature + ':' + type(rel)),
                  type: coalesce(type(rels[size(rels) - 1]), 'RELATED'),
                  properties: {
                    path_types: [rel IN rels | type(rel)],
                    via_count: size(path_nodes) - 2,
                    relationship_type: coalesce(type(rels[size(rels) - 1]), 'RELATED')
                  },
                  start: elementId(seed),
                  end: elementId(adjacent)
                } AS rel,
                adjacent AS target_node
            }
            RETURN
              {
                elementId: elementId(source_node),
                labels: labels(source_node),
                properties: properties(source_node),
                can_traverse: EXISTS {
                  MATCH (source_node)-[]-(candidate)
                  WHERE NOT (candidate:DatasheetChunk OR candidate:GraphChunk)
                    AND (
                      any(label IN labels(candidate) WHERE label IN $instance_node_labels)
                      OR coalesce(candidate.is_cad_business_object, false) = true
                      OR coalesce(candidate.semantic_role, '') IN $semantic_instance_roles
                    )
                }
              } AS n,
              rel AS r,
              CASE WHEN target_node IS NOT NULL THEN {
                elementId: elementId(target_node),
                labels: labels(target_node),
                properties: properties(target_node),
                can_traverse: CASE
                  WHEN any(label IN labels(target_node) WHERE label IN $instance_node_labels)
                    OR coalesce(target_node.is_cad_business_object, false) = true
                    OR coalesce(target_node.semantic_role, '') IN $semantic_instance_roles THEN EXISTS {
                    MATCH (target_node)-[]-(candidate)
                    WHERE NOT (candidate:DatasheetChunk OR candidate:GraphChunk)
                      AND (
                        any(label IN labels(candidate) WHERE label IN $instance_node_labels)
                        OR coalesce(candidate.is_cad_business_object, false) = true
                        OR coalesce(candidate.semantic_role, '') IN $semantic_instance_roles
                      )
                  }
                  ELSE false
                END
              } ELSE NULL END AS m
            LIMIT $direct_limit
            """
        rows = cls._run(
            query,
            {
                "node_id": node_id,
                "direct_limit": row_limit,
                "depth": traversal_depth,
                "schema_node_labels": cls.SCHEMA_NODE_LABELS,
                "instance_node_labels": cls.INSTANCE_NODE_LABELS,
                "semantic_instance_roles": cls.INSTANCE_SEMANTIC_ROLES,
                "relationship_node_labels": cls.RELATIONSHIP_NODE_LABELS,
            },
        )
        graph = cls.rows_to_graph(rows)
        graph = cls._filter_graph_nodes(graph, only_individual_nodes=True)
        root_node = next((node for node in graph.get("nodes", []) if node.get("elementId") == node_id), None)
        graph["view"] = {
            "type": "traversal-slice",
            "node_id": node_id,
            "depth": traversal_depth,
            "root_node_id": node_id,
        }
        graph["root"] = root_node
        return graph
