from pathlib import Path

from data_product_package.integration import build_from_app_outputs


def test_build_from_app_outputs_preserves_lineage_and_artifact(tmp_path: Path) -> None:
    source = tmp_path / "graph.jsonld"
    source.write_text('{"@context": {}}', encoding="utf-8")

    result = build_from_app_outputs(
        output_dir=str(tmp_path / "output"),
        product={"product_id": "dp-1", "name": "Engineering Graph"},
        artifacts=[{"path": str(source), "kind": "graph", "format": "jsonld"}],
        ontologies=[{"id": "ap242", "prefix": "ap242"}],
        sources=[{"id": "task-1", "type": "ImportTask", "name": "part.stpx"}],
    )

    manifest = result["manifest"]
    assert manifest["validation"]["valid"] is True
    assert manifest["ontologies"][0]["prefix"] == "ap242"
    assert manifest["sources"][0]["id"] == "task-1"
    assert Path(result["zip"]).is_file()
