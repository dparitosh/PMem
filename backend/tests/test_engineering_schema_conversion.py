from backend.ingestion_service.schema_conversion import converter
from rdflib import Graph


EXPRESS = b"""SCHEMA demo; ENTITY Part; identifier : STRING; END_ENTITY; END_SCHEMA;"""
STEP = b"""ISO-10303-21;
HEADER; FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING')); ENDSEC;
DATA; #1 = PRODUCT('P-1','Part','Demo',()); ENDSEC; END-ISO-10303-21;"""


def test_express_and_step_share_the_normalized_conversion_contract():
    express = converter.convert(filename="demo.exp", content=EXPRESS)
    step = converter.convert(filename="demo.stp", content=STEP)

    for result in (express, step):
        assert {"format", "source_kind", "ontology", "statistics", "next_action"} <= set(result)
        assert {"name", "prefix", "base_uri", "turtle"} <= set(result["ontology"])
        assert result["ontology"]["turtle"].strip()
    assert express["source_kind"] == "schema"
    Graph().parse(data=express["ontology"]["turtle"], format="turtle")
    assert step["source_kind"] == "instance"


def test_step_extensions_share_one_converter():
    for filename in ("demo.stp", "demo.step", "demo.stpx"):
        assert converter.convert(filename=filename, content=STEP)["format"] == "STEP"
