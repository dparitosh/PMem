"""Ontology-based model workbench service.

This service is intentionally small and stable: Neo4j stores modeled elements as
(:ModelElement) nodes and modeled relationships as [:MODEL_REL] edges with a
`type` property. That keeps Cypher fully parameterized and avoids unsafe dynamic
labels/relationship types while still supporting ArchiMate/MBSE/UAF/PLM concepts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from backend.core.graph import query_with_timeout

_METAMODEL_PATH = Path(__file__).resolve().parents[1] / "config" / "modeling_metamodel.json"


def _load_metamodel_config() -> Dict[str, Any]:
    try:
        return json.loads(_METAMODEL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


_METAMODEL_CONFIG = _load_metamodel_config()

ALLOWED_ELEMENT_TYPES = set(_METAMODEL_CONFIG.get("element_types") or [
    "Capability",
    "OperationalActivity",
    "Resource",
    "Performer",
    "Requirement",
    "Function",
    "Interface",
    "Product",
    "Part",
    "Document",
    "Package",
    "Project",
])

REQUIRED_PROPERTIES = _METAMODEL_CONFIG.get("required_properties") or {
    "Capability": ["name"],
    "OperationalActivity": ["name"],
    "Resource": ["name"],
    "Performer": ["name"],
    "Requirement": ["name", "text"],
    "Function": ["name"],
    "Interface": ["name"],
    "Product": ["name"],
    "Part": ["name"],
    "Document": ["name"],
    "Package": ["name"],
    "Project": ["name"],
}

VALID_RELATIONSHIP_TYPES = set(_METAMODEL_CONFIG.get("relationship_types") or [
    "CONTAINS",
    "SATISFIES",
    "VERIFIES",
    "ALLOCATED_TO",
    "PERFORMS",
    "COMPOSED_OF",
    "REALIZES",
    "INTERFACES_WITH",
    "REFERENCES",
    "TRACE_TO",
    "DEPENDS_ON",
    "IMPLEMENTS",
])

DEFAULT_PROJECT = "Digital Engineering Model"
MAX_LIMIT = 2000


def _clean_text(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _safe_limit(limit: int | str | None, default: int = 500) -> int:
    try:
        parsed = int(limit or default)
    except Exception:
        parsed = default
    return max(1, min(parsed, MAX_LIMIT))


def _element_type(value: Any) -> str:
    requested = _clean_text(value, "Function")
    return requested if requested in ALLOWED_ELEMENT_TYPES else "Function"


def _relationship_type(value: Any) -> str:
    requested = re.sub(r"[^A-Za-z0-9_]+", "_", _clean_text(value, "TRACE_TO")).upper().strip("_")
    return requested if requested in VALID_RELATIONSHIP_TYPES else "TRACE_TO"


def _properties(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_node(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not row:
        return None
    props = dict(row.get("properties") or {})
    label = props.get("label") or props.get("name") or row.get("label") or row.get("id")
    try:
        x_value = float(props.get("x")) if props.get("x") is not None else None
        y_value = float(props.get("y")) if props.get("y") is not None else None
    except Exception:
        x_value = None
        y_value = None
    return {
        "id": row.get("elementId") or row.get("id"),
        "label": label,
        "type": props.get("type") or row.get("type") or "Function",
        "properties": props,
        "x": x_value,
        "y": y_value,
    }


def _normalize_link(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not row:
        return None
    props = dict(row.get("properties") or {})
    return {
        "id": row.get("elementId") or row.get("id"),
        "source": row.get("source"),
        "target": row.get("target"),
        "type": props.get("type") or row.get("type") or "TRACE_TO",
        "properties": props,
    }


def _graph_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    links: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        for key in ("n", "m"):
            node = _normalize_node(row.get(key))
            if node and node.get("id"):
                nodes[node["id"]] = node
        link = _normalize_link(row.get("r"))
        if link and link.get("id") and link.get("source") in nodes and link.get("target") in nodes:
            links[link["id"]] = link
    return {
        "nodes": list(nodes.values()),
        "links": list(links.values()),
        "counts": {"nodes": len(nodes), "links": len(links)},
    }


def metamodel() -> Dict[str, Any]:
    return {
        "name": _METAMODEL_CONFIG.get("name", "Ontology Modeling Metamodel"),
        "version": _METAMODEL_CONFIG.get("version", "1.0"),
        "profiles": _METAMODEL_CONFIG.get("profiles", ["OWL", "UAF", "SysML", "ArchiMate", "PLM"]),
        "element_types": sorted(ALLOWED_ELEMENT_TYPES),
        "relationship_types": sorted(VALID_RELATIONSHIP_TYPES),
        "required_properties": REQUIRED_PROPERTIES,
        "colors": _METAMODEL_CONFIG.get("colors", {}),
    }


def ensure_indexes() -> Dict[str, Any]:
    queries = [
        "CREATE INDEX model_element_uid IF NOT EXISTS FOR (n:ModelElement) ON (n.uid)",
        "CREATE INDEX model_element_project IF NOT EXISTS FOR (n:ModelElement) ON (n.project)",
        "CREATE INDEX model_element_project_uid IF NOT EXISTS FOR (n:ModelElement) ON (n.project, n.uid)",
        "CREATE INDEX model_element_type IF NOT EXISTS FOR (n:ModelElement) ON (n.type)",
        "CREATE INDEX model_element_label IF NOT EXISTS FOR (n:ModelElement) ON (n.label)",
    ]
    for query in queries:
        query_with_timeout(query, {}, timeout=60)
    return {"status": "success", "indexes": len(queries)}


def list_graph(project: str = DEFAULT_PROJECT, search: str = "", limit: int = 500) -> Dict[str, Any]:
    limit_value = _safe_limit(limit)
    search_value = _clean_text(search).lower()
    rows = query_with_timeout(
        """
        MATCH (n:ModelElement)
        WHERE coalesce(n.project, $project) = $project
          AND (
            $search = '' OR toLower(coalesce(n.label, n.name, n.uid, '')) CONTAINS $search
            OR any(k IN keys(n) WHERE toLower(k) CONTAINS $search OR toLower(toString(n[k])) CONTAINS $search)
          )
        OPTIONAL MATCH (n)-[r:MODEL_REL]-(m:ModelElement)
        WHERE m IS NULL OR coalesce(m.project, $project) = $project
        WITH n, r, m
        ORDER BY coalesce(n.package, ''), coalesce(n.label, n.name, n.uid), type(r), coalesce(m.label, m.name, m.uid)
        LIMIT $limit
        RETURN
          {elementId: elementId(n), properties: properties(n)} AS n,
          CASE WHEN r IS NULL THEN null ELSE {elementId: elementId(r), source: elementId(startNode(r)), target: elementId(endNode(r)), type: type(r), properties: properties(r)} END AS r,
          CASE WHEN m IS NULL THEN null ELSE {elementId: elementId(m), properties: properties(m)} END AS m
        """,
        {"project": project or DEFAULT_PROJECT, "search": search_value, "limit": limit_value},
        timeout=60,
    ) or []
    graph = _graph_from_rows(rows)
    graph["project"] = project or DEFAULT_PROJECT
    graph["search"] = search
    return graph


def tree(project: str = DEFAULT_PROJECT) -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH (n:ModelElement)
        WHERE coalesce(n.project, $project) = $project
        RETURN elementId(n) AS id,
               coalesce(n.label, n.name, n.uid, elementId(n)) AS label,
               coalesce(n.type, 'Function') AS type,
               coalesce(n.package, 'Model') AS package
        ORDER BY package, type, label
        LIMIT 2000
        """,
        {"project": project or DEFAULT_PROJECT},
        timeout=60,
    ) or []
    packages: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        pkg = row.get("package") or "Model"
        packages.setdefault(pkg, {"id": f"package::{pkg}", "label": pkg, "type": "Package", "children": []})
        packages[pkg]["children"].append(row)
    return {
        "project": project or DEFAULT_PROJECT,
        "tree": [{"id": "project", "label": project or DEFAULT_PROJECT, "type": "Project", "children": list(packages.values())}],
    }


def search(query: str, project: str = DEFAULT_PROJECT, limit: int = 50) -> Dict[str, Any]:
    q = _clean_text(query).lower().replace("*", "")
    if not q:
        return {"results": []}
    rows = query_with_timeout(
        """
        MATCH (n:ModelElement)
        WHERE coalesce(n.project, $project) = $project
          AND (
            toLower(coalesce(n.label, n.name, n.uid, '')) CONTAINS $q
            OR toLower(coalesce(n.type, '')) CONTAINS $q
            OR any(k IN keys(n) WHERE toLower(k) CONTAINS $q OR toLower(toString(n[k])) CONTAINS $q)
          )
        RETURN elementId(n) AS id, coalesce(n.label, n.name, n.uid, elementId(n)) AS label,
               coalesce(n.type, 'Function') AS type, properties(n) AS properties
        ORDER BY CASE WHEN toLower(coalesce(n.label, n.name, '')) STARTS WITH $q THEN 0 ELSE 1 END, label
        LIMIT $limit
        """,
        {"project": project or DEFAULT_PROJECT, "q": q, "limit": _safe_limit(limit, 50)},
        timeout=60,
    ) or []
    return {"results": rows, "query": query}


def context(element_id: str, depth: int = 1, limit: int = 300) -> Dict[str, Any]:
    depth_value = 1 if int(depth or 1) <= 1 else 2
    pattern = "MATCH path = (root)-[:MODEL_REL*0..1]-(n:ModelElement)" if depth_value == 1 else "MATCH path = (root)-[:MODEL_REL*0..2]-(n:ModelElement)"
    cypher = f"""
        MATCH (root:ModelElement)
        WHERE elementId(root) = $id
        {pattern}
        WITH collect(DISTINCT n)[0..$limit] AS ns
        UNWIND ns AS n
        OPTIONAL MATCH (n)-[r:MODEL_REL]-(m:ModelElement)
        WHERE m IN ns
        RETURN DISTINCT
          {{elementId: elementId(n), properties: properties(n)}} AS n,
          CASE WHEN r IS NULL THEN null ELSE {{elementId: elementId(r), source: elementId(startNode(r)), target: elementId(endNode(r)), type: type(r), properties: properties(r)}} END AS r,
          CASE WHEN m IS NULL THEN null ELSE {{elementId: elementId(m), properties: properties(m)}} END AS m
        LIMIT $limit
        """
    rows = query_with_timeout(
        cypher,
        {"id": element_id, "limit": _safe_limit(limit, 300)},
        timeout=60,
    ) or []
    graph = _graph_from_rows(rows)
    graph["root_id"] = element_id
    graph["depth"] = depth_value
    return graph


def create_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    props = _properties(payload.get("properties"))
    node_type = _element_type(payload.get("type") or props.get("type"))
    label = _clean_text(payload.get("label") or props.get("label") or props.get("name") or node_type)
    uid = _clean_text(payload.get("uid") or props.get("uid") or f"{node_type}:{label}")
    project = _clean_text(payload.get("project") or props.get("project") or DEFAULT_PROJECT)
    package = _clean_text(payload.get("package") or props.get("package") or "Model")
    props = {
        **props,
        "uid": uid,
        "label": label,
        "name": props.get("name") or label,
        "type": node_type,
        "project": project,
        "package": package,
        "x": props.get("x"),
        "y": props.get("y"),
    }
    props = {key: value for key, value in props.items() if value is not None}
    rows = query_with_timeout(
        """
        MERGE (n:ModelElement {project: $project, uid: $uid})
        ON CREATE SET n.created_at = datetime()
        SET n += $props, n.updated_at = datetime()
        RETURN {elementId: elementId(n), properties: properties(n)} AS n
        """,
        {"project": project, "uid": uid, "props": props},
        timeout=60,
    ) or []
    return {"node": _normalize_node(rows[0].get("n") if rows else None)}


def update_node(element_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    props = _properties(payload.get("properties"))
    if payload.get("label"):
        props["label"] = _clean_text(payload.get("label"))
        props.setdefault("name", props["label"])
    if payload.get("type"):
        props["type"] = _element_type(payload.get("type"))
    rows = query_with_timeout(
        """
        MATCH (n:ModelElement)
        WHERE elementId(n) = $id
        SET n += $props, n.updated_at = datetime()
        RETURN {elementId: elementId(n), properties: properties(n)} AS n
        """,
        {"id": element_id, "props": props},
        timeout=60,
    ) or []
    return {"node": _normalize_node(rows[0].get("n") if rows else None)}


def delete_node(element_id: str) -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH (n:ModelElement)
        WHERE elementId(n) = $id
        WITH n, elementId(n) AS id
        DETACH DELETE n
        RETURN id
        """,
        {"id": element_id},
        timeout=60,
    ) or []
    return {"deleted": bool(rows), "id": element_id}


def create_link(payload: Dict[str, Any]) -> Dict[str, Any]:
    props = _properties(payload.get("properties"))
    rel_type = _relationship_type(payload.get("type") or props.get("type"))
    source = _clean_text(payload.get("source"))
    target = _clean_text(payload.get("target"))
    props = {**props, "type": rel_type, "label": props.get("label") or rel_type}
    rows = query_with_timeout(
        """
        MATCH (a:ModelElement), (b:ModelElement)
        WHERE elementId(a) = $source AND elementId(b) = $target
        MERGE (a)-[r:MODEL_REL {type: $type}]->(b)
        ON CREATE SET r.created_at = datetime()
        SET r += $props, r.updated_at = datetime()
        RETURN {elementId: elementId(r), source: elementId(startNode(r)), target: elementId(endNode(r)), type: type(r), properties: properties(r)} AS r
        """,
        {"source": source, "target": target, "type": rel_type, "props": props},
        timeout=60,
    ) or []
    return {"link": _normalize_link(rows[0].get("r") if rows else None)}


def update_link(element_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    props = _properties(payload.get("properties"))
    if payload.get("type"):
        props["type"] = _relationship_type(payload.get("type"))
        props.setdefault("label", props["type"])
    rows = query_with_timeout(
        """
        MATCH ()-[r:MODEL_REL]->()
        WHERE elementId(r) = $id
        SET r += $props, r.updated_at = datetime()
        RETURN {elementId: elementId(r), source: elementId(startNode(r)), target: elementId(endNode(r)), type: type(r), properties: properties(r)} AS r
        """,
        {"id": element_id, "props": props},
        timeout=60,
    ) or []
    return {"link": _normalize_link(rows[0].get("r") if rows else None)}


def delete_link(element_id: str) -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH ()-[r:MODEL_REL]->()
        WHERE elementId(r) = $id
        WITH r, elementId(r) AS id
        DELETE r
        RETURN id
        """,
        {"id": element_id},
        timeout=60,
    ) or []
    return {"deleted": bool(rows), "id": element_id}


def validate(project: str = DEFAULT_PROJECT) -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH (n:ModelElement)
        WHERE coalesce(n.project, $project) = $project
        OPTIONAL MATCH (n)--(m:ModelElement)
        WITH n, count(m) AS degree
        RETURN elementId(n) AS id, properties(n) AS props, degree
        LIMIT 5000
        """,
        {"project": project or DEFAULT_PROJECT},
        timeout=60,
    ) or []
    seen: Dict[str, int] = {}
    issues: List[Dict[str, Any]] = []
    for row in rows:
        props = row.get("props") or {}
        uid = props.get("uid") or props.get("id") or row.get("id")
        seen[uid] = seen.get(uid, 0) + 1
        node_type = props.get("type") or "Function"
        for required in REQUIRED_PROPERTIES.get(node_type, ["name"]):
            if not _clean_text(props.get(required)):
                issues.append({"severity": "warning", "elementId": row.get("id"), "rule": "missing_required_property", "message": f"{node_type} is missing {required}."})
        if int(row.get("degree") or 0) == 0:
            issues.append({"severity": "info", "elementId": row.get("id"), "rule": "orphan_node", "message": f"{props.get('label') or uid} has no model relationships."})
    for uid, count in seen.items():
        if count > 1:
            issues.append({"severity": "error", "rule": "duplicate_uid", "message": f"Duplicate model uid: {uid}", "count": count})
    return {"issues": issues, "counts": {"issues": len(issues), "nodes_checked": len(rows)}}


def seed_sample(project: str = DEFAULT_PROJECT) -> Dict[str, Any]:
    ensure_indexes()
    nodes = [
        {"uid": "pkg:sys", "label": "System Model", "type": "Package", "package": "Model", "x": 460, "y": 310},
        {"uid": "cap:mission", "label": "Mission Capability", "type": "Capability", "package": "Capabilities", "x": 270, "y": 180},
        {"uid": "op:operate", "label": "Operate System", "type": "OperationalActivity", "package": "Operations", "x": 450, "y": 180},
        {"uid": "req:safety", "label": "Safety Requirement", "type": "Requirement", "package": "Requirements", "text": "System shall remain safe under degraded conditions.", "x": 650, "y": 320},
        {"uid": "fn:monitor", "label": "Monitor Health", "type": "Function", "package": "Functions", "x": 460, "y": 420},
        {"uid": "part:controller", "label": "Controller Assembly", "type": "Part", "package": "Product", "x": 250, "y": 420},
    ]
    for node in nodes:
        create_node({"project": project, "package": node.get("package"), "type": node["type"], "label": node["label"], "uid": node["uid"], "properties": node})
    ids = {row["props"]["uid"]: row["id"] for row in query_with_timeout("MATCH (n:ModelElement) WHERE n.project = $project RETURN elementId(n) AS id, properties(n) AS props", {"project": project}, timeout=60) or []}
    for source, target, typ in [
        ("cap:mission", "op:operate", "REALIZES"),
        ("op:operate", "fn:monitor", "ALLOCATED_TO"),
        ("fn:monitor", "req:safety", "SATISFIES"),
        ("part:controller", "fn:monitor", "PERFORMS"),
        ("pkg:sys", "cap:mission", "CONTAINS"),
    ]:
        if ids.get(source) and ids.get(target):
            create_link({"source": ids[source], "target": ids[target], "type": typ})
    return list_graph(project=project, limit=200)
