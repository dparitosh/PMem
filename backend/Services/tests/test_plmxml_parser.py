from pathlib import Path

from backend.Services.unified_data_import import FileParser
from backend.Services.plmxml_parser import parse_plmxml_file


def test_plmxml_parser_collects_stats_duplicates_and_unresolved_refs(tmp_path: Path):
    plmxml = """<?xml version="1.0" encoding="UTF-8"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="7" author="test">
  <Product id="PartA" name="Assembly A" />
  <Product id="PartA" name="Assembly A Duplicate" />
  <ProductInstance id="Inst1" name="Inst A" partRef="PartA" parentRef="MissingParent" />
  <ProductView id="View1" name="Main View" rootRefs="Inst1 MissingRoot" productRef="PartA" />
  <Relationship id="Rel1" source="Inst1" target="PartA" type="USES" />
</PLMXML>
"""
    file_path = tmp_path / "sample.plmxml"
    file_path.write_text(plmxml, encoding="utf-8")

    doc = parse_plmxml_file(file_path)

    assert doc.parse_stats["elements_parsed"] >= 5
    assert doc.parse_stats["duplicate_ids"] == 1
    assert doc.parse_stats["unresolved_references"] >= 2
    assert "PartA" in doc.duplicate_ids
    assert any(item["target_id"] == "MissingParent" for item in doc.unresolved_references)
    assert any(item["target_id"] == "MissingRoot" for item in doc.unresolved_references)
    assert any(rel.source_id == "Inst1" and rel.target_id == "PartA" for rel in doc.relationships)


def test_plmxml_import_skips_structural_metadata_nodes():
    plmxml = """<?xml version="1.0" encoding="UTF-8"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="7" author="test">
  <Product id="PartA" name="Assembly A" />
  <ProductInstance id="Inst1" name="Inst A" partRef="PartA" />
  <Form id="id12" name="id12" subType="AccessIntent" subClass="AccessIntent" />
  <AccessIntent id="id12" name="id12" label="AccessIntent" />
</PLMXML>
"""

    rows, stats = FileParser._parse_plmxml(plmxml.encode("utf-8"))

    element_types = {row.get("element_type") for row in rows}
    assert "Part" in element_types
    assert "ProductInstance" in element_types
    assert "Form" not in element_types
    assert "AccessIntent" not in element_types
    assert stats["metadata_only_entities_skipped"] >= 2
