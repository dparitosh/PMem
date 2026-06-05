"""Focused smoke tests for OWL generation and SHACL validation services."""

from __future__ import annotations

import rdflib

from backend.Services.owl_generation_service import OWLGenerationService
from backend.Services.shacl_service import ShaclValidationService


def test_owl_generation_from_minimal_xmi() -> None:
    xmi = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xmi:XMI xmlns:xmi="http://www.omg.org/XMI" '
        'xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">'
        '<uml:Model xmi:id="_model" name="TestModel">'
        '<packagedElement xmi:type="uml:Class" xmi:id="_cls1" name="Wheel"/>'
        '<packagedElement xmi:type="uml:Class" xmi:id="_cls2" name="Axle"/>'
        "</uml:Model>"
        "</xmi:XMI>"
    ).encode("utf-8")

    ttl, metadata = OWLGenerationService.generate_owl(xmi, "test.xmi")

    assert "Wheel" in ttl
    assert metadata.get("format")


def test_shacl_validation_accepts_valid_graph() -> None:
    data_graph = rdflib.Graph().parse(
        data="""
        @prefix ex: <http://example.org/> .
        ex:Alice a ex:Person ; ex:name "Alice" .
        """,
        format="turtle",
    )
    shacl_ttl = """
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        @prefix ex: <http://example.org/> .
        ex:PersonShape a sh:NodeShape ;
            sh:targetClass ex:Person ;
            sh:property [
                sh:path ex:name ;
                sh:datatype xsd:string ;
                sh:minCount 1
            ] .
    """

    result = ShaclValidationService().validate_graph(data_graph, shacl_graph_str=shacl_ttl)

    assert result["conforms"] is True
    assert result.get("violation_count", 0) == 0

