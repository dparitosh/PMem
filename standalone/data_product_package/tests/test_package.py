import json
from pathlib import Path
import zipfile

from data_product_package.builder import DataProductBuilder
from data_product_package.catalog import read_xlsx_catalog
from data_product_package.models import ArtifactSpec, DataProductSpec


def test_catalog_reader_reads_reference_workbook(tmp_path):
    workbook = tmp_path / "catalog.xlsx"
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Recommended Table / Graph Label</t></si>
              <si><t>Ontology Registry / OntologyMetadata</t></si>
            </sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
              <row r="1"><c r="A1" t="s"><v>0</v></c></row>
              <row r="2"><c r="A2" t="s"><v>1</v></c></row>
            </sheetData></worksheet>""",
        )

    catalog = read_xlsx_catalog(str(workbook))
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
