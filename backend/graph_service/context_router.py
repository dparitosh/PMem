"""Read-only context endpoints backed by the configured Neo4j graph."""
from __future__ import annotations

from backend.depo_platform.request_bodies import ContextBody
from backend.depo_platform.decision_policy import assess_recommendation

from typing import Any
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from backend.depo_platform.authorization import graph_read_identity
from .neo4j_publisher import publisher

router = APIRouter(tags=["graph-context"], dependencies=[Depends(graph_read_identity)])


def _display_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("label") or row.get("uri") or row.get("id") or "Unnamed")


def _ontology_node_clause() -> str:
    """Select published terms and retained source records for business analysis."""
    from .query_repository import IMPORTED_INSTANCE_FILTER
    return "(((n:OntologyResource OR n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty OR n:AnnotationProperty OR n:NamedIndividual) AND NOT n:StagedOntologyResource AND NOT n:RetainedOntologyIdentity) OR (" + IMPORTED_INSTANCE_FILTER + "))"


def _find_node(name: str, *, node_id: str = "", scope: dict[str, Any] | None = None) -> dict[str, Any] | None:
    query = str(name or "").strip()
    identifier = str(node_id or "").strip()
    scope = scope if isinstance(scope, dict) else {}
    ontology_prefix = str(scope.get("prefix") or scope.get("ontology_prefix") or "").strip()
    ontology_id = str(scope.get("ontology_id") or "").strip()
    if not query and not identifier:
        raise HTTPException(status_code=422, detail="A graph term is required")
    if not identifier:
        graph=publisher.search(query=query,limit=2,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
        rows=[{'id':n['elementId'],'name':n['properties'].get('label') or n['elementId'],
               'labels':n.get('labels',[]),'rdf_types':n['properties'].get('rdf_types',[]),
               'source_tag':n['properties'].get('ontology_id') or 'graph'} for n in graph['nodes']]
        exact=[row for row in rows if str(row['name']).casefold()==query.casefold()]
        if (graph.get('view') or {}).get('truncated'):
            raise HTTPException(409,'Graph search is bounded; select its node_id and ontology scope')
        if len(exact)==1:
            return exact[0]
        if len(rows)>1:
            raise HTTPException(409,'Graph term is ambiguous; select its node_id and ontology scope')
        return rows[0] if rows else None
    node_clause = _ontology_node_clause()
    rows = publisher._session_rows(
        f"MATCH (n) WHERE {node_clause} "
        "WITH n, coalesce(n.name, n.label, n.uri, n.iri) AS display "
        "WHERE elementId(n) = $node_id "
        "AND ($node_id <> '' OR $search_text = '' OR toLower(display) CONTAINS toLower($search_text)) "
        "AND ($ontology_prefix = '' OR n.prefix = $ontology_prefix OR n.ontology_prefix = $ontology_prefix) "
        "AND ($ontology_id = '' OR n.ontology_id = $ontology_id OR n.source_ontology = $ontology_id) "
        "RETURN elementId(n) AS id, display AS name, labels(n) AS labels, coalesce(n.rdf_types,[]) AS rdf_types, "
        "coalesce(n.source_ontology, n.ontology_id, n.prefix, 'graph') AS source_tag "
        "ORDER BY CASE WHEN toLower(display) = toLower($search_text) THEN 0 ELSE 1 END, display LIMIT 2",
        search_text=query, node_id=identifier, ontology_prefix=ontology_prefix, ontology_id=ontology_id,
    )
    if len(rows) > 1:
        exact = [row for row in rows if str(row.get('name') or '').casefold() == query.casefold()]
        if len(exact) == 1:
            return exact[0]
        raise HTTPException(409, 'Graph term is ambiguous; select its node_id and ontology scope')
    return rows[0] if rows else None


@router.get("/api/v1/graph/contextual-subgraph", summary="Search a bounded contextual engineering subgraph")
async def contextual_subgraph(
    search: str = Query(default="", max_length=500),
    ontology_prefix: str = Query(default="", max_length=256),
    import_id: str = Query(default="", max_length=256),
    limit: int = Query(default=400, ge=1, le=1000),
    search_mode: str = Query(default="best", pattern="^(best|broader)$"),
    expand_neighbors: bool = Query(default=False),
) -> dict[str, Any]:
    from backend.Services.graph_view_service import GraphViewService

    try:
        result = await run_in_threadpool(
            GraphViewService.get_contextual_subgraph,
            search=search,
            ontology_prefix=ontology_prefix,
            import_id=import_id,
            limit=limit,
            search_mode=search_mode,
            expand_neighbors=expand_neighbors,
        )
        return {**result, 'representation':'neo4j_contextual_graph'}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Contextual graph is unavailable") from exc


def _neighbors(node_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    return publisher._session_rows(
        "MATCH (root)-[r]-(neighbor) WHERE elementId(root) = $node_id "
        "AND NOT root:StagedOntologyResource AND NOT neighbor:StagedOntologyResource "
        "AND NOT root:RetainedOntologyIdentity AND NOT neighbor:RetainedOntologyIdentity "
        "AND NOT neighbor:OntologyPublication AND NOT neighbor:GraphChunk AND NOT neighbor:DatasheetChunk "
        "RETURN elementId(neighbor) AS id, coalesce(neighbor.name, neighbor.label, neighbor.uri, neighbor.iri) AS name, "
        "labels(neighbor) AS labels, coalesce(neighbor.rdf_types,[]) AS rdf_types, type(r) AS relation_type, r.predicate AS predicate, elementId(r) AS relationship_id, "
        "coalesce(neighbor.source_ontology, neighbor.ontology_id, neighbor.prefix, 'graph') AS source_tag "
        "ORDER BY name LIMIT $limit",
        node_id=node_id,
        limit=max(1, min(int(limit), 500)),
    )


def _kind(row: dict[str, Any]) -> str:
    return " ".join(str(value).lower() for value in [*row.get("labels", []), *row.get('rdf_types',[]), row.get("name", "")])


@router.get('/api/v1/graph/business-context', summary='Retrieve connected business instances with inclusion evidence')
async def business_context(node_id: str = Query(max_length=256), ontology_id: str = Query(default='',max_length=128),
                           ontology_prefix: str = Query(default='',max_length=128), depth: int = Query(default=1,ge=1,le=2),
                           limit: int = Query(default=60,ge=20,le=100)):
    from .business_context import retrieve
    try:
        return await run_in_threadpool(retrieve,publisher,node_id=node_id,ontology_id=ontology_id,ontology_prefix=ontology_prefix,depth=depth,limit=limit)
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503,'Business context is unavailable; check the graph service') from exc


@router.get('/api/v1/graph/document-evidence', summary='Read bounded indexed graph and document excerpts')
async def document_evidence(query: str = Query(min_length=1,max_length=500), ontology_id: str = Query(default='',max_length=128),
                            ontology_prefix: str = Query(default='',max_length=128),node_id: str = Query(default='',max_length=256),
                            limit: int = Query(default=6,ge=1,le=10)):
    from .document_evidence import retrieve
    try:
        return await run_in_threadpool(retrieve,publisher,query=query,ontology_id=ontology_id,ontology_prefix=ontology_prefix,node_id=node_id,limit=limit)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get("/api/v1/requirements", summary="List normalized requirement resources from the context graph")
def list_requirements(source: str = Query(default="all"), limit: int = Query(default=1000, ge=1, le=5000), offset: int = Query(default=0, ge=0)) -> dict:
    selected_source = source.strip().lower()
    source_expression = "coalesce(n.source, n.source_format, n.source_ontology, CASE WHEN n.iri CONTAINS '/entity/reqif%3A' THEN 'ReqIF' ELSE 'Graph' END)"
    # Format is a classification; source can instead be a provenance namespace.
    # Preserve source in the response and classify before pagination in Neo4j.
    source_kind_expression = (
        "CASE "
        "WHEN any(value IN source_values WHERE value = 'plmxml' OR value STARTS WITH 'http://www.plmxml.org/schemas/' "
        "OR value STARTS WITH 'https://www.plmxml.org/schemas/') THEN 'plmxml' "
        "WHEN any(value IN source_values WHERE value IN ['reqif', 'reqifz']) "
        "OR coalesce(n.iri, '') CONTAINS '/entity/reqif%3A' THEN 'reqif' "
        "WHEN any(value IN source_values WHERE value IN ['sysml-v1', 'sysml-v2', 'mbse']) THEN 'mbse' "
        "WHEN any(value IN source_values WHERE value IN ['qif', 'oslc', 'alm', 'unstructured', 'graph']) "
        "THEN head([value IN source_values WHERE value IN ['qif', 'oslc', 'alm', 'unstructured', 'graph']]) "
        f"ELSE toLower({source_expression}) END"
    )
    rows = publisher._session_rows(
        "MATCH (n) WHERE (n:Requirement OR any(label IN labels(n) WHERE toLower(label) CONTAINS 'requirement') "
        "OR EXISTS { MATCH (n)-[type_edge]->(t) WHERE type_edge.predicate = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' "
        "AND t.iri = 'https://depo.example.org/ceim/0.1/Requirement' }) "
        "AND NOT n:StagedOntologyResource "
        "WITH n, [value IN [n.source_format, n.source, n.source_ontology] "
        "WHERE value IS NOT NULL | toLower(trim(toString(value)))] AS source_values "
        f"WITH n, source_values, {source_kind_expression} AS source_kind "
        "WHERE ($source = 'all' OR source_kind = $source OR $source IN source_values) "
        "WITH n, source_kind ORDER BY coalesce(n.name, n.title, n.label, n.uri), elementId(n) SKIP $offset LIMIT $limit "
        "OPTIONAL MATCH (n)-[r]-() "
        "RETURN elementId(n) AS requirement_id, coalesce(n.name, n.title, n.label, n.uri) AS title, "
        "coalesce(n.text, n.description, n.comment, '') AS text, labels(n) AS labels, "
        f"{source_expression} AS source, source_kind, count(DISTINCT r) AS relationship_count "
        "ORDER BY title, requirement_id",
        limit=limit + 1,
        offset=offset,
        source=selected_source,
    )
    return {"requirements": rows[:limit], "count": len(rows[:limit]), "source": source,
            "offset": offset, "limit": limit, "has_more": len(rows) > limit}


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


def _change_impact_result(payload: ContextBody) -> dict:
    root = _find_node(str(payload.get("change_name") or ""), node_id=str(payload.get("node_id") or ""), scope=payload.get("scope"))
    if root is None:
        return {"message": "No matching graph term was found.", "impacted_parts": [], "assembly_impact": [], "impacted_requirements": [], "process_impacts": [], "realization_chain": []}
    neighbors = _neighbors(str(root["id"]))
    parts, assemblies, requirements, processes, realization = [], [], [], [], []
    for row in neighbors:
        # A reference to a revision, export record or metadata carrier is not
        # evidence of business impact. Require an explicit impact/trace edge.
        raw_relation = str(row.get('relation_type') or '')
        if raw_relation == 'SEMANTIC_RELATION' and row.get('predicate'):
            raw_relation = str(row['predicate']).rsplit('#',1)[-1].rsplit('/',1)[-1]
        relation = re.sub(r'[^A-Z0-9]', '', raw_relation.upper())
        if relation not in {'IMPACTS', 'AFFECTS', 'CMHASIMPACTEDITEM', 'CMHASPROBLEMITEM',
                            'CMHASSOLUTIONITEM', 'HASIMPACTEDITEM', 'HASPROBLEMITEM',
                            'HASSOLUTIONITEM', 'SATISFIES', 'SEG0SATISFY', 'FNDTRACELINK',
                            'TRACELINK', 'REALIZES', 'TRACESTO'}:
            continue
        kind = _kind(row)
        base = {"name": _display_name(row), "source_tag": row.get("source_tag"), "relation_type": raw_relation, "predicate":row.get("predicate"), "relationship_id":row.get("relationship_id"), "class_name": ", ".join(row.get("labels") or [])}
        if "requirement" in kind:
            requirements.append({"name": base["name"], "catalogue_id": row.get("id"), "linked_part": root["name"]})
        elif "assembly" in kind:
            assemblies.append({"assembly_name": base["name"], "depth": 1, "from_part": root["name"]})
        elif "process" in kind or "manufactur" in kind:
            processes.append({"name": base["name"], "source_tag": base["source_tag"], "from_part": root["name"]})
        elif any(label.rsplit('/',1)[-1].lower() in {'part', 'product', 'productrevision', 'individual', 'namedindividual'} for label in [*row.get('labels', []),*row.get('rdf_types',[])]):
            parts.append(base)
        else:
            continue
        realization.append({"name": base["name"], "link_type": base["relation_type"], "from_part": root["name"]})
    impact_count = len(realization)
    return {
        "change_entity": {"name": root["name"], "source_tag": root.get("source_tag", "graph"), "revision": None},
        "impact_score": min(100, impact_count * 10) if impact_count else None,
        "evidence_status": "linked_candidates" if impact_count else "insufficient",
        "message": ("Linked records are review candidates; the indicator measures graph evidence, not impact severity or confidence."
                    if impact_count else "The selected record was found, but no explicit impact or traceability links were found in its bounded neighborhood. Impact is unknown; review and link the affected business records before making a change decision."),
        "context_relationships_examined": len(neighbors),
        "impacted_parts": parts,
        "assembly_impact": assemblies,
        "impacted_requirements": requirements,
        "process_impacts": processes,
        "realization_chain": realization,
        "traceability": "Live Neo4j neighborhood; results are read-only and bounded.",
    }


def _similar_parts_result(payload: ContextBody) -> dict:
    root = _find_node(str(payload.get("part_name") or ""), node_id=str(payload.get("node_id") or ""), scope=payload.get("scope"))
    if root is None:
        return {"message": "No matching graph term was found.", "similar_parts": []}
    top_n = max(1, min(int(payload.get("top_n", 10)), 50))
    selected_scope=payload.get('scope') or {}
    graph=publisher.search(query=str(root['name']),limit=50,
        ontology_id=selected_scope.get('ontology_id',''),
        ontology_prefix=selected_scope.get('ontology_prefix',selected_scope.get('prefix','')),business_only=True)
    rows=[{'id':n['elementId'],'name':n['properties'].get('label') or n['elementId'],
           'labels':n.get('labels',[]),'rdf_types':n['properties'].get('rdf_types',[]),
           'source_tag':n['properties'].get('ontology_id') or 'graph'} for n in graph['nodes'] if n['elementId']!=root['id']]
    generic={'OntologyResource','OntologyClass','Individual','NamedIndividual','resource'}
    source_labels = set(root.get('rdf_types') or root.get("labels") or []) - generic
    candidates = []
    for row in rows:
        type_match = bool(source_labels.intersection(set(row.get('rdf_types') or row.get("labels") or [])-generic))
        source_tokens = set(re.findall(r"[a-z0-9]+", str(root["name"]).casefold()))
        target_tokens = set(re.findall(r"[a-z0-9]+", _display_name(row).casefold()))
        lexical = len(source_tokens & target_tokens) / max(1, len(source_tokens | target_tokens))
        candidates.append({
            "name": _display_name(row),
            "similarity_score": round(100 * (.75 * lexical + .25 * int(type_match)), 2),
            "score_evidence": {"token_jaccard": lexical, "graph_type_match": type_match,
                               "weights": {"token_jaccard": .75, "graph_type_match": .25}},
            "source_tag_match": row.get("source_tag") == root.get("source_tag"),
            "rflp_layer_match": False,
            "shared_assembly": False,
            "traceability_link": "lexical + graph-type match",
        })
    return {"source_part": {"name": root["name"], "source_tag": root.get("source_tag", "graph"), "rflp_layer": None}, "similar_parts": sorted(candidates, key=lambda c: (-c["similarity_score"], c["name"]))[:top_n], "ranking_scope": "At most 50 lexical graph candidates; score is a heuristic, not probability."}


def _manufacturing_context_result(payload: ContextBody) -> dict:
    root = _find_node(str(payload.get("part_name") or ""), node_id=str(payload.get("node_id") or ""), scope=payload.get("scope"))
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


@router.post("/recommendations/change-impact", summary="Trace graph-backed semantic change impact")
@router.post("/api/v1/recommendations/change-impact", summary="Trace graph-backed semantic change impact")
def change_impact(payload: ContextBody) -> dict:
    return assess_recommendation(_change_impact_result(payload), "change-impact", payload.get("scope"))


@router.post("/recommendations/similar-parts", summary="Find graph terms with lexical and type similarity")
@router.post("/api/v1/recommendations/similar-parts", summary="Find graph terms with lexical and type similarity")
def similar_parts(payload: ContextBody) -> dict:
    return assess_recommendation(_similar_parts_result(payload), "similar-parts", payload.get("scope"))


@router.post("/recommendations/manufacturing", summary="Find process context linked to a graph term")
@router.post("/api/v1/recommendations/manufacturing", summary="Find process context linked to a graph term")
def manufacturing_context(payload: ContextBody) -> dict:
    return assess_recommendation(_manufacturing_context_result(payload), "manufacturing", payload.get("scope"))


@router.get('/api/v1/graph/business-answer', summary='Read typed PLM product and part-PMI evidence')
async def business_answer(query: str = Query(min_length=1,max_length=500), ontology_id: str = Query(default='',max_length=128), ontology_prefix: str = Query(default='',max_length=128)):
    from .plm_answers import retrieve
    try:
        return await run_in_threadpool(retrieve,publisher,query=query,ontology_id=ontology_id,ontology_prefix=ontology_prefix)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
