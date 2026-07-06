from __future__ import annotations

from typing import Any

from ontology_agentic.config import settings
from ontology_agentic.runtime.registry import AgentRegistry
from ontology_agentic.tools.depo_api_tools import (
    depo_execute_semantic_workflow,
    depo_export_import_owl,
    depo_graph_search,
    depo_graph_search_many,
    depo_healthcheck,
    depo_list_registered_ontologies,
    depo_oslc_catalog,
    depo_oslc_dictionary,
    depo_oslc_provider,
    depo_oslc_query_resources,
    depo_oslc_resource,
    depo_oslc_shapes,
    depo_oslc_taxonomies,
    depo_oslc_trs,
    depo_merge_ontologies,
)
from ontology_agentic.tools.cad_step_tools import export_step_to_ttl, inspect_step_file
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


class OntologyWorkflowEngine:
    def __init__(self) -> None:
        self.registry = AgentRegistry(settings.agent_specs_dir)
        self._register_default_agents()

    def _register_default_agents(self) -> None:
        specs = settings.agent_specs_dir
        self.registry.register("ontology_intake_handler", self._run_ontology_intake, specs / "ontology_intake_agent.yaml")
        self.registry.register("ontology_structure_handler", self._run_ontology_structure_review, specs / "ontology_structure_review_agent.yaml")
        self.registry.register("semantic_bridge_planner_handler", self._run_semantic_bridge_planner, specs / "semantic_bridge_planner_agent.yaml")
        self.registry.register("ontology_export_handler", self._run_ontology_export, specs / "ontology_export_agent.yaml")
        self.registry.register("ontology_orchestrator_handler", self._run_ontology_orchestrator, specs / "ontology_orchestrator_agent.yaml")

    def run_agent(self, agent_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        agent = self.registry.get(agent_name)
        result = agent.handler(inputs)
        return {
            "agent": agent.spec.name,
            "handler": agent.handler_name,
            "result": result,
        }

    def run_workflow(self, workflow_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        workflow_map = {
            "ontology_review": self._workflow_ontology_review,
            "ontology_alignment": self._workflow_ontology_alignment,
            "ontology_export": self._workflow_ontology_export,
            "step_inspect": self._workflow_step_inspect,
            "step_export": self._workflow_step_export,
            "reqif_inspect": self._workflow_reqif_inspect,
            "reqif_export": self._workflow_reqif_export,
            "requirements_normalize": self._workflow_requirements_normalize,
            "requirements_alignment_export": self._workflow_requirements_alignment_export,
            "requirements_alignment_profile": self._workflow_requirements_alignment_profile,
            "depo_healthcheck": self._workflow_depo_healthcheck,
            "depo_registered_ontologies": self._workflow_depo_registered_ontologies,
            "depo_graph_search": self._workflow_depo_graph_search,
            "depo_oslc": self._workflow_depo_oslc,
            "depo_semantic_workflow": self._workflow_depo_semantic_workflow,
            "depo_ontology_merge": self._workflow_depo_ontology_merge,
            "depo_import_export": self._workflow_depo_import_export,
        }
        try:
            handler = workflow_map[workflow_id]
        except KeyError as exc:
            raise KeyError(f"Unknown workflow: {workflow_id}") from exc
        return handler(inputs)

    def _workflow_ontology_review(self, inputs: dict[str, Any]) -> dict[str, Any]:
        intake = self._run_ontology_intake(inputs)
        review = self._run_ontology_structure_review(inputs)
        return {
            "workflow_id": "ontology_review",
            "steps": [
                {"agent": "ontology_intake_agent", "status": "completed", "output": intake},
                {"agent": "ontology_structure_review_agent", "status": "completed", "output": review},
            ],
            "status": "completed",
        }

    def _workflow_ontology_alignment(self, inputs: dict[str, Any]) -> dict[str, Any]:
        intake = self._run_ontology_intake(inputs)
        plan = self._run_semantic_bridge_planner(inputs)
        return {
            "workflow_id": "ontology_alignment",
            "steps": [
                {"agent": "ontology_intake_agent", "status": "completed", "output": intake},
                {"agent": "semantic_bridge_planner_agent", "status": "completed", "output": plan},
            ],
            "status": "completed",
        }

    def _workflow_ontology_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        intake = self._run_ontology_intake(inputs)
        exports = self._run_ontology_export(inputs)
        return {
            "workflow_id": "ontology_export",
            "steps": [
                {"agent": "ontology_intake_agent", "status": "completed", "output": intake},
                {"agent": "ontology_export_agent", "status": "completed", "output": exports},
            ],
            "status": "completed",
        }

    def _workflow_step_inspect(self, inputs: dict[str, Any]) -> dict[str, Any]:
        step_path = inputs.get("step_path") or inputs.get("file_path")
        if not step_path:
            raise ValueError("step_path is required")
        result = inspect_step_file(
            path_value=step_path,
            include_entity_sample=bool(inputs.get("include_entity_sample", True)),
            sample_size=int(inputs.get("sample_size", 20)),
        )
        return {
            "workflow_id": "step_inspect",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_intake_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_step_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        step_path = inputs.get("step_path") or inputs.get("file_path")
        if not step_path:
            raise ValueError("step_path is required")
        result = export_step_to_ttl(
            path_value=step_path,
            output_path=inputs.get("output_path"),
            base_uri=str(inputs.get("base_uri") or "http://depo-onto.local/step#"),
            namespace_prefix=str(inputs.get("namespace_prefix") or "step"),
            include_pmi=bool(inputs.get("include_pmi", True)),
        )
        return {
            "workflow_id": "step_export",
            "status": "completed" if result.get("success") else "failed",
            "steps": [
                {
                    "agent": "ontology_export_agent",
                    "status": "completed" if result.get("success") else "failed",
                    "output": result,
                }
            ],
        }

    def _workflow_reqif_inspect(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reqif_path = inputs.get("reqif_path") or inputs.get("file_path")
        if not reqif_path:
            raise ValueError("reqif_path is required")
        result = inspect_reqif_file(path_value=reqif_path, sample_size=int(inputs.get("sample_size", 20)))
        return {
            "workflow_id": "reqif_inspect",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_intake_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_reqif_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reqif_path = inputs.get("reqif_path") or inputs.get("file_path")
        if not reqif_path:
            raise ValueError("reqif_path is required")
        result = export_reqif_to_ttl(
            path_value=reqif_path,
            output_path=inputs.get("output_path"),
            base_uri=str(inputs.get("base_uri") or "http://depo-onto.local/reqif/"),
            sample_size=int(inputs.get("sample_size", 10000)),
        )
        return {
            "workflow_id": "reqif_export",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_export_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_requirements_normalize(self, inputs: dict[str, Any]) -> dict[str, Any]:
        records = inputs.get("records") or []
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        result = normalize_requirement_records(
            records=records,
            source_name=str(inputs.get("source_name") or ""),
            source_type=str(inputs.get("source_type") or "unstructured"),
        )
        return {
            "workflow_id": "requirements_normalize",
            "status": "completed",
            "steps": [
                {
                    "agent": "semantic_bridge_planner_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_requirements_alignment_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        payload = inputs.get("payload") or {}
        output_path = inputs.get("output_path")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if not output_path:
            raise ValueError("output_path is required")
        result = export_requirements_alignment_ttl(
            payload=payload,
            output_path=output_path,
            base_uri=str(inputs.get("base_uri") or "http://depo-onto.local/requirements/"),
        )
        return {
            "workflow_id": "requirements_alignment_export",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_export_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_requirements_alignment_profile(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "workflow_id": "requirements_alignment_profile",
            "status": "completed",
            "steps": [
                {
                    "agent": "semantic_bridge_planner_agent",
                    "status": "completed",
                    "output": requirement_alignment_profile(),
                }
            ],
        }

    def _workflow_depo_healthcheck(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "workflow_id": "depo_healthcheck",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_orchestrator_agent",
                    "status": "completed",
                    "output": depo_healthcheck(base_url=inputs.get("depo_api_base_url")),
                }
            ],
        }

    def _workflow_depo_registered_ontologies(self, inputs: dict[str, Any]) -> dict[str, Any]:
        payload = depo_list_registered_ontologies(base_url=inputs.get("depo_api_base_url"))
        return {
            "workflow_id": "depo_registered_ontologies",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_orchestrator_agent",
                    "status": "completed",
                    "output": payload,
                }
            ],
        }

    def _workflow_depo_graph_search(self, inputs: dict[str, Any]) -> dict[str, Any]:
        names = inputs.get("names")
        search = inputs.get("search")
        ontology_prefix = str(inputs.get("ontology_prefix") or "").strip()
        use_multi = bool(inputs.get("many") or names or isinstance(search, list))

        if use_multi:
            result = depo_graph_search_many(
                names=names if isinstance(names, list) else None,
                search=search,
                base_url=inputs.get("depo_api_base_url"),
            )
            mode = "multi"
        else:
            query = str(search or "").strip()
            if not query:
                raise ValueError("search or names are required")
            result = depo_graph_search(
                search=query,
                ontology_prefix=ontology_prefix,
                base_url=inputs.get("depo_api_base_url"),
            )
            mode = "single"

        return {
            "workflow_id": "depo_graph_search",
            "status": "completed",
            "mode": mode,
            "steps": [
                {
                    "agent": "ontology_orchestrator_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_depo_oslc(self, inputs: dict[str, Any]) -> dict[str, Any]:
        action = str(inputs.get("action") or "catalog").strip().lower().replace("-", "_")
        base_url = inputs.get("depo_api_base_url")

        if action == "catalog":
            result = depo_oslc_catalog(base_url=base_url)
        elif action == "provider":
            result = depo_oslc_provider(provider_id=str(inputs.get("provider_id") or "depo"), base_url=base_url)
        elif action == "shapes":
            result = depo_oslc_shapes(shape_id=str(inputs.get("shape_id") or ""), base_url=base_url)
        elif action == "query":
            query_params = inputs.get("query_params") or {}
            if not isinstance(query_params, dict):
                raise ValueError("query_params must be an object")
            result = depo_oslc_query_resources(
                resource_type=str(inputs.get("resource_type") or "resources"),
                query_params=query_params,
                base_url=base_url,
            )
        elif action == "resource":
            result = depo_oslc_resource(
                element_id=str(inputs.get("element_id") or ""),
                include_links=bool(inputs.get("include_links", True)),
                base_url=base_url,
            )
        elif action == "dictionary":
            result = depo_oslc_dictionary(
                prefix=str(inputs.get("prefix") or ""),
                instance_limit=inputs.get("instance_limit"),
                relationship_limit=inputs.get("relationship_limit"),
                fallback_limit=inputs.get("fallback_limit"),
                base_url=base_url,
            )
        elif action in {"taxonomy", "taxonomies"}:
            result = depo_oslc_taxonomies(ontology_id=str(inputs.get("ontology_id") or ""), base_url=base_url)
        elif action == "trs":
            result = depo_oslc_trs(
                section=str(inputs.get("section") or "descriptor"),
                after=inputs.get("after"),
                limit=inputs.get("limit"),
                base_url=base_url,
            )
        else:
            raise ValueError("Unsupported OSLC action. Use catalog, provider, shapes, query, resource, dictionary, taxonomies, or trs.")

        return {
            "workflow_id": "depo_oslc",
            "status": "completed",
            "action": action,
            "steps": [
                {
                    "agent": "ontology_orchestrator_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_depo_semantic_workflow(self, inputs: dict[str, Any]) -> dict[str, Any]:
        depo_workflow_id = str(inputs.get("depo_workflow_id") or inputs.get("workflow_id") or "").strip()
        if not depo_workflow_id or depo_workflow_id == "depo_semantic_workflow":
            raise ValueError("depo_workflow_id is required")
        payload = inputs.get("payload") or inputs.get("depo_payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        result = depo_execute_semantic_workflow(
            workflow_id=depo_workflow_id,
            payload=payload,
            base_url=inputs.get("depo_api_base_url"),
        )
        return {
            "workflow_id": "depo_semantic_workflow",
            "status": "completed",
            "remote_workflow_id": depo_workflow_id,
            "steps": [
                {
                    "agent": "ontology_orchestrator_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_depo_ontology_merge(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from_ontology_id = str(inputs.get("from_ontology_id") or "").strip()
        to_ontology_id = str(inputs.get("to_ontology_id") or "").strip()
        if not from_ontology_id or not to_ontology_id:
            raise ValueError("from_ontology_id and to_ontology_id are required")
        result = depo_merge_ontologies(
            from_ontology_id=from_ontology_id,
            to_ontology_id=to_ontology_id,
            dry_run=bool(inputs.get("dry_run", False)),
            base_url=inputs.get("depo_api_base_url"),
        )
        return {
            "workflow_id": "depo_ontology_merge",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_orchestrator_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _workflow_depo_import_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        task_id = str(inputs.get("task_id") or "").strip()
        export_format = str(inputs.get("export_format") or "ttl").strip().lower()
        output_dir = inputs.get("output_dir", str(settings.output_dir / "depo_exports"))
        if not task_id:
            raise ValueError("task_id is required")
        result = depo_export_import_owl(
            task_id=task_id,
            export_format=export_format,
            output_dir=output_dir,
            base_url=inputs.get("depo_api_base_url"),
        )
        return {
            "workflow_id": "depo_import_export",
            "status": "completed",
            "steps": [
                {
                    "agent": "ontology_export_agent",
                    "status": "completed",
                    "output": result,
                }
            ],
        }

    def _run_ontology_intake(self, inputs: dict[str, Any]) -> dict[str, Any]:
        ontology_path = inputs.get("ontology_path")
        if not ontology_path:
            raise ValueError("Missing required input: ontology_path")
        return inspect_ontology_artifact(ontology_path)

    def _run_ontology_structure_review(self, inputs: dict[str, Any]) -> dict[str, Any]:
        ontology_path = inputs.get("ontology_path")
        if not ontology_path:
            raise ValueError("Missing required input: ontology_path")
        return review_ontology_structure(ontology_path)

    def _run_semantic_bridge_planner(self, inputs: dict[str, Any]) -> dict[str, Any]:
        ontology_path = inputs.get("ontology_path")
        instance_metadata = inputs.get("instance_metadata", {})
        if not ontology_path:
            raise ValueError("Missing required input: ontology_path")
        if not isinstance(instance_metadata, dict):
            raise ValueError("instance_metadata must be an object")
        return plan_instance_alignment(ontology_path, instance_metadata)

    def _run_ontology_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        ontology_path = inputs.get("ontology_path")
        export_formats = inputs.get("export_formats", ["ttl"])
        output_dir = inputs.get("output_dir", str(settings.output_dir))
        if not ontology_path:
            raise ValueError("Missing required input: ontology_path")
        if not isinstance(export_formats, list) or not export_formats:
            raise ValueError("export_formats must be a non-empty list")

        exports = [export_ontology(ontology_path, output_dir, fmt) for fmt in export_formats]
        return {"exports": exports, "status": "completed"}

    def _run_ontology_orchestrator(self, inputs: dict[str, Any]) -> dict[str, Any]:
        requested_workflow = str(inputs.get("workflow_id", "ontology_review")).strip()
        if inputs.get("execution_mode") == "depo_api" and requested_workflow in {"ontology_review", "ontology_alignment", "ontology_export"}:
            requested_workflow = str(inputs.get("depo_workflow_id") or requested_workflow).strip()
        return self.run_workflow(requested_workflow, inputs)
