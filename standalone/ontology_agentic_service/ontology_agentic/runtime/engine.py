"""Minimal ontology-agent runtime used by the standalone HTTP adapter."""

from __future__ import annotations

from typing import Any

from ontology_agentic.config import settings
from ontology_agentic.runtime.registry import AgentRegistry
from ontology_agentic.tools.ontology_tools import (
    ontology_alignment_plan,
    ontology_export,
    ontology_inspect,
    ontology_review,
)


class OntologyWorkflowEngine:
    def __init__(self) -> None:
        self.registry = AgentRegistry(settings.agent_specs_dir)
        self._register_agents()

    def _register_agents(self) -> None:
        specs = settings.agent_specs_dir
        self.registry.register("ontology_intake_handler", self._run_intake, specs / "ontology_intake_agent.yaml")
        self.registry.register("ontology_review_handler", self._run_review, specs / "ontology_review_agent.yaml")
        self.registry.register("ontology_alignment_handler", self._run_alignment, specs / "ontology_alignment_agent.yaml")
        self.registry.register("ontology_export_handler", self._run_export, specs / "ontology_export_agent.yaml")

    def run_agent(self, agent_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        agent = self.registry.get(agent_name)
        return {
            "agent": agent.spec.name,
            "handler": agent.handler_name,
            "result": agent.handler(inputs),
        }

    def run_workflow(self, workflow_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        workflows = {
            "ontology_lifecycle": self._workflow_lifecycle,
            "ontology_review": self._workflow_review,
            "ontology_alignment": self._workflow_alignment,
            "ontology_export": self._workflow_export,
        }
        try:
            return workflows[workflow_id](inputs)
        except KeyError as exc:
            raise KeyError(f"Unknown workflow: {workflow_id}") from exc

    @staticmethod
    def _blocking_issues(review: dict[str, Any]) -> list[dict[str, Any]]:
        return [issue for issue in review["issues"] if issue.get("severity") == "high"]

    def _workflow_review(self, inputs: dict[str, Any]) -> dict[str, Any]:
        intake = self._run_intake(inputs)
        review = self._run_review(inputs)
        return {
            "workflow_id": "ontology_review",
            "status": review["status"],
            "steps": [
                {"agent": "ontology_intake_agent", "status": "completed", "output": intake},
                {"agent": "ontology_review_agent", "status": "completed", "output": review},
            ],
        }

    def _workflow_alignment(self, inputs: dict[str, Any]) -> dict[str, Any]:
        reviewed = self._workflow_review(inputs)
        blocking = self._blocking_issues(reviewed["steps"][-1]["output"])
        if blocking and not bool(inputs.get("continue_on_review", False)):
            return {**reviewed, "workflow_id": "ontology_alignment", "status": "review_required", "blocking_issues": blocking}
        reviewed["steps"].append(
            {"agent": "ontology_alignment_agent", "status": "completed", "output": self._run_alignment(inputs)}
        )
        reviewed.update(workflow_id="ontology_alignment", status="completed")
        return reviewed

    def _workflow_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        aligned = self._workflow_alignment(inputs)
        if aligned["status"] == "review_required":
            return {**aligned, "workflow_id": "ontology_export"}
        aligned["steps"].append(
            {"agent": "ontology_export_agent", "status": "completed", "output": self._run_export(inputs)}
        )
        aligned.update(workflow_id="ontology_export", status="completed")
        return aligned

    def _workflow_lifecycle(self, inputs: dict[str, Any]) -> dict[str, Any]:
        result = self._workflow_alignment(inputs)
        result["workflow_id"] = "ontology_lifecycle"
        if result["status"] == "review_required" or not inputs.get("output_dir"):
            return result
        result["steps"].append(
            {"agent": "ontology_export_agent", "status": "completed", "output": self._run_export(inputs)}
        )
        return result

    @staticmethod
    def _ontology_path(inputs: dict[str, Any]) -> str:
        value = str(inputs.get("ontology_path") or "").strip()
        if not value:
            raise ValueError("Missing required input: ontology_path")
        return value

    def _run_intake(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return ontology_inspect(self._ontology_path(inputs))

    def _run_review(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return ontology_review(
            self._ontology_path(inputs),
            profile=str(inputs.get("review_profile") or "schema"),
        )

    def _run_alignment(self, inputs: dict[str, Any]) -> dict[str, Any]:
        metadata = inputs.get("instance_metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("instance_metadata must be an object")
        return ontology_alignment_plan(self._ontology_path(inputs), metadata)

    def _run_export(self, inputs: dict[str, Any]) -> dict[str, Any]:
        output_dir = str(inputs.get("output_dir") or "").strip()
        if not output_dir:
            raise ValueError("Missing required input: output_dir")
        formats = inputs.get("export_formats", ["ttl"])
        if not isinstance(formats, list) or not formats or not all(isinstance(item, str) for item in formats):
            raise ValueError("export_formats must be a non-empty array of strings")
        exports = [ontology_export(self._ontology_path(inputs), output_dir, item) for item in formats]
        return {"status": "completed", "exports": exports}
