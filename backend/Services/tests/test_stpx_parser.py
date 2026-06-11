from pathlib import Path

from backend.Services.unified_data_import import FileParser
from backend.Services.step_parser import detect_step_format, iter_part21_entities, parse_step_metadata


def test_stpx_streaming_parser_preserves_identifiers_refs_and_text(tmp_path: Path):
    stpx = """<?xml version="1.0" encoding="UTF-8"?>
<Uos xmlns="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model bom.xsd">
  <Header>
    <Name>Example STPX</Name>
  </Header>
  <Part uid="part-1" id="PartOne" type="n0:PartType">
    <Name>Motor Assembly</Name>
    <Occurrence uid="occ-1" uidRef="part-1" idContextRef="ctx-1">
      <Identifier>OCC-1</Identifier>
    </Occurrence>
  </Part>
</Uos>
"""
    path = tmp_path / "sample.stpx"
    path.write_text(stpx, encoding="utf-8")

    assert detect_step_format(path) == "stpx"
    meta = parse_step_metadata(path)
    assert meta.format == "stpx"
    assert meta.file_schema == "bo_model"

    entities = list(iter_part21_entities(path))
    assert len(entities) >= 5
    assert any(e.entity_type == "PART" and e.source_identifier == "PartOne" for e in entities)
    assert any(e.entity_type == "OCCURRENCE" and e.ref_ids for e in entities)
    assert any(e.text_value == "Motor Assembly" for e in entities)

    rows, stats = FileParser._parse_step(path.read_bytes())
    assert rows
    assert stats["format"] == "STEP"
    assert stats["unresolved_reference_count"] >= 1
    occurrence_rows = [row for row in rows if row.get("entity_type") == "OCCURRENCE"]
    assert occurrence_rows
    assert occurrence_rows[0]["uidRef"] == "part-1"
    assert occurrence_rows[0]["parent_step_id"].startswith("#")
