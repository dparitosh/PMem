"""Ontology toolset for the standalone package."""

from ontology_agentic.tools.cad_step_tools import export_step_to_ttl, inspect_step_file
from ontology_agentic.tools.depo_api_tools import (
    depo_execute_semantic_workflow,
    depo_export_import_owl,
    depo_graph_search,
    depo_graph_search_many,
    depo_healthcheck,
    depo_list_registered_ontologies,
    depo_merge_ontologies,
    depo_oslc_catalog,
    depo_oslc_dictionary,
    depo_oslc_provider,
    depo_oslc_query_resources,
    depo_oslc_resource,
    depo_oslc_shapes,
    depo_oslc_taxonomies,
    depo_oslc_trs,
)
from ontology_agentic.tools.reqif_tools import export_reqif_to_ttl, inspect_reqif_file
from ontology_agentic.tools.requirement_normalization_tools import (
    export_requirements_alignment_ttl,
    normalize_requirement_records,
    requirement_alignment_profile,
)
from ontology_agentic.tools.ontology_tools import (
    export_ontology,
    inspect_ontology_artifact,
    plan_instance_alignment,
    review_ontology_structure,
)
from ontology_agentic.tools.openapi_tools import inspect_openapi_document

__all__ = [
    "depo_execute_semantic_workflow",
    "depo_export_import_owl",
    "depo_graph_search",
    "depo_graph_search_many",
    "depo_healthcheck",
    "depo_list_registered_ontologies",
    "depo_merge_ontologies",
    "depo_oslc_catalog",
    "depo_oslc_dictionary",
    "depo_oslc_provider",
    "depo_oslc_query_resources",
    "depo_oslc_resource",
    "depo_oslc_shapes",
    "depo_oslc_taxonomies",
    "depo_oslc_trs",
    "export_ontology",
    "export_reqif_to_ttl",
    "export_step_to_ttl",
    "inspect_ontology_artifact",
    "inspect_reqif_file",
    "inspect_step_file",
    "normalize_requirement_records",
    "requirement_alignment_profile",
    "export_requirements_alignment_ttl",
    "plan_instance_alignment",
    "review_ontology_structure",
    "inspect_openapi_document",
]
