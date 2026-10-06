"""HTTP transport for the graph service's deliberately read-only GraphQL API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from graphql import GraphQLError, parse

from backend.depo_platform.authorization import graph_read_identity
from .graphql_schema import execute

router = APIRouter(prefix="/api/v1/graphql", tags=["graphql"])
MAX_FIELDS = 25
MAX_DEPTH = 4
MAX_COST = 100
FIELD_COSTS = {"health": 1, "overview": 15, "search": 20, "ontology": 20, "traversal": 30,
               "searchResult": 20, "contextualSubgraph": 35, "contextualResult": 35, "dataJobRuns": 20, "dataJobRun": 10,
               "dataProducts": 25, "dataProduct": 10, "dataProductManifest": 15}
MAX_VARIABLE_BYTES = 128_000
MAX_VARIABLE_ITEMS = 500


def _validate_complexity(document: str, variables: dict[str, Any] | None = None) -> None:
    """Reject alias fan-out before any resolver can reach Neo4j."""
    try:
        parsed = parse(document)
    except GraphQLError as exc:
        raise HTTPException(400, {"errors": [{"message": exc.message}]}) from exc
    fields = 0
    cost = 0
    fragments = {
        definition.name.value: definition
        for definition in parsed.definitions
        if definition.__class__.__name__ == "FragmentDefinitionNode"
    }
    variable_defaults = {}
    for definition in parsed.definitions:
        for declaration in getattr(definition, 'variable_definitions', ()) or ():
            value = declaration.default_value
            if value is not None:
                variable_defaults[declaration.variable.name.value] = getattr(value, 'value', None)

    def argument(selection, name, default):
        value = next((item.value for item in selection.arguments if item.name.value == name), None)
        if value is None:
            return default
        if value.__class__.__name__ == 'VariableNode':
            return (variables or {}).get(value.name.value, variable_defaults.get(value.name.value, default))
        raw = getattr(value, 'value', default)
        return raw

    def visit(selection_set, depth: int, fragment_stack: set[str] | None = None) -> None:
        nonlocal fields, cost
        fragment_stack = set(fragment_stack or ())
        if depth > MAX_DEPTH:
            raise HTTPException(422, f"GraphQL query depth must not exceed {MAX_DEPTH}")
        for selection in selection_set.selections:
            if selection.__class__.__name__ == "FieldNode":
                fields += 1
                cost += FIELD_COSTS.get(getattr(getattr(selection, "name", None), "value", ""), 1)
                # Bound expensive result sizes and neighborhood work in addition
                # to aliases. The resolver still validates argument types.
                if selection.name.value in FIELD_COSTS:
                    requested_limit = argument(selection, 'limit', 200)
                    if isinstance(requested_limit, (int, str)) and not isinstance(requested_limit, bool):
                        try:
                            cost += max(0, min(int(requested_limit), 1000) - 500) // 20
                        except ValueError:
                            pass
                    if selection.name.value in {'contextualSubgraph', 'contextualResult'} and argument(selection, 'expandNeighbors', False) in (True, 'true'):
                        cost += 25
                    if selection.name.value == 'traversal':
                        try:
                            cost += max(0, min(int(argument(selection, 'depth', 1)), 5) - 1) * 10
                        except (ValueError, TypeError):
                            pass
                if fields > MAX_FIELDS:
                    raise HTTPException(422, f"GraphQL query must not select more than {MAX_FIELDS} fields")
                if cost > MAX_COST:
                    raise HTTPException(422, f"GraphQL query cost must not exceed {MAX_COST}")
            if selection.__class__.__name__ == "FragmentSpreadNode":
                name = selection.name.value
                if name in fragment_stack:
                    raise HTTPException(422, "GraphQL fragment cycle is not allowed")
                fragment = fragments.get(name)
                if fragment is not None:
                    visit(fragment.selection_set, depth, fragment_stack | {name})
            elif getattr(selection, "selection_set", None):
                visit(selection.selection_set, depth + (selection.__class__.__name__ == 'FieldNode'), fragment_stack)
    for definition in parsed.definitions:
        if definition.__class__.__name__ == "OperationDefinitionNode" and getattr(definition, "selection_set", None):
            visit(definition.selection_set, 1)


def _validate_variables(variables: Any) -> dict[str, Any] | None:
    if variables is None:
        return None
    if not isinstance(variables, dict):
        raise HTTPException(422, "variables must be an object")

    def inspect(value: Any, depth: int = 0) -> int:
        if depth > 6:
            raise HTTPException(422, "variables nesting must not exceed 6 levels")
        if isinstance(value, dict):
            if len(value) > MAX_VARIABLE_ITEMS:
                raise HTTPException(422, "variables object has too many fields")
            return sum(len(str(key)) + inspect(child, depth + 1) for key, child in value.items())
        if isinstance(value, list):
            if len(value) > MAX_VARIABLE_ITEMS:
                raise HTTPException(422, "variables list has too many items")
            return sum(inspect(child, depth + 1) for child in value)
        if isinstance(value, str) and len(value) > 10_000:
            raise HTTPException(422, "variable string must not exceed 10000 characters")
        return len(str(value))

    if inspect(variables) > MAX_VARIABLE_BYTES:
        raise HTTPException(422, "variables must not exceed 128 KB")
    return variables


@router.post("", summary="Execute a bounded read-only graph query")
def query(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    graph_read_identity(request)
    document = str(payload.get("query") or "")
    if not document.strip() or len(document) > 10_000:
        raise HTTPException(422, "query is required and must be at most 10000 characters")
    variables = _validate_variables(payload.get("variables"))
    _validate_complexity(document, variables)
    operation_name = payload.get("operationName")
    if operation_name is not None and (not isinstance(operation_name, str) or len(operation_name) > 256):
        raise HTTPException(422, "operationName must be a string of at most 256 characters")
    result = execute(document, variables=variables, operation_name=operation_name)
    if result.get("errors"):
        unavailable = any(error.get("extensions", {}).get("code") == "SERVICE_UNAVAILABLE" for error in result["errors"])
        raise HTTPException(503 if unavailable else 400, result)
    return result
