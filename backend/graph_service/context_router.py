"""Read-only context endpoints backed by the configured Neo4j graph."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .neo4j_publisher import publisher

router = APIRouter(tags=["graph-context"])


def _display_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("label") or row.get("uri") or row.get("id") or "Unnamed")


def _ontology_node_clause() -> str:
    """Select the active graph projection without querying absent labels."""
    source = publisher.overview(limit=1).get("view", {}).get("source")
    return "n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty" if source == "existing_ontology" else "n:OntologyResource"


def _find_node(name: str) -> dict[str, Any] | None:
    query = str(name or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="A graph term is required")
    node_clause = _ontology_node_clause()
    rows = publisher._session_rows(
        f"MATCH (n) WHERE {node_clause} "
        "WITH n, coalesce(n.name, n.label, n.uri, n.iri) AS display "
        "WHERE toLower(display) CONTAINS toLower($search_text) "
        "RETURN elementId(n) AS id, display AS name, labels(n) AS labels, "
        "coalesce(n.source_ontology, n.ontology_id, n.prefix, 'graph') AS source_tag "
        "ORDER BY CASE WHEN toLower(display) = toLower($search_text) THEN 0 ELSE 1 END, display LIMIT 1",
        search_text=query,
    )
    return rows[0] if rows else None


def _neighbors(node_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    return publisher._session_rows(
        "MATCH (root)-[r]-(neighbor) WHERE elementId(root) = $node_id "
        "RETURN elementId(neighbor) AS id, coalesce(neighbor.name, neighbor.label, neighbor.uri, neighbor.iri) AS name, "
        "labels(neighbor) AS labels, type(r) AS relation_type, "
        "coalesce(neighbor.source_ontology, neighbor.ontology_id, neighbor.prefix, 'graph') AS source_tag "
        "ORDER BY name LIMIT $limit",
        node_id=node_id,
        limit=max(1, min(int(limit), 500)),
    )


def _kind(row: dict[str, Any]) -> str:
    return " ".join(str(value).lower() for value in [*row.get("labels", []), row.get("name", "")])


@router.get("/api/v1/requirements", summary="List normalized requirement resources from the context graph")
def list_requirements(source: str = Query(default="all"), limit: int = Query(default=1000, ge=1, le=5000)) -> dict:
    rows = publisher._session_rows(
        "MATCH (n) WHERE n:Requirement OR any(label IN labels(n) WHERE toLower(label) CONTAINS 'requirement') "
        "RETURN elementId(n) AS requirement_id, coalesce(n.name, n.title, n.label, n.uri) AS title, "
        "coalesce(n.text, n.description, n.comment, '') AS text, labels(n) AS labels, "
        "coalesce(n.source, n.source_ontology, 'Graph') AS source ORDER BY title LIMIT $limit",
        limit=limit,
    )
    if source.strip().lower() != "all":
        rows = [row for row in rows if str(row.get("source", "")).lower() == source.strip().lower()]
    for row in rows:
        row["relationship_count"] = 0
    return {"requirements": rows, "count": len(rows), "source": source}


@router.get("/recommendations/health", summary="Check graph-backed recommendation readiness")
def recommendation_health() -> dict:
    node_count = int(publisher.overview(limit=1).get("counts", {}).get("nodes", 0))
    ready = node_count > 0
    return {
        "status": "ok",
        "readiness": {
            "scenario_ready": ready,
            "message": "Graph context is ready for recommendation queries." if ready else "Load graph context before running recommendation queries.",
            "service_readiness": {"change-impact": ready, "similar-parts": ready, "manufacturing": ready},
        },
    }


@router.post("/recommendations/change-impact", summary="Trace graph-backed semantic change impact")
def change_impact(payload: dict[str, Any]) -> dict:
    root = _find_node(str(payload.get("change_name") or ""))
    if root is None:
        return {"message": "No matching graph term was found.", "impacted_parts": [], "assembly_impact": [], "impacted_requirements": [], "process_impacts": [], "realization_chain": []}
    neighbors = _neighbors(str(root["id"]))
    parts, assemblies, requirements, processes, realization = [], [], [], [], []
    for row in neighbors:
        kind = _kind(row)
        base = {"name": _display_name(row), "source_tag": row.get("source_tag"), "relation_type": row.get("relation_type"), "class_name": ", ".join(row.get("labels") or [])}
        if "requirement" in kind:
            requirements.append({"name": base["name"], "catalogue_id": row.get("id"), "linked_part": root["name"]})
        elif "assembly" in kind:
            assemblies.append({"assembly_name": base["name"], "depth": 1, "from_part": root["name"]})
        elif "process" in kind or "manufactur" in kind:
            processes.append({"name": base["name"], "source_tag": base["source_tag"], "from_part": root["name"]})
        else:
            parts.append(base)
        realization.append({"name": base["name"], "link_type": base["relation_type"], "from_part": root["name"]})
    impact_count = len(neighbors)
    return {
        "change_entity": {"name": root["name"], "source_tag": root.get("source_tag", "graph"), "revision": None},
        "impact_score": min(100, impact_count * 10),
        "impacted_parts": parts,
        "assembly_impact": assemblies,
        "impacted_requirements": requirements,
        "process_impacts": processes,
        "realization_chain": realization,
        "traceability": "Live Neo4j neighborhood; results are read-only and bounded.",
    }


@router.post("/recommendations/similar-parts", summary="Find graph terms with lexical and type similarity")
def similar_parts(payload: dict[str, Any]) -> dict:
    root = _find_node(str(payload.get("part_name") or ""))
    if root is None:
        return {"message": "No matching graph term was found.", "similar_parts": []}
    top_n = max(1, min(int(payload.get("top_n", 10)), 50))
    tokens = [token for token in str(root["name"]).lower().replace("_", " ").split() if len(token) > 2][:4]
    node_clause = _ontology_node_clause()
    rows = publisher._session_rows(
        f"MATCH (n) WHERE ({node_clause}) "
        "AND elementId(n) <> $root_id "
        "WITH n, coalesce(n.name, n.label, n.uri, n.iri) AS name "
        "WHERE any(token IN $tokens WHERE toLower(name) CONTAINS token) "
        "RETURN elementId(n) AS id, name, labels(n) AS labels, coalesce(n.source_ontology, n.ontology_id, n.prefix, 'graph') AS source_tag "
        "ORDER BY name LIMIT $limit",
        root_id=root["id"], tokens=tokens or [str(root["name"]).lower()], limit=top_n,
    )
    source_labels = set(root.get("labels") or [])
    candidates = []
    for index, row in enumerate(rows):
        type_match = bool(source_labels.intersection(set(row.get("labels") or [])))
        candidates.append({
            "name": _display_name(row),
            "similarity_score": max(10, 90 - index * 7 + (10 if type_match else 0)),
            "source_tag_match": type_match,
            "rflp_layer_match": False,
            "shared_assembly": False,
            "traceability_link": "lexical + graph-type match",
        })
    return {"source_part": {"name": root["name"], "source_tag": root.get("source_tag", "graph"), "rflp_layer": None}, "similar_parts": candidates}


@router.post("/recommendations/manufacturing", summary="Find process context linked to a graph term")
def manufacturing_context(payload: dict[str, Any]) -> dict:
    root = _find_node(str(payload.get("part_name") or ""))
    if root is None:
        return {"message": "No matching graph term was found.", "direct_processes": [], "process_instances": [], "related_processes": [], "process_summary": {}}
    neighbors = _neighbors(str(root["id"]))
    process_rows = [row for row in neighbors if "process" in _kind(row) or "manufactur" in _kind(row)]
    direct = [{"process_name": _display_name(row), "source_tag": row.get("source_tag"), "file_name": None} for row in process_rows]
    return {
        "part": {"name": root["name"], "source_tag": root.get("source_tag", "graph")},
        "direct_processes": direct,
        "process_instances": [],
        "related_processes": [],
        "related_part_processes": [],
        "process_summary": {"total_direct": len(direct), "total_instances": 0, "total_related": 0},
        "message": None if direct else "No manufacturing-process nodes are linked to this semantic term yet.",
    }
