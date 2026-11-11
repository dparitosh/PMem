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
    "self_learning_review": ["pipeline.run.evidence", "learning.lessons"],
    "orchestrator": ["pipeline.definitions", "pipeline.runs", "pipeline.run.evidence", "data.catalog.products"],
}

TOOLS = [
    ("pipeline.reconciliation.evidence","data_pipeline","GET","/pipeline/speed/reconciliations/{reconciliation_id}"),
    ("learning.lessons", "agentic", "GET", "/learning/lessons"),
    ("pipeline.definitions", "data_pipeline", "GET", "/pipeline/jobs/definitions"),
    ("pipeline.runs", "data_pipeline", "GET", "/pipeline/jobs/runs"),
    ("pipeline.run.evidence", "data_pipeline", "GET", "/pipeline/jobs/runs/{run_id}"),
    ("pipeline.run", "data_pipeline", "POST", "/pipeline/jobs/definitions/{job_id}/{version}/run"),
    ("data.catalog.product", "catalog", "GET", "/catalog/products/{product_id}"),
]


def extend_catalog(source):
    catalog = deepcopy(source)
    for agent in catalog['agents']:
        if agent['id'] in {'ontology-governor','ontology-steward'} and 'learning.lessons' not in agent['tools']:
            agent['tools'].append('learning.lessons')
    for agent in catalog['agents']:
        if agent['id'] in {'graph-analyst','ontology-steward'}:
            if 'pipeline.reconciliation.evidence' not in agent['tools']:agent['tools'].append('pipeline.reconciliation.evidence')
            if agent['id']=='graph-analyst' and 'pipeline.run.evidence' not in agent['tools']:agent['tools'].append('pipeline.run.evidence')
            if 'pipeline.reconciliation.evidence' not in agent['system_prompt']:agent['system_prompt'] += ' For a selected reconciliation_id, inspect pipeline.reconciliation.evidence. Explain its retained semantic checks and recovery state; do not equate reconciliation with business correctness or publication approval. Memory is advisory; current owning-service evidence wins.'
            if agent['id']=='graph-analyst' and 'For a selected run_id inspect pipeline.run.evidence' not in agent['system_prompt']:
                agent['system_prompt']+=' For a selected run_id inspect pipeline.run.evidence before explaining ingestion or mapping readiness. Do not invent source columns or semantic mappings from run metadata.'
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
    from .prompt_policy import attach_policies
    return attach_policies(catalog)


def capabilities():
    return {"roles": ROLE_TOOLS, "execution": "/api/v1/runs",
            "agent_id_format": "dt-<role with underscores replaced by hyphens>",
            "analytics": {"job_type": "schema-analytics-product", "quality_profile": "schema-analytics-v1",
                          "requires": "approved enabled job definition and immutable input"},
            "unsupported": ["automatic lesson promotion", "automatic publication approval"],
            "governed_learning": {"status":"/api/v1/learning/status", "scope":"receipted mapping review hints", "model_training":False},
            "external_client_binding_required": True}
