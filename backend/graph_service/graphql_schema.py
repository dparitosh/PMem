"""Read-only GraphQL schema over bounded graph-service projections."""
from __future__ import annotations

from typing import Any

from graphql import GraphQLArgument, GraphQLError, GraphQLField, GraphQLInt, GraphQLNonNull, GraphQLObjectType, GraphQLScalarType, GraphQLSchema, GraphQLString, graphql_sync

from .control_plane_client import ControlPlaneUnavailable, control_plane_client
from .neo4j_publisher import publisher


def _serialize_json(value: Any) -> Any:
    return value


JSON = GraphQLScalarType(name="JSON", serialize=_serialize_json)


def _bounded(value: int | None, default: int, maximum: int = 1000) -> int:
    return max(1, min(int(value if value is not None else default), maximum))


def _control_plane_read(call):
    try:
        return call()
    except ControlPlaneUnavailable as exc:
        raise GraphQLError(str(exc)) from exc


Query = GraphQLObjectType(
    name="Query",
    fields=lambda: {
        "health": GraphQLField(JSON, resolve=lambda *_: publisher.health()),
        "overview": GraphQLField(JSON, args={"limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, limit=None: publisher.overview(limit=_bounded(limit, 200))),
        "ontology": GraphQLField(JSON, args={"ontologyId": GraphQLArgument(GraphQLNonNull(GraphQLString)), "limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, ontologyId, limit=None: publisher.explorer_projection(ontology_id=ontologyId, limit=_bounded(limit, 200))),
        "traversal": GraphQLField(JSON, args={"iri": GraphQLArgument(GraphQLNonNull(GraphQLString)), "depth": GraphQLArgument(GraphQLInt), "limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, iri, depth=None, limit=None: publisher.traversal(iri=iri, depth=_bounded(depth, 1, 5), limit=_bounded(limit, 200))),
        "dataJobRuns": GraphQLField(JSON, args={"limit": GraphQLArgument(GraphQLInt)}, resolve=lambda _root, _info, limit=None: _control_plane_read(lambda: control_plane_client.job_runs(_bounded(limit, 100)))),
        "dataJobRun": GraphQLField(JSON, args={"runId": GraphQLArgument(GraphQLNonNull(GraphQLString))}, resolve=lambda _root, _info, runId: _control_plane_read(lambda: control_plane_client.job_run(runId))),
        "dataProducts": GraphQLField(JSON, resolve=lambda *_: _control_plane_read(control_plane_client.data_products)),
        "dataProduct": GraphQLField(JSON, args={"productVersion": GraphQLArgument(GraphQLNonNull(GraphQLString))}, resolve=lambda _root, _info, productVersion: _control_plane_read(lambda: control_plane_client.data_product(productVersion))),
        "dataProductManifest": GraphQLField(JSON, args={"productVersion": GraphQLArgument(GraphQLNonNull(GraphQLString))}, resolve=lambda _root, _info, productVersion: _control_plane_read(lambda: control_plane_client.data_product_manifest(productVersion))),
    },
)

schema = GraphQLSchema(query=Query)


def execute(query: str, variables: dict[str, Any] | None = None, operation_name: str | None = None) -> dict[str, Any]:
    result = graphql_sync(schema, query, variable_values=variables, operation_name=operation_name)
    payload: dict[str, Any] = {"data": result.data}
    if result.errors:
        payload["errors"] = [{"message": error.message} for error in result.errors]
    return payload
