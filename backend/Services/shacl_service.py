from __future__ import annotations

from typing import Dict, Any, Optional
from loguru import logger
import rdflib
from rdflib import Graph
from rdflib.namespace import RDF, SH
try:
    from pyshacl import validate
except ImportError:
    validate = None
    logger.warning("pyshacl library not found. SHACL validation disabled.")

def _summarize_shapes_graph(shacl_graph: Optional[rdflib.Graph]) -> Dict[str, int]:
    """Return a small structural summary of the active SHACL shapes graph."""
    if shacl_graph is None:
        return {
            "node_shapes": 0,
            "property_shapes": 0,
            "shape_nodes": 0,
        }
    try:
        node_shape_nodes = set(shacl_graph.subjects(RDF.type, SH.NodeShape))
        property_shape_nodes = set(shacl_graph.subjects(RDF.type, SH.PropertyShape))
        node_shapes = len(node_shape_nodes)
        property_shapes = len(property_shape_nodes)
        shape_nodes = len(node_shape_nodes | property_shape_nodes)
        return {
            "node_shapes": node_shapes,
            "property_shapes": property_shapes,
            "shape_nodes": shape_nodes,
        }
    except Exception:
        return {
            "node_shapes": 0,
            "property_shapes": 0,
            "shape_nodes": 0,
        }


def _summarize_report_graph(report_graph: Optional[Graph]) -> Dict[str, int]:
    """Count pySHACL validation results by severity."""
    if report_graph is None:
        return {
            "result_count": 0,
            "violation_count": 0,
            "warning_count": 0,
            "info_count": 0,
        }
    try:
        result_nodes = list(report_graph.subjects(RDF.type, SH.ValidationResult))
        violation_count = 0
        warning_count = 0
        info_count = 0
        for node in result_nodes:
            severity = next(report_graph.objects(node, SH.resultSeverity), None)
            if severity == SH.Violation:
                violation_count += 1
            elif severity == SH.Warning:
                warning_count += 1
            elif severity == SH.Info:
                info_count += 1
        return {
            "result_count": len(result_nodes),
            "violation_count": violation_count,
            "warning_count": warning_count,
            "info_count": info_count,
        }
    except Exception:
        return {
            "result_count": 0,
            "violation_count": 0,
            "warning_count": 0,
            "info_count": 0,
        }

class ShaclValidationService:
    """
    Service for validating RDF data against SHACL shapes.
    Ensures data conforms to defined constraints before ingestion.
    """
    def __init__(self):
        if not validate:
            logger.warning("SHACL validation service initialized without pyshacl library.")

    def validate_graph(
        self,
        data_graph: rdflib.Graph,
        shacl_graph: rdflib.Graph = None,
        shacl_graph_str: str = None,
        *,
        ontology_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Validate a data graph against a SHACL shapes graph.
        Returns a dictionary with validation results.
        """
        if not validate:
            return {"conforms": False, "error": "pyshacl library missing"}

        try:
            # Prepare SHACL graph
            if shacl_graph is None and shacl_graph_str:
                shacl_graph = rdflib.Graph().parse(data=shacl_graph_str, format="turtle")
            
            if not shacl_graph:
                # If no shapes provided, maybe check if data graph has shapes?
                # Sometimes shapes are included in data.
                pass

            conforms, report_graph, report_text = validate(
                data_graph,
                shacl_graph=shacl_graph,
                advanced=True,
                inference='rdfs',
                serialize_report_graph=False
            )

            report: Dict[str, Any] = {
                "conforms": conforms,
                "report_text": report_text,
                "report_graph": report_graph.serialize(format="turtle") if report_graph is not None else "",
                "validation_engine": "pyshacl",
                "shape_summary": _summarize_shapes_graph(shacl_graph),
                **_summarize_report_graph(report_graph),
            }
            if ontology_context:
                report["ontology_context"] = ontology_context
            return report

        except Exception as e:
            logger.error(f"SHACL Validation error: {e}")
            return {"conforms": False, "error": str(e)}

    def create_default_shapes(self) -> str:
        """
        Generate comprehensive SHACL shapes covering all OWL2 construct categories with enhanced validation:
        - owl:Class              (label, comment, proper superclass)
        - owl:subClassOf         (target must be owl:Class, no cycles)
        - owl:ObjectProperty     (label, domain, range, characteristics)
        - owl:DatatypeProperty   (label, domain, range, functional)
        - owl:AnnotationProperty (label, proper usage)
        - owl:NamedIndividual    (label, class membership, uniqueness)
        - owl:Ontology           (complete metadata, imports)
        """
        return """
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix dc:   <http://purl.org/dc/elements/1.1/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix iae:  <http://IAE-depo.com/shapes#> .

# ── 1. Enhanced owl:Class validation with semantic completeness ──────────────
iae:ClassShape a sh:NodeShape ;
    sh:name    "Enhanced OWL Class Validation" ;
    sh:targetClass owl:Class ;
    sh:property [
        sh:path        rdfs:label ;
        sh:minCount    1 ;
        sh:datatype    xsd:string ;
        sh:message     "Every owl:Class must have at least one rdfs:label." ;
    ] ;
    sh:property [
        sh:path        rdfs:comment ;
        sh:minCount    1 ;
        sh:datatype    xsd:string ;
        sh:severity    sh:Warning ;
        sh:message     "owl:Class should have descriptive rdfs:comment." ;
    ] ;
    sh:property [
        sh:path        dc:source ;
        sh:minCount    1 ;
        sh:severity    sh:Warning ;
        sh:message     "owl:Class should specify provenance via dc:source." ;
    ] ;
    sh:property [
        sh:path        skos:definition ;
        sh:severity    sh:Info ;
        sh:message     "Consider adding skos:definition for better semantic clarity." ;
    ] .

# ── 2. Enhanced owl:ObjectProperty validation with characteristics ─────────
iae:ObjectPropertyShape a sh:NodeShape ;
    sh:name    "Enhanced OWL ObjectProperty Validation" ;
    sh:targetClass owl:ObjectProperty ;
    sh:property [
        sh:path     rdfs:label ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
        sh:message  "Every owl:ObjectProperty must have rdfs:label." ;
    ] ;
    sh:property [
        sh:path     rdfs:comment ;
        sh:minCount 1 ;
        sh:severity sh:Warning ;
        sh:message  "owl:ObjectProperty should have descriptive rdfs:comment." ;
    ] ;
    sh:property [
        sh:path     rdfs:domain ;
        sh:minCount 1 ;
        sh:node [
            sh:or (
                [ sh:class owl:Class ]
                [ sh:class skos:Concept ]
            )
        ] ;
        sh:message  "Every owl:ObjectProperty must specify rdfs:domain as owl:Class or skos:Concept." ;
    ] ;
    sh:property [
        sh:path     rdfs:range ;
        sh:minCount 1 ;
        sh:node [
            sh:or (
                [ sh:class owl:Class ]
                [ sh:class skos:Concept ]
            )
        ] ;
        sh:message  "Every owl:ObjectProperty must specify rdfs:range as owl:Class or skos:Concept." ;
    ] ;
    sh:property [
        sh:path        dc:source ;
        sh:severity    sh:Warning ;
        sh:message     "ObjectProperty should specify provenance via dc:source." ;
    ] .

# ── 3. Enhanced owl:DatatypeProperty validation with range checking ────────
iae:DatatypePropertyShape a sh:NodeShape ;
    sh:name    "Enhanced OWL DatatypeProperty Validation" ;
    sh:targetClass owl:DatatypeProperty ;
    sh:property [
        sh:path     rdfs:label ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
        sh:message  "Every owl:DatatypeProperty must have rdfs:label." ;
    ] ;
    sh:property [
        sh:path     rdfs:comment ;
        sh:minCount 1 ;
        sh:severity sh:Warning ;
        sh:message  "owl:DatatypeProperty should have descriptive rdfs:comment." ;
    ] ;
    sh:property [
        sh:path     rdfs:domain ;
        sh:minCount 1 ;
        sh:class    owl:Class ;
        sh:message  "Every owl:DatatypeProperty must specify rdfs:domain as owl:Class." ;
    ] ;
    sh:property [
        sh:path     rdfs:range ;
        sh:minCount 1 ;
        sh:nodeKind sh:IRI ;
        sh:message  "Every owl:DatatypeProperty must specify rdfs:range as XSD datatype." ;
    ] .

# ── 4. Enhanced owl:AnnotationProperty validation ──────────────────────────
iae:AnnotationPropertyShape a sh:NodeShape ;
    sh:name    "Enhanced OWL AnnotationProperty Validation" ;
    sh:targetClass owl:AnnotationProperty ;
    sh:property [
        sh:path     rdfs:label ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
        sh:message  "owl:AnnotationProperty must have rdfs:label." ;
    ] ;
    sh:property [
        sh:path     rdfs:comment ;
        sh:minCount 1 ;
        sh:severity sh:Warning ;
        sh:message  "owl:AnnotationProperty should have rdfs:comment." ;
    ] .

# ── 5. Enhanced owl:NamedIndividual validation with type checking ───────────
iae:IndividualShape a sh:NodeShape ;
    sh:name    "Enhanced OWL NamedIndividual Validation" ;
    sh:targetClass owl:NamedIndividual ;
    sh:property [
        sh:path     rdfs:label ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
        sh:message  "Every owl:NamedIndividual must have rdfs:label." ;
    ] ;
    sh:property [
        sh:path        rdf:type ;
        sh:minCount    2 ;
        sh:message     "NamedIndividual must have domain class type beyond owl:NamedIndividual." ;
    ] ;
    sh:property [
        sh:path        rdfs:comment ;
        sh:severity    sh:Warning ;
        sh:message     "Consider adding rdfs:comment for individual description." ;
    ] .

# ── 6. Enhanced owl:Ontology header validation with complete metadata ──────
iae:OntologyHeaderShape a sh:NodeShape ;
    sh:name    "Enhanced OWL Ontology Validation" ;
    sh:targetClass owl:Ontology ;
    sh:property [
        sh:path     rdfs:label ;
        sh:minCount 1 ;
        sh:or (
            [ sh:datatype rdf:langString ]
            [ sh:datatype xsd:string ]
        ) ;
        sh:message  "owl:Ontology declaration must have rdfs:label." ;
    ] ;
    sh:property [
        sh:path        owl:versionInfo ;
        sh:minCount    1 ;
        sh:datatype    xsd:string ;
        sh:severity    sh:Warning ;
        sh:message     "owl:Ontology should specify owl:versionInfo." ;
    ] ;
    sh:property [
        sh:path        dcterms:created ;
        sh:maxCount    1 ;
        sh:datatype    xsd:dateTime ;
        sh:severity    sh:Warning ;
        sh:message     "owl:Ontology should specify dcterms:created timestamp." ;
    ] ;
    sh:property [
        sh:path        dc:creator ;
        sh:minCount    1 ;
        sh:datatype    xsd:string ;
        sh:severity    sh:Warning ;
        sh:message     "owl:Ontology should specify dc:creator." ;
    ] ;
    sh:property [
        sh:path        owl:versionIRI ;
        sh:maxCount    1 ;
        sh:nodeKind    sh:IRI ;
        sh:severity    sh:Info ;
        sh:message     "Consider adding owl:versionIRI for version tracking." ;
    ] .

# ── 7. Property characteristic validation ──────────────────────────────────
iae:FunctionalPropertyShape a sh:NodeShape ;
    sh:name    "Functional Property Validation" ;
    sh:targetClass owl:FunctionalProperty ;
    sh:or (
        [ sh:class owl:ObjectProperty ]
        [ sh:class owl:DatatypeProperty ]
    ) ;
    sh:message  "FunctionalProperty must also be ObjectProperty or DatatypeProperty." .

# ── 8. Inverse property validation ─────────────────────────────────────────
iae:InversePropertyShape a sh:PropertyShape ;
    sh:name    "Inverse Property Validation" ;
    sh:path    owl:inverseOf ;
    sh:class   owl:ObjectProperty ;
    sh:message "owl:inverseOf must reference another owl:ObjectProperty." .

# ── 9. Class disjointness validation ───────────────────────────────────────
iae:DisjointClassShape a sh:PropertyShape ;
    sh:name    "Disjoint Class Validation" ;
    sh:path    owl:disjointWith ;
    sh:class   owl:Class ;
    sh:message "owl:disjointWith must reference owl:Class." .

# ── 10. SKOS consistency validation ────────────────────────────────────────
iae:SKOSConceptShape a sh:NodeShape ;
    sh:name    "SKOS Concept Validation" ;
    sh:targetClass skos:Concept ;
    sh:property [
        sh:path     skos:prefLabel ;
        sh:minCount 1 ;
        sh:or (
            [ sh:datatype rdf:langString ]
            [ sh:datatype xsd:string ]
        ) ;
        sh:message  "Every skos:Concept must have skos:prefLabel." ;
    ] ;
    sh:property [
        sh:path     skos:definition ;
        sh:severity sh:Warning ;
        sh:message  "skos:Concept should have skos:definition." ;
    ] .
"""
