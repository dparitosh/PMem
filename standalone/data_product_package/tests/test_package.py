import json
from pathlib import Path

from data_product_package.builder import DataProductBuilder
from data_product_package.catalog import read_xlsx_catalog
from data_product_package.models import ArtifactSpec, DataProductSpec


def test_catalog_reader_reads_reference_workbook():
    catalog = read_xlsx_catalog(r"D:\dataproduct1.xlsx")
    assert catalog["records"]
    assert catalog["records"][0]["Recommended Table / Graph Label"] == "Ontology Registry / OntologyMetadata"


def test_builder_creates_checksummed_directory_and_zip(tmp_path):
    source = tmp_path / "ontology.ttl"
    source.write_text("@prefix ex: <https://example.test/> .\n", encoding="utf-8")
    spec = DataProductSpec(
        product_id="dp-test",
        name="Test Product",
        ontologies=[{"id": "test", "prefix": "ex"}],
        artifacts=[ArtifactSpec(path=str(source), kind="ontology", format="ttl")],
    )
    result = DataProductBuilder(str(tmp_path / "output")).build(spec)
    manifest = json.loads(Path(result["directory"], "manifest.json").read_text(encoding="utf-8"))
    assert Path(result["zip"]).is_file()
    assert manifest["validation"]["valid"] is True
    assert len(manifest["artifacts"][0]["sha256"]) == 64
