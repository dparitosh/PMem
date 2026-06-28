from __future__ import annotations

from typing import Any

from ontology_agentic.config import settings
from ontology_agentic.runtime.registry import AgentRegistry
from ontology_agentic.tools.depo_api_tools import (
    depo_execute_semantic_workflow,
    depo_export_import_owl,
    depo_healthcheck,
    depo_list_registered_ontologies,
    depo_merge_ontologies,
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
            "depo_healthcheck": self._workflow_depo_healthcheck,
            "depo_registered_ontologies": self._workflow_depo_registered_ontologies,
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
