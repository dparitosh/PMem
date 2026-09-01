"""
Minimal read-only OSLC interoperability service.

This layer exposes discovery and query capabilities on top of the current
Neo4j-backed semantic graph without changing the underlying data model.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from rdflib import Graph
from rdflib.namespace import RDF, RDFS, SH

from .graph_view_service import GraphViewService
from .ontology_reasoning_service import OntologyReasoningService
from .ontology_taxonomy_service import OntologyTaxonomyService
from .ontology_upload_manager import OntologyUploadManager
from .oslc_query_service import OSLCCondition, OSLCQueryParameters


@dataclass(frozen=True)
class OSLCRuntimeConfig:
    base_url: str
    provider_id: str
    provider_title: str
    max_page_size: int


def _safe_path_token(value: str, default: str) -> str:
    token = str(value or "").strip()
    if not token:
        return default
    return re.sub(r"[^A-Za-z0-9._-]+", "-", token)


def _default_base_url() -> str:
    host = str(os.getenv("APP_HOST", "")).strip() or "localhost"
    port = str(os.getenv("APP_PORT", os.getenv("BACKEND_PORT", "8000"))).strip() or "8000"
    scheme = str(os.getenv("APP_SCHEME", "http")).strip() or "http"
    return f"{scheme}://{host}:{port}"


class OSLCService:
    """Read-only OSLC facade over the current semantic graph."""

    DEFAULT_RESOURCE_TYPE = "resources"
    AM_RESOURCE_TYPE = "architecture-resources"
    RM_REQUIREMENT_TYPE = "requirements"
    RM_COLLECTION_TYPE = "requirement-collections"
    SUPPORTED_RESOURCE_TYPES = {
        DEFAULT_RESOURCE_TYPE,
        AM_RESOURCE_TYPE,
        RM_REQUIREMENT_TYPE,
        RM_COLLECTION_TYPE,
    }
    AM_TYPE_URI = "http://open-services.net/ns/am#Resource"
    RM_REQUIREMENT_URI = "http://open-services.net/ns/rm#Requirement"
    RM_COLLECTION_URI = "http://open-services.net/ns/rm#RequirementCollection"
    DOMAIN_SHAPES = {
        AM_RESOURCE_TYPE: {
            "title": "OSLC AM Architecture Resource Shape",
            "domain": "oslc_am",
            "describes": [AM_TYPE_URI],
            "properties": [
                {"name": "dcterms:title", "occurs": "exactly-one", "valueType": "oslc:LiteralValue"},
                {"name": "dcterms:description", "occurs": "zero-or-one", "valueType": "oslc:LiteralValue"},
                {"name": "dcterms:identifier", "occurs": "zero-or-one", "valueType": "oslc:LiteralValue"},
                {"name": "oslc:serviceProvider", "occurs": "exactly-one", "valueType": "oslc:Resource"},
                {"name": "dcterms:relation", "occurs": "zero-or-many", "valueType": "oslc:Resource"},
            ],
        },
        RM_REQUIREMENT_TYPE: {
            "title": "OSLC RM Requirement Shape",
            "domain": "oslc_rm",
            "describes": [RM_REQUIREMENT_URI],
            "properties": [
                {"name": "dcterms:title", "occurs": "exactly-one", "valueType": "oslc:LiteralValue"},
                {"name": "dcterms:description", "occurs": "zero-or-one", "valueType": "oslc:LiteralValue"},
                {"name": "dcterms:identifier", "occurs": "zero-or-one", "valueType": "oslc:LiteralValue"},
                {"name": "oslc:serviceProvider", "occurs": "exactly-one", "valueType": "oslc:Resource"},
                {"name": "dcterms:relation", "occurs": "zero-or-many", "valueType": "oslc:Resource"},
            ],
        },
        RM_COLLECTION_TYPE: {
            "title": "OSLC RM Requirement Collection Shape",
            "domain": "oslc_rm",
            "describes": [RM_COLLECTION_URI],
            "properties": [
                {"name": "dcterms:title", "occurs": "exactly-one", "valueType": "oslc:LiteralValue"},
                {"name": "dcterms:description", "occurs": "zero-or-one", "valueType": "oslc:LiteralValue"},
                {"name": "dcterms:identifier", "occurs": "zero-or-one", "valueType": "oslc:LiteralValue"},
                {"name": "oslc:serviceProvider", "occurs": "exactly-one", "valueType": "oslc:Resource"},
                {"name": "oslc_rm:uses", "occurs": "zero-or-many", "valueType": "oslc:Resource"},
            ],
        },
    }
    INTERNAL_DICTIONARY_PROPS = {
        "ontology_prefix", "ontology_id", "ontology_name", "source_ontology",
        "version", "created_at", "updated_at", "id", "elementId",
        "prefix", "source_format", "source_file"
    }

    @classmethod
    def is_enabled(cls) -> bool:
        return str(os.getenv("OSLC_ENABLED", "true")).strip().lower() in {"true", "1", "yes"}

    @classmethod
    def config(cls) -> OSLCRuntimeConfig:
        provider_id = _safe_path_token(os.getenv("OSLC_PROVIDER_ID", "depo"), "depo")
        provider_title = str(os.getenv("OSLC_PROVIDER_TITLE", "DEPO Semantic Platform")).strip() or "DEPO Semantic Platform"
        base_url = str(os.getenv("OSLC_BASE_URL", "")).strip().rstrip("/")
        if not base_url:
            base_url = _default_base_url()
        raw_max_page_size = str(os.getenv("OSLC_MAX_PAGE_SIZE", "200")).strip() or "200"
        try:
            max_page_size = int(raw_max_page_size)
        except (TypeError, ValueError):
            max_page_size = 200
        return OSLCRuntimeConfig(
            base_url=base_url,
            provider_id=provider_id,
            provider_title=provider_title,
            max_page_size=max(10, min(1000, max_page_size)),
        )

    @classmethod
    def service_provider_catalog(cls) -> Dict[str, Any]:
        cfg = cls.config()
        provider_uri = f"{cfg.base_url}/oslc/providers/{cfg.provider_id}"
        return {
            "uri": f"{cfg.base_url}/oslc/catalog",
            "type": "oslc:ServiceProviderCatalog",
            "title": f"{cfg.provider_title} Catalog",
            "serviceProviders": [
                {
                    "uri": provider_uri,
                    "title": cfg.provider_title,
                    "details": provider_uri,
                }
            ],
        }

    @classmethod
    def _ontology_domains(cls) -> List[Dict[str, Any]]:
        """Turn every registered ontology into an OSLC domain declaration."""
        listed = OntologyUploadManager.list_ontologies()
        if listed.get("status") != "success":
            return []
        domains: List[Dict[str, Any]] = []
        for metadata in listed.get("ontologies", []):
            ontology_id = str(metadata.get("ontology_id") or "").strip()
            if not ontology_id:
                continue
            prefix = str(metadata.get("prefix") or metadata.get("ontology_prefix") or ontology_id).strip()
            domains.append({
                "id": f"ontology:{ontology_id}", "ontology_id": ontology_id, "prefix": prefix,
                "title": metadata.get("ontology_name") or metadata.get("original_filename") or ontology_id,
                "namespace": metadata.get("namespace") or metadata.get("ontology_uri") or f"urn:depo:ontology:{prefix}",
                "description": metadata.get("description") or f"DEPO governed ontology domain '{prefix}'.",
                "version": metadata.get("version", 1), "schema_type": metadata.get("schema_type", "schema"),
            })
        return domains

    @classmethod
    def service_provider(cls) -> Dict[str, Any]:
        cfg = cls.config()
        query_base = f"{cfg.base_url}/oslc/query/{cls.DEFAULT_RESOURCE_TYPE}"
        am_query_base = f"{cfg.base_url}/oslc/query/{cls.AM_RESOURCE_TYPE}"
        rm_query_base = f"{cfg.base_url}/oslc/query/{cls.RM_REQUIREMENT_TYPE}"
        rm_collection_query_base = f"{cfg.base_url}/oslc/query/{cls.RM_COLLECTION_TYPE}"
        return {
            "uri": f"{cfg.base_url}/oslc/providers/{cfg.provider_id}",
            "type": "oslc:ServiceProvider",
            "title": cfg.provider_title,
            "domains": [
                {
                    "id": "ap242",
                    "title": "AP242 Product and Manufacturing Information",
                    "namespace": "http://depo-onto.local/ap242#",
                    "description": "STEP AP242-aligned product structure, PMI, requirements traceability, process, and manufacturing context resources.",
                },
                {
                    "id": "oslc_am",
                    "title": "OSLC Architecture Management",
                    "namespace": "http://open-services.net/ns/am#",
                    "description": "Architecture/model element and traceability discovery profile for Teamcenter Linked Data and MBSE integrations.",
                },
                {
                    "id": "oslc_rm",
                    "title": "OSLC Requirements Management",
                    "namespace": "http://open-services.net/ns/rm#",
                    "description": "Requirement, requirement collection, and cross-domain traceability discovery profile.",
                },
                *cls._ontology_domains(),
            ],
            "queryCapabilities": [
                {
                    "resourceType": cls.DEFAULT_RESOURCE_TYPE,
                    "queryBase": query_base,
                    "supportedParameters": [
                        "oslc.where",
                        "oslc.select",
                        "oslc.orderBy",
                        "oslc.searchTerms",
                        "oslc.paging",
                        "oslc.pageSize",
                        "oslc.pageNum",
                    ],
                    "domains": ["ap242", "oslc_am", "oslc_rm"],
                },
                {
                    "resourceType": cls.AM_RESOURCE_TYPE,
                    "resourceTypeUri": cls.AM_TYPE_URI,
                    "queryBase": am_query_base,
                    "resourceShape": f"{cfg.base_url}/oslc/shapes/{cls.AM_RESOURCE_TYPE}",
                    "supportedParameters": ["oslc.where", "oslc.select", "oslc.orderBy", "oslc.searchTerms", "oslc.paging", "oslc.pageSize", "oslc.pageNum"],
                    "domains": ["oslc_am"],
                },
                {
                    "resourceType": cls.RM_REQUIREMENT_TYPE,
                    "resourceTypeUri": cls.RM_REQUIREMENT_URI,
                    "queryBase": rm_query_base,
                    "resourceShape": f"{cfg.base_url}/oslc/shapes/{cls.RM_REQUIREMENT_TYPE}",
                    "supportedParameters": ["oslc.where", "oslc.select", "oslc.orderBy", "oslc.searchTerms", "oslc.paging", "oslc.pageSize", "oslc.pageNum"],
                    "domains": ["oslc_rm"],
                },
                {
                    "resourceType": cls.RM_COLLECTION_TYPE,
                    "resourceTypeUri": cls.RM_COLLECTION_URI,
                    "queryBase": rm_collection_query_base,
                    "resourceShape": f"{cfg.base_url}/oslc/shapes/{cls.RM_COLLECTION_TYPE}",
                    "supportedParameters": ["oslc.where", "oslc.select", "oslc.orderBy", "oslc.searchTerms", "oslc.paging", "oslc.pageSize", "oslc.pageNum"],
                    "domains": ["oslc_rm"],
                },
                *[
                    {
                        "resourceType": f"ontology:{domain['ontology_id']}",
                        "queryBase": query_base,
                        "resourceShape": f"{cfg.base_url}/oslc/shapes/{domain['ontology_id']}",
                        "supportedParameters": ["oslc.where", "oslc.select", "oslc.orderBy", "oslc.searchTerms", "oslc.paging", "oslc.pageSize", "oslc.pageNum"],
                        "domains": [domain["id"]],
                    }
                    for domain in cls._ontology_domains()
                ],
            ],
            "resourceShapes": [
                {
                    "uri": f"{cfg.base_url}/oslc/shapes/{cls.DEFAULT_RESOURCE_TYPE}",
                    "title": "Graph Resource Shape",
                },
                {
                    "uri": f"{cfg.base_url}/oslc/shapes",
                    "title": "Ontology Resource Shapes",
                },
                *[
                    {
                        "uri": f"{cfg.base_url}/oslc/shapes/{shape_id}",
                        "title": definition["title"],
                    }
                    for shape_id, definition in cls.DOMAIN_SHAPES.items()
                ],
                *[
                    {"uri": f"{cfg.base_url}/oslc/shapes/{domain['ontology_id']}", "title": domain["title"]}
                    for domain in cls._ontology_domains()
                ],
            ],
            "domainResources": {
                "ap242": {
                    "title": "AP242 Semantic Resources",
                    "dictionary": f"{cfg.base_url}/oslc/dictionaries/ap242",
                    "queryBase": query_base,
                    "shape": f"{cfg.base_url}/oslc/shapes/ap242",
                    "trs": f"{cfg.base_url}/oslc/trs",
                    "description": "AP242-aligned linked data for product, PMI, requirements, process, and manufacturing traceability.",
                },
                "oslc_am": {
                    "title": "OSLC AM Architecture Resources",
                    "queryBase": am_query_base,
                    "shape": f"{cfg.base_url}/oslc/shapes/{cls.AM_RESOURCE_TYPE}",
                    "trs": f"{cfg.base_url}/oslc/trs",
                    "description": "Architecture/model element discovery profile for Teamcenter LDS and MBSE integrations.",
                },
                "oslc_rm": {
                    "title": "OSLC RM Requirement Resources",
                    "queryBase": rm_query_base,
                    "collectionQueryBase": rm_collection_query_base,
                    "shape": f"{cfg.base_url}/oslc/shapes/{cls.RM_REQUIREMENT_TYPE}",
                    "collectionShape": f"{cfg.base_url}/oslc/shapes/{cls.RM_COLLECTION_TYPE}",
                    "trs": f"{cfg.base_url}/oslc/trs",
                    "description": "Requirement, requirement collection, and lifecycle traceability discovery profile.",
                },
                "dictionaries": {
                    "title": "Ontology Data Dictionaries",
                    "uriTemplate": f"{cfg.base_url}/oslc/dictionaries/{{prefix}}",
                    "description": "Live Neo4j-backed data dictionaries by ontology prefix.",
                },
                "taxonomies": {
                    "title": "Ontology Taxonomies",
                    "uri": f"{cfg.base_url}/oslc/taxonomies",
                    "description": "Uploaded ontology taxonomy and hierarchy resources.",
                },
                "ontologies": {
                    "title": "Governed Ontology Domains",
                    "domains": {
                        domain["id"]: {
                            "ontologyId": domain["ontology_id"], "prefix": domain["prefix"],
                            "shape": f"{cfg.base_url}/oslc/shapes/{domain['ontology_id']}",
                            "queryBase": query_base, "trs": f"{cfg.base_url}/oslc/trs",
                        }
                        for domain in cls._ontology_domains()
                    },
                },
            },
        }

    @classmethod
    def _fallback_resource_shape(cls) -> Dict[str, Any]:
        labels = sorted({
            str(row.get("label") or "")
            for row in GraphViewService._run(
                "MATCH (n) WHERE NOT (n:DatasheetChunk OR n:GraphChunk) "
                "UNWIND labels(n) AS label RETURN DISTINCT label ORDER BY label"
            )
            if row.get("label")
        })
        properties = sorted({
            str(row.get("propertyKey") or "")
            for row in GraphViewService._run(
                "MATCH (n) WHERE NOT (n:DatasheetChunk OR n:GraphChunk) "
                "UNWIND keys(n) AS propertyKey RETURN DISTINCT propertyKey ORDER BY propertyKey"
            )
            if row.get("propertyKey")
        })
        cfg = cls.config()
        return {
            "uri": f"{cfg.base_url}/oslc/shapes/{cls.DEFAULT_RESOURCE_TYPE}",
            "type": "oslc:ResourceShape",
            "title": "Graph Resource Shape",
            "describes": labels,
            "properties": properties,
            "source": "graph_scan",
        }

    @staticmethod
    def _discover_shacl_file(meta: Dict[str, Any], context: Dict[str, Any]) -> Optional[Path]:
        raw_base_path = str(meta.get("file_path") or context.get("source_file_path") or context.get("file_path") or "").strip()
        if not raw_base_path:
            return None
        resolved_base = Path(raw_base_path).resolve()
        base_dir = resolved_base.parent
        prefix = str(meta.get("prefix") or meta.get("ontology_prefix") or meta.get("ontology_id") or "").strip()
        source_file = Path(context.get("source_file_path") or context.get("file_path") or "")
        semantic_file = Path(context.get("file_path") or source_file)
        candidates = []
        for base in [source_file, semantic_file]:
            if base and str(base):
                candidates.append(base.with_name(base.stem + '_shapes.ttl'))
                candidates.append(base.with_name(base.stem + '.shacl.ttl'))
        if prefix:
            candidates.append(base_dir / f'{prefix}_shapes.ttl')
            candidates.append(base_dir / f'{prefix}.shacl.ttl')
        for candidate in candidates:
            if candidate.exists():
                return candidate
        for candidate in sorted(base_dir.glob('*shapes*.ttl')):
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _fragment(value: Any) -> str:
        raw = str(value or "")
        if "#" in raw:
            return raw.rsplit("#", 1)[-1]
        if "/" in raw:
            return raw.rstrip("/").rsplit("/", 1)[-1]
        return raw

    @classmethod
    def _shacl_summary(cls, shape_file: Optional[Path]) -> Dict[str, Any]:
        if not shape_file or not shape_file.exists():
            return {
                "available": False,
                "source": "none",
                "node_shapes": 0,
                "property_shapes": 0,
                "shape_nodes": 0,
                "property_constraints": [],
            }
        try:
            graph = Graph()
            graph.parse(str(shape_file))
            node_shape_nodes = set(graph.subjects(RDF.type, SH.NodeShape))
            property_shape_nodes = set(graph.subjects(RDF.type, SH.PropertyShape))
            candidate_shapes = set(property_shape_nodes)
            for node_shape in node_shape_nodes:
                candidate_shapes.update(graph.objects(node_shape, SH.property))

            constraints_by_key: Dict[str, Dict[str, Any]] = {}
            for shape in candidate_shapes:
                path_obj = next(graph.objects(shape, SH.path), None)
                if path_obj is None:
                    continue
                path_uri = str(path_obj)
                title = cls._fragment(path_obj)
                existing = constraints_by_key.get(path_uri) or constraints_by_key.get(title) or {
                    "uri": path_uri,
                    "title": title,
                    "minCount": None,
                    "maxCount": None,
                    "datatype": None,
                    "nodeKind": None,
                    "class": None,
                    "messages": [],
                    "descriptions": [],
                    "shapeCount": 0,
                }
                existing["shapeCount"] += 1
                min_count = next(graph.objects(shape, SH.minCount), None)
                max_count = next(graph.objects(shape, SH.maxCount), None)
                datatype = next(graph.objects(shape, SH.datatype), None)
                node_kind = next(graph.objects(shape, SH.nodeKind), None)
                class_target = next(graph.objects(shape, SH['class']), None)
                name = next(graph.objects(shape, SH.name), None)
                description = next(graph.objects(shape, SH.description), None)
                message_values = [str(item).strip() for item in graph.objects(shape, SH.message) if str(item).strip()]
                if min_count is not None:
                    value = int(min_count)
                    existing["minCount"] = value if existing["minCount"] is None else max(existing["minCount"], value)
                if max_count is not None:
                    value = int(max_count)
                    existing["maxCount"] = value if existing["maxCount"] is None else min(existing["maxCount"], value)
                if datatype is not None:
                    existing["datatype"] = str(datatype)
                if node_kind is not None:
                    existing["nodeKind"] = cls._fragment(node_kind)
                if class_target is not None:
                    existing["class"] = str(class_target)
                if name is not None and not existing.get("title"):
                    existing["title"] = str(name).strip()
                if description is not None and str(description).strip() not in existing["descriptions"]:
                    existing["descriptions"].append(str(description).strip())
                for message in message_values:
                    if message not in existing["messages"]:
                        existing["messages"].append(message)
                constraints_by_key[path_uri] = existing
                constraints_by_key[title] = existing

            unique_constraints = []
            seen_ids = set()
            for constraint in constraints_by_key.values():
                marker = constraint.get("uri") or constraint.get("title")
                if not marker or marker in seen_ids:
                    continue
                seen_ids.add(marker)
                unique_constraints.append(constraint)
            return {
                "available": True,
                "source": str(shape_file),
                "node_shapes": len(node_shape_nodes),
                "property_shapes": len(property_shape_nodes),
                "shape_nodes": len(node_shape_nodes | property_shape_nodes),
                "property_constraints": sorted(unique_constraints, key=lambda item: str(item.get("title") or item.get("uri") or "")),
            }
        except Exception as exc:
            return {
                "available": False,
                "source": str(shape_file),
                "node_shapes": 0,
                "property_shapes": 0,
                "shape_nodes": 0,
                "property_constraints": [],
                "error": str(exc),
            }

    @staticmethod
    def _value_type_for_property(term: Dict[str, Any]) -> str:
        target_type = str(term.get("target_ontology_type") or "")
        if target_type == "ObjectProperty":
            return "oslc:Resource"
        if target_type == "AnnotationProperty":
            return "oslc:AnyResource"
        return "oslc:LiteralValue"

    @staticmethod
    def _term_title(term: Dict[str, Any]) -> str:
        return str(term.get("label") or term.get("local_name") or term.get("iri") or "").strip()

    @staticmethod
    def _occurs_value(min_count: Any, max_count: Any) -> str:
        min_value = int(min_count) if min_count is not None else None
        max_value = int(max_count) if max_count is not None else None
        if min_value == 1 and max_value == 1:
            return "exactly-one"
        if min_value == 1 and (max_value is None or max_value > 1):
            return "one-or-many"
        if (min_value is None or min_value == 0) and max_value == 1:
            return "zero-or-one"
        return "zero-or-many"

    @classmethod
    def _constraint_lookup_keys(cls, uri: Any, title: Any) -> List[str]:
        keys = []
        if uri:
            keys.append(str(uri))
            keys.append(cls._fragment(uri))
        if title:
            keys.append(str(title))
        return [key for key in keys if key]

    @classmethod
    def _semantic_property_descriptor(cls, term: Dict[str, Any], constraint: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        description_parts = [str(term.get("definition") or "").strip()]
        if constraint:
            description_parts.extend(constraint.get("descriptions") or [])
        descriptor = {
            "name": cls._term_title(term),
            "title": cls._term_title(term),
            "uri": term.get("iri") or term.get("uri"),
            "propertyType": term.get("target_ontology_type"),
            "valueType": cls._value_type_for_property(term),
            "domain": [item.get("label") or item.get("local_name") or item.get("iri") for item in (term.get("domain") or [])],
            "range": [item.get("label") or item.get("local_name") or item.get("iri") for item in (term.get("range") or [])],
            "description": " ".join(part for part in description_parts if part).strip(),
            "occurs": cls._occurs_value(constraint.get("minCount") if constraint else None, constraint.get("maxCount") if constraint else None),
        }
        if constraint:
            for key in ["minCount", "maxCount", "datatype", "nodeKind", "class", "messages", "shapeCount"]:
                value = constraint.get(key)
                if value not in (None, [], ""):
                    descriptor[key] = value
            if constraint.get("datatype"):
                descriptor["valueType"] = constraint.get("datatype")
        return descriptor

    @classmethod
    def _constraint_only_descriptor(cls, constraint: Dict[str, Any]) -> Dict[str, Any]:
        uri = constraint.get("uri")
        title = constraint.get("title") or cls._fragment(uri)
        description = " ".join([*(constraint.get("descriptions") or []), *(constraint.get("messages") or [])]).strip()
        value_type = "oslc:LiteralValue"
        if constraint.get("nodeKind") in {"IRI", "BlankNodeOrIRI"} or constraint.get("class"):
            value_type = "oslc:Resource"
        if constraint.get("datatype"):
            value_type = constraint.get("datatype")
        descriptor = {
            "name": title,
            "title": title,
            "uri": uri,
            "propertyType": "SHACLProperty",
            "valueType": value_type,
            "domain": [],
            "range": [constraint.get("class")] if constraint.get("class") else [],
            "description": description,
            "occurs": cls._occurs_value(constraint.get("minCount"), constraint.get("maxCount")),
        }
        for key in ["minCount", "maxCount", "datatype", "nodeKind", "class", "messages", "shapeCount"]:
            value = constraint.get(key)
            if value not in (None, [], ""):
                descriptor[key] = value
        return descriptor

    @classmethod
    def _dictionary_property_descriptor(cls, property_name: str, property_meta: Dict[str, Any]) -> Dict[str, Any]:
        classes = [item for item in (property_meta.get("classes") or []) if item]
        return {
            "name": property_name,
            "title": property_name,
            "uri": None,
            "propertyType": "DictionaryProperty",
            "valueType": "oslc:LiteralValue",
            "domain": classes,
            "range": [],
            "description": "",
            "occurs": "zero-or-many",
        }


    @classmethod
    def list_shapes(cls) -> Dict[str, Any]:
        members = [
            {
                "uri": f"{cls.config().base_url}/oslc/shapes/{cls.DEFAULT_RESOURCE_TYPE}",
                "shape_id": cls.DEFAULT_RESOURCE_TYPE,
                "title": "Graph Resource Shape",
                "kind": "generic",
            }
        ]
        members.extend(
            {
                "uri": f"{cls.config().base_url}/oslc/shapes/{shape_id}",
                "shape_id": shape_id,
                "title": definition["title"],
                "domain": definition["domain"],
                "kind": "oslc-domain",
            }
            for shape_id, definition in cls.DOMAIN_SHAPES.items()
        )
        listed = OntologyUploadManager.list_ontologies()
        if listed.get("status") == "success":
            for meta in listed.get("ontologies", []):
                ontology_id = meta.get("ontology_id")
                if not ontology_id:
                    continue
                members.append({
                    "uri": f"{cls.config().base_url}/oslc/shapes/{ontology_id}",
                    "shape_id": ontology_id,
                    "title": meta.get("ontology_name") or meta.get("original_filename") or ontology_id,
                    "prefix": meta.get("prefix") or meta.get("ontology_prefix"),
                    "kind": "ontology",
                })
        return {
            "uri": f"{cls.config().base_url}/oslc/shapes",
            "type": "oslc:ResourceShapeCollection",
            "members": members,
            "count": len(members),
        }

    @classmethod
    def resource_shape(cls, shape_id: str | None = None) -> Dict[str, Any]:
        normalized_shape_id = str(shape_id or cls.DEFAULT_RESOURCE_TYPE).strip()
        if normalized_shape_id in {"", cls.DEFAULT_RESOURCE_TYPE}:
            return cls._fallback_resource_shape()
        if normalized_shape_id in cls.DOMAIN_SHAPES:
            definition = cls.DOMAIN_SHAPES[normalized_shape_id]
            return {
                "uri": f"{cls.config().base_url}/oslc/shapes/{normalized_shape_id}",
                "type": "oslc:ResourceShape",
                "shape_id": normalized_shape_id,
                "title": definition["title"],
                "domain": definition["domain"],
                "describes": list(definition["describes"]),
                "properties": [dict(item) for item in definition["properties"]],
                "source": "oslc-domain-profile",
            }

        context = OntologyReasoningService.semantic_context(normalized_shape_id)
        reasoning = OntologyReasoningService.inspect_context(context)
        meta = context["meta"]
        shacl_file = cls._discover_shacl_file(meta, context)
        shacl_summary = cls._shacl_summary(shacl_file)
        constraint_lookup: Dict[str, Dict[str, Any]] = {}
        for constraint in (shacl_summary.get("property_constraints") or []):
            for key in cls._constraint_lookup_keys(constraint.get("uri"), constraint.get("title")):
                constraint_lookup[key] = constraint
        semantic_terms = list(OntologyReasoningService.iter_semantic_terms(reasoning))
        classes = reasoning.get("classes") or []
        dictionary_fallback = None
        describes = [
            {
                "uri": item.get("iri") or item.get("uri"),
                "label": item.get("label") or item.get("local_name"),
                "parents": [parent.get("label") or parent.get("local_name") or parent.get("iri") for parent in (item.get("parents") or [])],
            }
            for item in classes
        ]
        shape_source = "owlready2_semantics"
        if not describes and not semantic_terms:
            taxonomy = OntologyTaxonomyService.get_taxonomy(normalized_shape_id)
            describes = [
                {
                    "uri": item.get("uri") or item.get("term_id"),
                    "label": item.get("label"),
                    "parents": [],
                }
                for item in (taxonomy.get("nodes") or [])[:500]
            ]
            shape_source = "taxonomy_fallback"
        if not semantic_terms and reasoning.get("prefix"):
            try:
                dictionary_fallback = cls.get_dictionary(reasoning.get("prefix"), instance_limit=500, relationship_limit=100, fallback_limit=100)
            except Exception:
                dictionary_fallback = None
        property_descriptors = []
        matched_constraint_keys = set()
        for term in semantic_terms:
            constraint = None
            for key in cls._constraint_lookup_keys(term.get("iri") or term.get("uri"), cls._term_title(term)):
                if key in constraint_lookup:
                    constraint = constraint_lookup[key]
                    matched_constraint_keys.add(constraint.get("uri") or constraint.get("title"))
                    break
            property_descriptors.append(cls._semantic_property_descriptor(term, constraint))

        for constraint in (shacl_summary.get("property_constraints") or []):
            marker = constraint.get("uri") or constraint.get("title")
            if marker in matched_constraint_keys:
                continue
            property_descriptors.append(cls._constraint_only_descriptor(constraint))

        if not property_descriptors and dictionary_fallback:
            dictionary_props = (((dictionary_fallback or {}).get("data") or {}).get("properties") or {})
            for property_name, property_meta in sorted(dictionary_props.items()):
                property_descriptors.append(cls._dictionary_property_descriptor(property_name, property_meta or {}))
            if property_descriptors and shape_source == "taxonomy_fallback":
                shape_source = "taxonomy_dictionary_fallback"

        cfg = cls.config()
        export_links = [
            {
                "format": item.get("format"),
                "uri": f"{cfg.base_url}/api/v1/ontology/{normalized_shape_id}/export?format={item.get('format')}",
            }
            for item in (meta.get("ontology_export_artifacts") or [])
            if item.get("format")
        ]
        return {
            "uri": f"{cfg.base_url}/oslc/shapes/{normalized_shape_id}",
            "type": "oslc:ResourceShape",
            "title": reasoning.get("ontology_name") or reasoning.get("ontology_id") or normalized_shape_id,
            "ontology_id": reasoning.get("ontology_id"),
            "prefix": reasoning.get("prefix"),
            "source_filename": reasoning.get("source_filename"),
            "describes": describes,
            "properties": property_descriptors,
            "shapeSummary": {
                **(reasoning.get("summary") or {}),
                "annotation_properties": len(reasoning.get("annotation_properties") or []),
                "describes_count": len(describes),
                "property_constraints": len(shacl_summary.get("property_constraints") or []),
            },
            "validationShapes": shacl_summary,
            "exports": export_links,
            "source": shape_source,
        }

    @classmethod
    def list_taxonomies(cls) -> Dict[str, Any]:
        listed = OntologyUploadManager.list_ontologies()
        if listed.get("status") != "success":
            raise RuntimeError(listed.get("error") or "Failed to list ontologies.")

        cfg = cls.config()
        members = []
        for meta in listed.get("ontologies", []):
            ontology_id = meta.get("ontology_id")
            if not ontology_id:
                continue
            members.append({
                "uri": f"{cfg.base_url}/oslc/taxonomies/{ontology_id}",
                "ontology_id": ontology_id,
                "prefix": meta.get("prefix") or meta.get("ontology_prefix"),
                "title": meta.get("ontology_name") or meta.get("original_filename") or ontology_id,
                "source_filename": meta.get("original_filename") or meta.get("stored_filename"),
            })

        return {
            "uri": f"{cfg.base_url}/oslc/taxonomies",
            "type": "oslc:TaxonomyCollection",
            "members": members,
            "count": len(members),
        }

    @classmethod
    def get_taxonomy(cls, ontology_id: str) -> Dict[str, Any]:
        payload = OntologyTaxonomyService.get_taxonomy(ontology_id)
        return {
            "uri": f"{cls.config().base_url}/oslc/taxonomies/{ontology_id}",
            "type": "oslc:TaxonomyResource",
            "title": payload.get("ontology_name") or payload.get("ontology_id") or ontology_id,
            **payload,
        }

    @classmethod
    def get_dictionary(
        cls,
        prefix: str,
        instance_limit: int = 2000,
        relationship_limit: int = 500,
        fallback_limit: int = 200,
    ) -> Dict[str, Any]:
        normalized_prefix = str(prefix or "").strip()
        if not normalized_prefix:
            raise ValueError("Ontology prefix is required")

        entities: Dict[str, Any] = {}
        all_props: Dict[str, Any] = {}
        relationships: Dict[str, Any] = {}

        schema_rows = GraphViewService._run(
            """
            MATCH (c:OntologyClass)
            WHERE coalesce(c.ontology_prefix, c.prefix) = $prefix
            OPTIONAL MATCH (p:OntologyProperty)-[:PROPERTY_OF]->(c)
            RETURN c.name AS name,
                   c.concept_type AS concept_type,
                   c.namespace AS namespace,
                   collect(DISTINCT p.name) AS schema_props
            ORDER BY c.name
            """,
            {"prefix": normalized_prefix},
        )

        class_names: List[str] = []
        for row in (schema_rows or []):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            class_names.append(name)
            static_props = [p for p in (row.get("schema_props") or []) if p]
            entities[name] = {
                "type": name,
                "concept_type": row.get("concept_type") or "Class",
                "namespace": row.get("namespace") or normalized_prefix,
                "ontology_prefix": normalized_prefix,
                "source": "schema",
                "properties": static_props,
            }
            for prop_name in static_props:
                all_props.setdefault(prop_name, {"name": prop_name, "classes": []})
                all_props[prop_name]["classes"].append(name)

        if class_names:
            inst_rows = GraphViewService._run(
                """
                MATCH (n)
                WHERE any(lbl IN labels(n) WHERE lbl IN $class_names)
                  AND coalesce(n.ontology_prefix, n.prefix) = $prefix
                RETURN DISTINCT labels(n) AS labels, keys(n) AS prop_keys
                LIMIT toInteger($instance_limit)
                """,
                {
                    "class_names": class_names,
                    "prefix": normalized_prefix,
                    "instance_limit": instance_limit,
                },
            )
            for row in (inst_rows or []):
                matched_label = next((lbl for lbl in (row.get("labels") or []) if lbl in class_names), None)
                if matched_label and matched_label in entities:
                    for key in (row.get("prop_keys") or []):
                        if key and key not in cls.INTERNAL_DICTIONARY_PROPS:
                            if key not in entities[matched_label]["properties"]:
                                entities[matched_label]["properties"].append(key)
                            all_props.setdefault(key, {"name": key, "classes": []})
                            if matched_label not in all_props[key]["classes"]:
                                all_props[key]["classes"].append(matched_label)

            rel_rows = GraphViewService._run(
                """
                MATCH (a)-[r]->(b)
                WHERE any(la IN labels(a) WHERE la IN $class_names)
                  AND any(lb IN labels(b) WHERE lb IN $class_names)
                  AND coalesce(a.ontology_prefix, a.prefix) = $prefix
                  AND coalesce(b.ontology_prefix, b.prefix) = $prefix
                RETURN DISTINCT type(r) AS rel_type,
                                head([la IN labels(a) WHERE la IN $class_names]) AS from_class,
                                head([lb IN labels(b) WHERE lb IN $class_names]) AS to_class
                LIMIT toInteger($relationship_limit)
                """,
                {
                    "class_names": class_names,
                    "prefix": normalized_prefix,
                    "relationship_limit": relationship_limit,
                },
            )
            for row in (rel_rows or []):
                rel_type = row.get("rel_type")
                if not rel_type:
                    continue
                relationships.setdefault(rel_type, {"type": rel_type, "connections": []})
                from_class = row.get("from_class")
                to_class = row.get("to_class")
                if from_class and to_class:
                    relationships[rel_type]["connections"].append({"from": from_class, "to": to_class})

            oc_rows = GraphViewService._run(
                """
                MATCH (a:OntologyClass)-[r]->(b:OntologyClass)
                WHERE coalesce(a.ontology_prefix, a.prefix) = $prefix
                  AND coalesce(b.ontology_prefix, b.prefix) = $prefix
                RETURN DISTINCT type(r) AS rel_type,
                                a.name AS from_class,
                                b.name AS to_class
                LIMIT toInteger($relationship_limit)
                """,
                {"prefix": normalized_prefix, "relationship_limit": relationship_limit},
            )
            for row in (oc_rows or []):
                rel_type = row.get("rel_type")
                if not rel_type:
                    continue
                relationships.setdefault(rel_type, {"type": rel_type, "connections": []})
                from_class = row.get("from_class")
                to_class = row.get("to_class")
                if from_class and to_class:
                    relationships[rel_type]["connections"].append({"from": from_class, "to": to_class})

            prop_rows = GraphViewService._run(
                """
                MATCH (p:OntologyProperty)-[:PROPERTY_OF]->(c:OntologyClass)
                WHERE coalesce(p.ontology_prefix, p.prefix) = $prefix
                  AND coalesce(c.ontology_prefix, c.prefix) = $prefix
                RETURN DISTINCT 'PROPERTY_OF' AS rel_type,
                                coalesce(p.name, p.id) AS from_term,
                                c.name AS to_term
                LIMIT toInteger($relationship_limit)
                """,
                {"prefix": normalized_prefix, "relationship_limit": relationship_limit},
            )
            for row in (prop_rows or []):
                rel_type = row.get("rel_type")
                if not rel_type:
                    continue
                relationships.setdefault(rel_type, {"type": rel_type, "connections": []})
                from_term = str(row.get("from_term") or "").strip()
                to_term = str(row.get("to_term") or "").strip()
                if from_term and to_term:
                    relationships[rel_type]["connections"].append({"from": from_term, "to": to_term})

            if not relationships and class_names:
                inst_rel_rows = GraphViewService._run(
                    """
                    MATCH (a:Instance {prefix: $prefix})-[r]->(b:Instance {prefix: $prefix})
                    WHERE a.type IN $class_names AND b.type IN $class_names
                    RETURN DISTINCT type(r) AS rel_type,
                                    a.type AS from_class,
                                    b.type AS to_class
                    LIMIT toInteger($relationship_limit)
                    """,
                    {
                        "class_names": class_names,
                        "prefix": normalized_prefix,
                        "relationship_limit": relationship_limit,
                    },
                )
                for row in (inst_rel_rows or []):
                    rel_type = row.get("rel_type")
                    if not rel_type:
                        continue
                    relationships.setdefault(rel_type, {"type": rel_type, "connections": []})
                    from_class = row.get("from_class")
                    to_class = row.get("to_class")
                    if from_class and to_class:
                        relationships[rel_type]["connections"].append({"from": from_class, "to": to_class})

        if not entities:
            inst_fallback = GraphViewService._run(
                """
                MATCH (n)
                WHERE coalesce(n.ontology_prefix, n.prefix) = $prefix
                  AND NOT (n:DatasheetChunk OR n:GraphChunk)
                WITH labels(n) AS lbls, keys(n) AS ks
                UNWIND lbls AS lbl
                WITH lbl, collect(DISTINCT ks) AS prop_sets
                RETURN lbl, prop_sets
                LIMIT toInteger($fallback_limit)
                """,
                {"prefix": normalized_prefix, "fallback_limit": fallback_limit},
            )
            for row in (inst_fallback or []):
                lbl = row.get("lbl")
                if not lbl or lbl in ("OntologyClass", "OntologyProperty"):
                    continue
                props = sorted({
                    key
                    for prop_set in (row.get("prop_sets") or [])
                    for key in prop_set
                    if key and key not in cls.INTERNAL_DICTIONARY_PROPS
                })
                if lbl not in entities:
                    entities[lbl] = {
                        "type": lbl,
                        "concept_type": "Class",
                        "namespace": normalized_prefix,
                        "ontology_prefix": normalized_prefix,
                        "source": "instance",
                        "properties": props,
                    }
                for prop_name in props:
                    all_props.setdefault(prop_name, {"name": prop_name, "classes": []})
                    if lbl not in all_props[prop_name]["classes"]:
                        all_props[prop_name]["classes"].append(lbl)

        if not entities and not all_props:
            raise ValueError(
                f"No data found in Neo4j for ontology prefix '{normalized_prefix}'. Commit an import with this prefix first."
            )

        return {
            "uri": f"{cls.config().base_url}/oslc/dictionaries/{normalized_prefix}",
            "type": "oslc:DomainDictionary",
            "title": f"{normalized_prefix} data dictionary",
            "status": "success",
            "ontology": normalized_prefix,
            "data": {
                "entities": entities,
                "relationships": relationships,
                "properties": all_props,
            },
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "property_count": len(all_props),
            "source": "neo4j_live",
        }

    @classmethod
    def query_resources(cls, resource_type: str, params: OSLCQueryParameters) -> Dict[str, Any]:
        requested_resource_type = str(resource_type or "").strip()
        normalized_resource_type = requested_resource_type.lower()
        ontology_scope = cls._ontology_domain_scope(requested_resource_type)
        if ontology_scope:
            query_resource_type = cls.DEFAULT_RESOURCE_TYPE
        elif normalized_resource_type in cls.SUPPORTED_RESOURCE_TYPES:
            query_resource_type = normalized_resource_type
        else:
            raise ValueError(f"Unsupported OSLC resource type: {resource_type}")
        cfg = cls.config()
        rows = GraphViewService._run(*cls._build_resource_query(params, query_resource_type, ontology_scope))
        total_rows = GraphViewService._run(*cls._build_count_query(params, query_resource_type, ontology_scope))
        total_count = int(total_rows[0].get("count", 0)) if total_rows else 0
        response_resource_type = requested_resource_type if ontology_scope else query_resource_type
        members = [cls._row_to_resource_payload(row, params.select, response_resource_type) for row in rows]
        return {
            "uri": f"{cfg.base_url}/oslc/query/{response_resource_type}",
            "type": "oslc:QueryResult",
            "resourceType": response_resource_type,
            "oslc:totalCount": total_count,
            "page": params.page_num,
            "pageSize": params.page_size,
            "members": members,
        }

    @classmethod
    def _ontology_domain_scope(cls, resource_type: str) -> Optional[Dict[str, str]]:
        """Return the persisted ontology scope represented by ``ontology:<id>``.

        OSLC providers may advertise many ontology domains.  Resolving the id
        against the registry before building Cypher keeps those advertised
        query capabilities real and prevents arbitrary prefix filtering.
        """
        prefix, separator, ontology_id = str(resource_type or "").partition(":")
        if prefix.lower() != "ontology" or not separator or not ontology_id.strip():
            return None
        requested_id = ontology_id.strip()
        for domain in cls._ontology_domains():
            if domain["ontology_id"] == requested_id:
                return {"ontology_id": requested_id, "prefix": domain["prefix"]}
        return None

    @classmethod
    def get_resource(cls, element_id: str) -> Optional[Dict[str, Any]]:
        rows = GraphViewService._run(
            """
            MATCH (n)
            WHERE elementId(n) = $element_id
              AND NOT (n:DatasheetChunk OR n:GraphChunk)
            OPTIONAL MATCH (n)-[r]->(m)
            WHERE NOT (m:DatasheetChunk OR m:GraphChunk)
            RETURN
              elementId(n) AS element_id,
              labels(n) AS labels,
              properties(n) AS properties,
              collect(DISTINCT {
                relationshipType: type(r),
                relationshipElementId: elementId(r),
                targetElementId: elementId(m),
                targetLabels: labels(m),
                targetProperties: {
                  element_type: m.element_type,
                  entity_type: m.entity_type,
                  type: m.type,
                  semantic_role: m.semantic_role,
                  source_format: m.source_format
                },
                targetName: coalesce(m.name, m.title, m.code, m.label, m.id, elementId(m))
              }) AS outgoing
            LIMIT 1
            """,
            {"element_id": element_id},
        )
        if not rows:
            return None
        return cls._resource_detail_payload(rows[0])

    @classmethod
    def _build_resource_query(
        cls,
        params: OSLCQueryParameters,
        resource_type: str = DEFAULT_RESOURCE_TYPE,
        ontology_scope: Optional[Dict[str, str]] = None,
    ):
        where_clauses = ["NOT (n:DatasheetChunk OR n:GraphChunk)"]
        domain_predicate = cls._resource_type_predicate(resource_type)
        if domain_predicate:
            where_clauses.append(domain_predicate)
        cypher_params: Dict[str, Any] = {
            "skip": (params.page_num - 1) * params.page_size,
            "limit": params.page_size,
        }
        if ontology_scope:
            where_clauses.append(
                "(toString(coalesce(n.ontology_id, '')) = $ontology_id "
                "OR toString(coalesce(n.ontology_prefix, n.prefix, '')) = $ontology_prefix)"
            )
            cypher_params.update({"ontology_id": ontology_scope["ontology_id"], "ontology_prefix": ontology_scope["prefix"]})

        for index, condition in enumerate(params.where):
            where_clauses.append(cls._condition_to_cypher(condition, index, cypher_params))

        search_predicates = []
        search_score_parts = []
        for term_index, term in enumerate(cls._normalized_search_terms(params.search_terms)):
            term_key = f"search_term_{term_index}"
            cypher_params[term_key] = term.lower()
            predicate = cls._search_term_predicate(term_key)
            search_predicates.append(predicate)
            search_score_parts.append(f"CASE WHEN {predicate} THEN 1 ELSE 0 END")
        if search_predicates:
            where_clauses.append(f"({' OR '.join(search_predicates)})")

        base_order_by = cls._build_order_by(params.order_by)
        if search_score_parts:
            tie_breakers = base_order_by.removeprefix("ORDER BY ")
            order_by = f"ORDER BY search_score DESC, {tie_breakers}"
            search_score_projection = f", ({' + '.join(search_score_parts)}) AS search_score"
        else:
            order_by = base_order_by
            search_score_projection = ""

        cypher = f"""
        MATCH (n)
        WHERE {' AND '.join(clause.strip() for clause in where_clauses)}
        RETURN elementId(n) AS element_id,
               labels(n) AS labels,
               properties(n) AS properties
               {search_score_projection}
        {order_by}
        SKIP $skip
        LIMIT $limit
        """
        return cypher, cypher_params

    @classmethod
    def _build_count_query(
        cls,
        params: OSLCQueryParameters,
        resource_type: str = DEFAULT_RESOURCE_TYPE,
        ontology_scope: Optional[Dict[str, str]] = None,
    ):
        where_clauses = ["NOT (n:DatasheetChunk OR n:GraphChunk)"]
        domain_predicate = cls._resource_type_predicate(resource_type)
        if domain_predicate:
            where_clauses.append(domain_predicate)
        cypher_params: Dict[str, Any] = {}
        if ontology_scope:
            where_clauses.append(
                "(toString(coalesce(n.ontology_id, '')) = $ontology_id "
                "OR toString(coalesce(n.ontology_prefix, n.prefix, '')) = $ontology_prefix)"
            )
            cypher_params.update({"ontology_id": ontology_scope["ontology_id"], "ontology_prefix": ontology_scope["prefix"]})
        for index, condition in enumerate(params.where):
            where_clauses.append(cls._condition_to_cypher(condition, index, cypher_params))
        search_predicates = []
        for term_index, term in enumerate(cls._normalized_search_terms(params.search_terms)):
            term_key = f"search_term_{term_index}"
            cypher_params[term_key] = term.lower()
            search_predicates.append(cls._search_term_predicate(term_key))
        if search_predicates:
            where_clauses.append(f"({' OR '.join(search_predicates)})")
        cypher = f"""
        MATCH (n)
        WHERE {' AND '.join(clause.strip() for clause in where_clauses)}
        RETURN count(n) AS count
        """
        return cypher, cypher_params

    @classmethod
    def _resource_type_predicate(cls, resource_type: str) -> str:
        normalized = str(resource_type or cls.DEFAULT_RESOURCE_TYPE).strip().lower()
        requirement = (
            "(any(lbl IN labels(n) WHERE toLower(lbl) IN "
            "['requirement', 'requirementrevision', 'oslcrequirement', 'reqifspecobject']) OR "
            "toLower(coalesce(toString(n.semantic_role), '')) = 'requirement' OR "
            "toLower(coalesce(toString(n.element_type), toString(n.entity_type), '')) IN "
            "['requirement', 'requirementrevision'])"
        )
        collection = (
            "(any(lbl IN labels(n) WHERE toLower(lbl) IN "
            "['specification', 'requirementcollection', 'reqifspecification']) OR "
            "toLower(coalesce(toString(n.semantic_role), '')) = 'requirement_specification' OR "
            "toLower(coalesce(toString(n.element_type), toString(n.entity_type), '')) IN "
            "['specification', 'requirementcollection'])"
        )
        if normalized == cls.DEFAULT_RESOURCE_TYPE:
            return ""
        if normalized == cls.RM_REQUIREMENT_TYPE:
            return requirement
        if normalized == cls.RM_COLLECTION_TYPE:
            return collection
        if normalized == cls.AM_RESOURCE_TYPE:
            architecture = (
                "(n:ModelElement OR any(lbl IN labels(n) WHERE toLower(lbl) IN "
                "['system', 'subsystem', 'component', 'interface', 'function', 'capability', "
                "'operationalactivity', 'performer', 'package', 'project', 'usecase', 'actor', "
                "'activity', 'signal', 'flowport', 'itemflow', 'constraintblock', 'view']) OR "
                "toLower(coalesce(toString(n.source_format), '')) IN "
                "['xmi', 'mdxml', 'sysml', 'uml', 'archimate'] OR "
                "toLower(coalesce(toString(n.type), '')) CONTAINS 'uml:' OR "
                "toLower(coalesce(toString(n.type), '')) CONTAINS 'sysml:' OR "
                "toLower(coalesce(toString(n.archimate_type), '')) <> '')"
            )
            return f"({architecture} AND NOT {requirement} AND NOT {collection})"
        raise ValueError(f"Unsupported OSLC resource type: {resource_type}")

    @staticmethod
    def _search_term_predicate(term_key: str) -> str:
        return (
            "("
            f"toLower(coalesce(toString(properties(n)['name']), '')) CONTAINS ${term_key} OR "
            f"toLower(coalesce(toString(properties(n)['title']), '')) CONTAINS ${term_key} OR "
            f"toLower(coalesce(toString(properties(n)['code']), '')) CONTAINS ${term_key} OR "
            f"toLower(coalesce(toString(properties(n)['label']), '')) CONTAINS ${term_key} OR "
            f"toLower(coalesce(toString(properties(n)['id']), '')) CONTAINS ${term_key} OR "
            f"any(key IN keys(n) WHERE toLower(coalesce(toString(properties(n)[key]), '')) CONTAINS ${term_key})"
            ")"
        )

    @staticmethod
    def _condition_to_cypher(condition: OSLCCondition, index: int, params: Dict[str, Any]) -> str:
        value_key = f"where_value_{index}"
        property_key = f"where_property_{index}"
        property_name = str(condition.property_name or "").strip()
        params[value_key] = condition.value
        params[property_key] = property_name
        operator_map = {
            "=": "=",
            "!=": "<>",
            ">": ">",
            "<": "<",
            ">=": ">=",
            "<=": "<=",
        }
        operator = operator_map[condition.operator]
        if property_name.lower() in {"type", "rdf:type", "label", "labels"}:
            if condition.operator == "=":
                return f"any(lbl IN labels(n) WHERE toLower(lbl) = toLower(toString($${value_key})))".replace("$$", "$")
            if condition.operator == "!=":
                return f"none(lbl IN labels(n) WHERE toLower(lbl) = toLower(toString($${value_key})))".replace("$$", "$")
            return f"any(lbl IN labels(n) WHERE toLower(lbl) {operator} toLower(toString($${value_key})))".replace("$$", "$")
        if isinstance(condition.value, (int, float)) and not isinstance(condition.value, bool):
            return f"toFloat(properties(n)[$${property_key}]) {operator} toFloat($${value_key})".replace("$$", "$")
        return f"coalesce(toString(properties(n)[$${property_key}]), '') {operator} toString($${value_key})".replace("$$", "$")

    @staticmethod
    def _normalized_search_terms(search_terms: Any) -> List[str]:
        if isinstance(search_terms, str):
            return [search_terms.strip()] if search_terms.strip() else []
        return [str(term).strip() for term in (search_terms or []) if str(term).strip()]

    @staticmethod
    def _build_order_by(order_by: List[tuple[str, str]]) -> str:
        if not order_by:
            return "ORDER BY toLower(coalesce(toString(properties(n)['name']), toString(properties(n)['title']), toString(properties(n)['code']), toString(properties(n)['label']), toString(properties(n)['id']), elementId(n))) ASC"

        fragments = []
        for field_name, direction in order_by:
            sort_dir = "DESC" if str(direction).lower() == "desc" else "ASC"
            safe_name = field_name.replace("'", "")
            if safe_name.lower() in {"type", "rdf:type", "label", "labels"}:
                fragments.append(
                    "reduce(label_key = '', lbl IN labels(n) | "
                    "CASE WHEN label_key = '' OR toLower(lbl) < label_key "
                    f"THEN toLower(lbl) ELSE label_key END) {sort_dir}"
                )
            else:
                fragments.append(f"toLower(toString(coalesce(properties(n)['{safe_name}'], ''))) {sort_dir}")
        return "ORDER BY " + ", ".join(fragments)

    @classmethod
    def resource_domain_types(cls, labels: List[str], properties: Dict[str, Any]) -> List[str]:
        """Return OSLC domain RDF types inferred from stable graph discriminators."""
        lowered_labels = {str(label).strip().lower() for label in (labels or [])}
        lowered = {
            key: str((properties or {}).get(key) or "").strip().lower()
            for key in ("semantic_role", "element_type", "entity_type", "type", "source_format", "archimate_type")
        }
        if (
            lowered_labels.intersection({"requirement", "requirementrevision", "oslcrequirement", "reqifspecobject"})
            or lowered["semantic_role"] == "requirement"
            or lowered["element_type"] in {"requirement", "requirementrevision"}
            or lowered["entity_type"] in {"requirement", "requirementrevision"}
        ):
            return [cls.RM_REQUIREMENT_URI]
        if (
            lowered_labels.intersection({"specification", "requirementcollection", "reqifspecification"})
            or lowered["semantic_role"] == "requirement_specification"
            or lowered["element_type"] in {"specification", "requirementcollection"}
            or lowered["entity_type"] in {"specification", "requirementcollection"}
        ):
            return [cls.RM_COLLECTION_URI]
        architecture_labels = {
            "modelelement", "system", "subsystem", "component", "interface", "function", "capability",
            "operationalactivity", "performer", "package", "project", "usecase", "actor", "activity",
            "signal", "flowport", "itemflow", "constraintblock", "view",
        }
        if (
            lowered_labels.intersection(architecture_labels)
            or lowered["source_format"] in {"xmi", "mdxml", "sysml", "uml", "archimate"}
            or "uml:" in lowered["type"]
            or "sysml:" in lowered["type"]
            or bool(lowered["archimate_type"])
        ):
            return [cls.AM_TYPE_URI]
        return []

    @classmethod
    def _profile_type_uris(cls, resource_type: str, labels: List[str], properties: Dict[str, Any]) -> List[str]:
        normalized = str(resource_type or cls.DEFAULT_RESOURCE_TYPE).strip().lower()
        explicit = {
            cls.AM_RESOURCE_TYPE: [cls.AM_TYPE_URI],
            cls.RM_REQUIREMENT_TYPE: [cls.RM_REQUIREMENT_URI],
            cls.RM_COLLECTION_TYPE: [cls.RM_COLLECTION_URI],
        }.get(normalized)
        return explicit or cls.resource_domain_types(labels, properties)

    @classmethod
    def _shape_for_types(cls, type_uris: List[str]) -> Optional[str]:
        type_to_shape = {
            cls.AM_TYPE_URI: cls.AM_RESOURCE_TYPE,
            cls.RM_REQUIREMENT_URI: cls.RM_REQUIREMENT_TYPE,
            cls.RM_COLLECTION_URI: cls.RM_COLLECTION_TYPE,
        }
        shape_id = next((type_to_shape[item] for item in type_uris if item in type_to_shape), None)
        return f"{cls.config().base_url}/oslc/shapes/{shape_id}" if shape_id else None

    @classmethod
    def _row_to_resource_payload(
        cls,
        row: Dict[str, Any],
        selected_fields: List[str],
        resource_type: str = DEFAULT_RESOURCE_TYPE,
    ) -> Dict[str, Any]:
        properties = dict(row.get("properties") or {})
        cfg = cls.config()
        encoded_id = quote(str(row.get('element_id') or ''), safe='')
        resource_uri = f"{cfg.base_url}/oslc/resources/{encoded_id}"
        types = row.get("labels") or []
        domain_types = cls._profile_type_uris(resource_type, types, properties)
        rdf_types = domain_types or types
        title = properties.get("name") or properties.get("title") or properties.get("code") or properties.get("label") or properties.get("id") or row.get("element_id")
        if selected_fields:
            selected = {}
            for field_name in selected_fields:
                normalized = field_name.lower()
                if normalized in {"uri", "rdf:about"}:
                    selected[field_name] = resource_uri
                elif normalized in {"type", "types", "rdf:type", "label", "labels"}:
                    selected[field_name] = rdf_types
                elif normalized in {"title", "dcterms:title"}:
                    selected[field_name] = title
                elif normalized in {"elementid", "element_id"}:
                    selected[field_name] = row.get("element_id")
                else:
                    selected[field_name] = properties.get(field_name)
        else:
            selected = properties
        payload = {
            "uri": resource_uri,
            "elementId": row.get("element_id"),
            "types": types,
            "rdf:type": rdf_types,
            "oslc:serviceProvider": f"{cfg.base_url}/oslc/providers/{cfg.provider_id}",
            "title": title,
            "properties": selected,
        }
        instance_shape = cls._shape_for_types(domain_types)
        if instance_shape:
            payload["oslc:instanceShape"] = instance_shape
        if row.get("search_score") is not None:
            payload["oslc:score"] = max(0, min(100, int(row.get("search_score") or 0)))
        return payload

    @classmethod
    def _resource_detail_payload(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        properties = dict(row.get("properties") or {})
        cfg = cls.config()
        labels = row.get("labels") or []
        domain_types = cls.resource_domain_types(labels, properties)
        links = [
            {
                **item,
                "targetUri": f"{cfg.base_url}/oslc/resources/{quote(str(item.get('targetElementId') or ''), safe='')}",
                "predicate": "http://purl.org/dc/terms/relation",
                "targetRdfTypes": cls.resource_domain_types(
                    item.get("targetLabels") or [], item.get("targetProperties") or {}
                ),
            }
            for item in (row.get("outgoing") or [])
            if item and item.get("relationshipType") and item.get("targetElementId")
        ]
        payload = {
            "uri": f"{cfg.base_url}/oslc/resources/{quote(str(row.get('element_id') or ''), safe='')}",
            "elementId": row.get("element_id"),
            "types": labels,
            "rdf:type": domain_types or labels,
            "oslc:serviceProvider": f"{cfg.base_url}/oslc/providers/{cfg.provider_id}",
            "title": properties.get("name") or properties.get("title") or properties.get("code") or properties.get("label") or properties.get("id") or row.get("element_id"),
            "properties": properties,
            "outgoingLinks": links,
        }
        instance_shape = cls._shape_for_types(domain_types)
        if instance_shape:
            payload["oslc:instanceShape"] = instance_shape
        return payload
