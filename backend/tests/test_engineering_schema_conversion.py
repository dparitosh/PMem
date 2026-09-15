from backend.ingestion_service.schema_conversion import converter
from backend.artifact_store import ArtifactStore
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


def test_schema_serialization_retains_an_analytics_product_draft(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE", str(tmp_path / "artifacts"))
    result = converter.convert(filename="demo.xsd", content=b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test"><xs:element name="Part" type="xs:string"/></xs:schema>''')

    assert set(result["artifacts"]) == {"source", "serialization", "analytics_profile"}
    assert result["data_product_draft"]["contract"] == "schema-analytics-data-product-v1"
    assert result["data_product_draft"]["artifacts"] == list(result["artifacts"].values())
    metadata, _ = ArtifactStore().resolve(result["artifacts"]["analytics_profile"])
    assert metadata["kind"] == "schema-analytics-profile"
