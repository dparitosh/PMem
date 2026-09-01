from pathlib import Path

from backend.ingestion_service.schema_conversion import converter


def test_ap242_express_schema_converts_to_traceable_ontology():
    source = Path("data/modules/ap242_managed_model_based_3d_engineering/mim_lf.exp")
    result = converter.convert(filename=source.name, content=source.read_bytes())
    assert result["format"] == "EXPRESS"
    assert result["source_kind"] == "schema"
    assert result["statistics"]["entity_count"] >= 2000
    assert "owl:Class" in result["ontology"]["turtle"]
