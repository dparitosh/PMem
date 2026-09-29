"""Read-only GraphQL schema over bounded graph-service projections."""
from __future__ import annotations

from typing import Any

from graphql import GraphQLArgument, GraphQLBoolean, GraphQLError, GraphQLField, GraphQLInt, GraphQLList, GraphQLNonNull, GraphQLObjectType, GraphQLScalarType, GraphQLSchema, GraphQLString, graphql_sync

from .control_plane_client import ControlPlaneUnavailable, control_plane_client
from .neo4j_publisher import publisher


def _serialize_json(value: Any) -> Any:
    return value


JSON = GraphQLScalarType(name="JSON", serialize=_serialize_json)


GraphNode = GraphQLObjectType(
    name="GraphNode",
    fields=lambda: {
        "elementId": GraphQLField(GraphQLNonNull(GraphQLString), resolve=lambda node, _info: str(node.get("elementId") or node.get("id") or "")),
        "label": GraphQLField(GraphQLString, resolve=lambda node, _info: str(node.get("label") or node.get("name") or (node.get("properties") or {}).get("name") or "")),
        "type": GraphQLField(GraphQLString, resolve=lambda node, _info: str(node.get("type") or (node.get("labels") or [""])[0] or "")),
        "labels": GraphQLField(GraphQLList(GraphQLNonNull(GraphQLString)), resolve=lambda node, _info: [str(value) for value in (node.get("labels") or [])]),
        "properties": GraphQLField(JSON, resolve=lambda node, _info: node.get("properties") or {}),
        "canTraverse": GraphQLField(GraphQLBoolean, resolve=lambda node, _info: bool(node.get("can_traverse", node.get("canTraverse", False)))),
    },
)

GraphRelationship = GraphQLObjectType(
    name="GraphRelationship",
    fields=lambda: {
        "elementId": GraphQLField(GraphQLString, resolve=lambda rel, _info: str(rel.get("elementId") or rel.get("id") or "")),
        "source": GraphQLField(GraphQLNonNull(GraphQLString), resolve=lambda rel, _info: str(rel.get("start") or rel.get("source") or "")),
        "target": GraphQLField(GraphQLNonNull(GraphQLString), resolve=lambda rel, _info: str(rel.get("end") or rel.get("target") or "")),
        "type": GraphQLField(GraphQLString, resolve=lambda rel, _info: str(rel.get("type") or "RELATED_TO")),
        "properties": GraphQLField(JSON, resolve=lambda rel, _info: rel.get("properties") or {}),
    },
)

GraphResult = GraphQLObjectType(
    name="GraphResult",
    fields=lambda: {
        "nodes": GraphQLField(GraphQLNonNull(GraphQLList(GraphQLNonNull(GraphNode))), resolve=lambda graph, _info: graph.get("nodes") or []),
        "relationships": GraphQLField(GraphQLNonNull(GraphQLList(GraphQLNonNull(GraphRelationship))), resolve=lambda graph, _info: graph.get("relationships") or graph.get("edges") or []),
        "counts": GraphQLField(JSON, resolve=lambda graph, _info: graph.get("counts") or {}),
        "view": GraphQLField(JSON, resolve=lambda graph, _info: graph.get("view") or {}),
        "root": GraphQLField(GraphNode, resolve=lambda graph, _info: graph.get("root")),
    },
)


def _bounded(value: int | None, default: int, maximum: int = 1000) -> int:
    return max(1, min(int(value if value is not None else default), maximum))


def _control_plane_read(call):
    try:
        return call()
    except ControlPlaneUnavailable as exc:
        raise GraphQLError("Control-plane dependency is unavailable", extensions={"code": "SERVICE_UNAVAILABLE"}) from exc


def _bounded_text(value: str, name: str, maximum: int = 500) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise GraphQLError(f"{name} is required and must be at most {maximum} characters")
    return text


def _contextual_graph(*, search: str, ontology_prefix: str = "", import_id: str = "", limit: int | None = None,
                      search_mode: str = "best", expand_neighbors: bool = False) -> dict[str, Any]:
    from backend.Services.graph_view_service import GraphViewService

    mode = str(search_mode or "best").strip().lower()
    if mode not in {"best", "broader"}:
        raise GraphQLError("searchMode must be 'best' or 'broader'")
    return GraphViewService.get_contextual_subgraph(
        search=_bounded_text(search, "search"),
        ontology_prefix=str(ontology_prefix or "")[:256],
        import_id=str(import_id or "")[:256],
        limit=_bounded(limit, 200),
        search_mode=mode,
        expand_neighbors=bool(expand_neighbors),
    )


Query = GraphQLObjectType(
    name="Query",
    fields=lambda: {
        "health": GraphQLField(JSON, resolve=lambda *_: publisher.health()),
        "overview": GraphQLField(JSON, args={"limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, limit=None: publisher.overview(limit=_bounded(limit, 200))),
        "search": GraphQLField(JSON, args={"query": GraphQLArgument(GraphQLNonNull(GraphQLString)), "limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, query, limit=None: publisher.search(query=_bounded_text(query, "query"), limit=_bounded(limit, 50, 200))),
        "searchResult": GraphQLField(GraphResult, args={"query": GraphQLArgument(GraphQLNonNull(GraphQLString)), "limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, query, limit=None: publisher.search(query=_bounded_text(query, "query"), limit=_bounded(limit, 50, 200))),
        "contextualSubgraph": GraphQLField(JSON, args={"search": GraphQLArgument(GraphQLNonNull(GraphQLString)), "ontologyPrefix": GraphQLArgument(GraphQLString), "importId": GraphQLArgument(GraphQLString), "limit": GraphQLArgument(GraphQLInt), "searchMode": GraphQLArgument(GraphQLString), "expandNeighbors": GraphQLArgument(GraphQLBoolean)}, resolve=lambda _root, _info, **args: _contextual_graph(search=args["search"], ontology_prefix=args.get("ontologyPrefix") or "", import_id=args.get("importId") or "", limit=args.get("limit"), search_mode=args.get("searchMode") or "best", expand_neighbors=bool(args.get("expandNeighbors")))),
        "contextualResult": GraphQLField(GraphResult, args={"search": GraphQLArgument(GraphQLNonNull(GraphQLString)), "ontologyPrefix": GraphQLArgument(GraphQLString), "importId": GraphQLArgument(GraphQLString), "limit": GraphQLArgument(GraphQLInt), "searchMode": GraphQLArgument(GraphQLString), "expandNeighbors": GraphQLArgument(GraphQLBoolean)}, resolve=lambda _root, _info, **args: _contextual_graph(search=args["search"], ontology_prefix=args.get("ontologyPrefix") or "", import_id=args.get("importId") or "", limit=args.get("limit"), search_mode=args.get("searchMode") or "best", expand_neighbors=bool(args.get("expandNeighbors")))),
        "ontology": GraphQLField(JSON, args={"ontologyId": GraphQLArgument(GraphQLNonNull(GraphQLString)), "limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, ontologyId, limit=None: publisher.explorer_projection(ontology_id=_bounded_text(ontologyId, "ontologyId", 256), limit=_bounded(limit, 200))),
        "traversal": GraphQLField(JSON, args={"iri": GraphQLArgument(GraphQLNonNull(GraphQLString)), "depth": GraphQLArgument(GraphQLInt), "limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, iri, depth=None, limit=None: publisher.traversal(iri=_bounded_text(iri, "iri", 2000), depth=_bounded(depth, 1, 5), limit=_bounded(limit, 200))),
        "dataJobRuns": GraphQLField(JSON, args={"limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, limit=None: _control_plane_read(lambda: control_plane_client.job_runs(_bounded(limit, 100)))),
        "dataJobRun": GraphQLField(JSON, args={"runId": GraphQLArgument(GraphQLNonNull(GraphQLString))}, resolve=lambda _root, _info, runId: _control_plane_read(lambda: control_plane_client.job_run(_bounded_text(runId, "runId", 256)))),
        "dataProducts": GraphQLField(JSON, args={"limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, limit=None: _control_plane_read(lambda: control_plane_client.data_products(_bounded(limit, 100, 500)))),
        "dataProduct": GraphQLField(JSON, args={"productVersion": GraphQLArgument(GraphQLNonNull(GraphQLString))}, resolve=lambda _root, _info, productVersion: _control_plane_read(lambda: control_plane_client.data_product(_bounded_text(productVersion, "productVersion", 256)))),
        "dataProductManifest": GraphQLField(JSON, args={"productVersion": GraphQLArgument(GraphQLNonNull(GraphQLString))}, resolve=lambda _root, _info, productVersion: _control_plane_read(lambda: control_plane_client.data_product_manifest(_bounded_text(productVersion, "productVersion", 256)))),
    },
)

schema = GraphQLSchema(query=Query)


def execute(query: str, variables: dict[str, Any] | None = None, operation_name: str | None = None) -> dict[str, Any]:
    result = graphql_sync(schema, query, variable_values=variables, operation_name=operation_name)
    payload: dict[str, Any] = {"data": result.data}
    if result.errors:
        payload["errors"] = [{"message": error.message, "extensions": error.extensions or {}} for error in result.errors]
    return payload
