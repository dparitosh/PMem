"""Explicit DT role bindings; no runtime imports or implicit tool privileges."""
from copy import deepcopy

ROLE_TOOLS = {
    "intake": ["engineering.inspect", "ontology.register", "pipeline.definitions"],
    "domain_identifier": ["ceim.contract", "context.search"],
    "structure_review": ["pipeline.definitions", "pipeline.run", "pipeline.run.evidence"],
    "semantic_bridge_planner": ["ceim.contract", "ceim.normalize.batch"],
    "entity_conflict_review": ["ontology.merge.preview", "pipeline.run.evidence"],
    "property_conflict_review": ["pipeline.definitions", "pipeline.run", "pipeline.run.evidence"],
    "context_graph_conflict_review": ["context.where_used", "graph.neighborhood", "pipeline.run.evidence"],
    "data_product_interaction": ["data.catalog.products", "data.catalog.product", "pipeline.definitions", "pipeline.run", "pipeline.run.evidence"],
    "kg_interaction": ["graph.analytics", "graph.neighborhood", "oslc.graph_rag"],
    "export": ["ontology.export"],
    "self_learning_review": ["pipeline.run.evidence"],
    "orchestrator": ["pipeline.definitions", "pipeline.runs", "pipeline.run.evidence", "data.catalog.products"],
}

TOOLS = [
    ("pipeline.definitions", "data_pipeline", "GET", "/pipeline/jobs/definitions"),
    ("pipeline.runs", "data_pipeline", "GET", "/pipeline/jobs/runs"),
    ("pipeline.run.evidence", "data_pipeline", "GET", "/pipeline/jobs/runs/{run_id}"),
    ("pipeline.run", "data_pipeline", "POST", "/pipeline/jobs/definitions/{job_id}/{version}/run"),
    ("data.catalog.product", "catalog", "GET", "/catalog/products/{product_id}"),
]


def extend_catalog(source):
    catalog = deepcopy(source)
    existing = {tool["id"] for tool in catalog["tools"]}
    for identifier, service, method, path in TOOLS:
        if identifier not in existing:
            catalog["tools"].append(dict(id=identifier, service=service, method=method,
                                         path=path, transport="openapi", mutates=method != "GET"))
    ids = {agent["id"] for agent in catalog["agents"]}
    for role, tools in ROLE_TOOLS.items():
        identifier = "dt-" + role.replace("_", "-")
        if identifier not in ids:
            catalog["agents"].append(dict(id=identifier, name="DT " + role,
                                         tools=tools, approval_required=False))
    return catalog


def capabilities():
    return {"roles": ROLE_TOOLS, "execution": "/api/v1/runs",
            "agent_id_format": "dt-<role with underscores replaced by hyphens>",
            "analytics": {"job_type": "schema-analytics-product", "quality_profile": "schema-analytics-v1",
                          "requires": "approved enabled job definition and immutable input"},
            "unsupported": ["automatic lesson promotion", "automatic publication approval"],
            "external_client_binding_required": True}
