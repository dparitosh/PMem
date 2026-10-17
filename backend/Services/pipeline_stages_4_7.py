"""Retirement shim for the historical stage simulator.

Read-only validation is maintained in ontology_validation_service. The former
load, enrichment and health estimates are not graph or publication evidence.
"""
from .ontology_validation_service import OntologyValidationService, ValidationMetrics

RETIRED_MESSAGE = (
    'The simulated stage 4-7 pipeline is retired. Use the engineering workflow '
    'and governed ontology/graph publication APIs. Verify retained publication '
    'receipts before reporting graph writes or post-publication health.'
)


class OntologyEnrichmentService:
    @staticmethod
    def enrich(owl_ttl, schema_metadata):
        raise RuntimeError(RETIRED_MESSAGE)


class Neo4jLoadService:
    @staticmethod
    def load_to_neo4j(owl_ttl, schema_metadata, task_id):
        raise RuntimeError(RETIRED_MESSAGE)


class HealthCheckService:
    @staticmethod
    def verify(task_id, load_metrics, schema_metadata):
        raise RuntimeError(RETIRED_MESSAGE)


class UnifiedStage4to7Service:
    def process_stages(self, owl_ttl, schema_metadata, task_id):
        raise RuntimeError(RETIRED_MESSAGE)
