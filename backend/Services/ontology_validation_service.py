"""Read-only ontology validation; graph persistence requires a publication receipt."""
from typing import Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationMetrics:
    """Stage 4: Validation Results"""
    valid: bool
    errors: int
    warnings: int
    schema_triples: int
    class_count: int
    property_count: int
    issues: list


class OntologyValidationService:
    """Read-only RDF/SHACL validation with observed graph counts"""

    @staticmethod
    def validate(owl_ttl: str, schema_metadata: Dict) -> ValidationMetrics:
        """
        Validates OWL/Turtle ontology structure
        """
        try:
            from .owl_generation_service import OWLGenerationService
            from rdflib import Graph
            from rdflib.namespace import RDF, OWL
            graph = Graph().parse(data=owl_ttl, format='turtle')
            report = OWLGenerationService.validate_with_shacl(owl_ttl)
            valid = report.get('conforms') is True and not report.get('error')
            return ValidationMetrics(
                valid=valid,
                errors=int(report.get('violation_count') or (0 if valid else 1)),
                warnings=int(report.get('warning_count') or 0),
                schema_triples=len(graph),
                class_count=len(set(graph.subjects(RDF.type, OWL.Class))),
                property_count=len(set(graph.subjects(RDF.type, OWL.ObjectProperty)) |
                                   set(graph.subjects(RDF.type, OWL.DatatypeProperty))),
                issues=[] if valid else ['Ontology SHACL validation failed or is unavailable; review the validation report.']
            )

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationMetrics(
                valid=False,
                errors=1,
                warnings=0,
                schema_triples=0,
                class_count=0,
                property_count=0,
                issues=[str(e)]
            )
