"""Deployment-owned strategy registry for processing jobs.

Register trusted handlers during startup, never from request-provided code.
Contracts and execution strategy share one definition to prevent drift.
"""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class JobHandler:
    input_contract: str
    output_contract: str
    execute: Callable[..., dict[str, Any]]


class HandlerRegistry:
    def __init__(self):
        self._handlers: dict[str, JobHandler] = {}

    def register(self, name: str, handler: JobHandler) -> None:
        if name in self._handlers:
            raise ValueError(f"Job handler already registered: {name}")
        self._handlers[name] = handler

    def get(self, name: str) -> JobHandler:
        try:
            return self._handlers[name]
        except KeyError as exc:
            raise ValueError(f"Unsupported job handler: {name}") from exc

    def contracts(self):
        return {name: (h.input_contract, h.output_contract) for name, h in self._handlers.items()}


def _method(name, **options):
    def execute(runner, payload, *, correlation_id):
        return getattr(runner, name)(payload, correlation_id=correlation_id, **options)
    return execute


registry = HandlerRegistry()
for name, input_contract, output_contract, method, options in [
    ("interactive-quality-summary", "quality-records-v1", "quality-summary-v1", "transform_quality_summary", {}),
    ("data-quality-assessment", "quality-records-v1", "data-quality-report-v1", "assess_data_quality", {}),
    ("schema-analytics-product", "engineering-schema-artifact-v1", "schema-analytics-data-product-draft-v1", "build_schema_analytics_product", {}),
    ("normalize-ceim", "source-ceim-batch-v1", "normalized-ceim-batch-v1", "normalize_ceim_batch", {"validate": False}),
    ("validate-semantic-batch", "source-ceim-batch-v1", "semantic-validation-report-v1", "normalize_ceim_batch", {"validate": True}),
    ("validate-unstructured-evidence", "unstructured-evidence-batch-v1", "validated-unstructured-evidence-v1", "validate_unstructured_evidence", {}),
    ("enrich-document-evidence", "unstructured-evidence-batch-v1", "document-graph-proposal-v1", "enrich_document_evidence", {}),
    ("normalize-unstructured-ceim", "document-graph-proposal-v1", "semantic-validation-report-v1", "normalize_unstructured_ceim", {}),
    ("rdf-quality-statistics", "rdf-artifact-v1", "rdf-quality-report-v1", "rdf_quality_statistics", {}),
    ("rdf-deduplicate-serialize", "rdf-artifact-v1", "canonical-ntriples-v1", "rdf_deduplicate_serialize", {}),
]:
    registry.register(name, JobHandler(input_contract, output_contract, _method(method, **options)))
