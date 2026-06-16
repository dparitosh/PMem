from pathlib import Path
import asyncio
import pytest

from backend.Services.unified_data_import import DataTransformer, FileParser, FileType, UnifiedDataImportService, import_tasks, _detect_xml_family
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


def test_plmxml_parser_exposes_configured_metadata_exclusion_tags(tmp_path: Path):
    plmxml = """<?xml version="1.0" encoding="UTF-8"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="7" author="test">
  <Product id="PartA" name="Assembly A" />
  <UserData id="UD1" type="PartMeta">
    <UserValue title="material" value="Steel" />
  </UserData>
  <AccessIntent id="AI1" name="ReadIntent" />
</PLMXML>
"""
    file_path = tmp_path / "metadata-config.plmxml"
    file_path.write_text(plmxml, encoding="utf-8")

    doc = parse_plmxml_file(file_path, metadata_exclusion_tags=["AccessIntent", "UserData"])

    assert "AccessIntent" in doc.parse_stats["metadata_exclusion_tags"]
    assert "UserData" in doc.parse_stats["metadata_exclusion_tags"]
    assert "UD1" in doc.user_data


def test_plmxml_import_flattens_metadata_refs_into_domain_rows():
    plmxml = """<?xml version="1.0" encoding="UTF-8"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="7" author="test">
  <Product id="PartA" name="Assembly A" masterRef="F1" userDataRefs="UD1" />
  <ProductInstance id="Inst1" name="Inst A" partRef="PartA" userDataRefs="UD1" />
  <UserData id="UD1" type="PartMeta" title="Part Metadata">
    <UserValue title="material" value="Steel" />
    <UserValue title="finish" value="Painted" />
  </UserData>
  <Form id="F1" name="MasterForm" subType="PartMaster" subClass="PartMaster">
    <Description>Master definition</Description>
    <UserData>
      <UserValue title="owning_user" value="teamcenter" />
    </UserData>
  </Form>
  <AccessIntent id="AI1" name="ReadIntent" />
</PLMXML>
"""

    rows, stats = FileParser._parse_plmxml(plmxml.encode("utf-8"))

    rows_by_type = {}
    for row in rows:
        rows_by_type.setdefault(row["element_type"], []).append(row)

    assert "Part" in rows_by_type
    assert "ProductInstance" in rows_by_type
    assert "UserData" not in rows_by_type
    assert "Form" not in rows_by_type
    assert "AccessIntent" not in rows_by_type

    part_row = next(row for row in rows if row["id"] == "PartA")
    inst_row = next(row for row in rows if row["id"] == "Inst1")

    assert part_row["user_data_material"] == "Steel"
    assert part_row["user_data_finish"] == "Painted"
    assert part_row["metadata_form_sub_type"] == "PartMaster"
    assert part_row["form_owning_user"] == "teamcenter"
    assert inst_row["user_data_material"] == "Steel"
    assert stats["metadata_properties_attached"] >= 2
    assert stats["metadata_only_entities_skipped"] >= 3


def test_start_import_persists_plmxml_metadata_exclusion_options(monkeypatch):
    UnifiedDataImportService.initialize()

    class _Loop:
        def __init__(self):
            self.calls = []

        def run_in_executor(self, executor, fn, *args):
            self.calls.append((executor, fn, args))
            return None

    fake_loop = _Loop()
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: fake_loop)
    monkeypatch.setattr(UnifiedDataImportService, "_persist_task", classmethod(lambda cls, task_id: None))
    monkeypatch.setattr(UnifiedDataImportService, "_write_artifact", classmethod(lambda cls, *args, **kwargs: None))
    monkeypatch.setattr(UnifiedDataImportService, "_prune_tasks", classmethod(lambda cls: None))

    task_id = asyncio.run(
        UnifiedDataImportService.start_import(
            b"<PLMXML/>",
            "sample.plmxml",
            "plmxml",
            parse_options={"metadata_exclusion_tags": ["AccessIntent", "CustomMeta"]},
        )
    )

    task = import_tasks[task_id]
    assert task["parse_options"]["metadata_exclusion_tags"] == ["AccessIntent", "CustomMeta"]
    assert task["stats"]["metadata_exclusion_tags"] == ["AccessIntent", "CustomMeta"]
    assert fake_loop.calls, "parse job was not scheduled"

    import_tasks.pop(task_id, None)


def test_plmxml_commit_pipeline_never_sends_metadata_only_rows_to_neo4j(monkeypatch):
    plmxml = """<?xml version="1.0" encoding="UTF-8"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="7" author="test">
  <Product id="PartA" name="Assembly A" masterRef="F1" userDataRefs="UD1" />
  <ProductInstance id="Inst1" name="Inst A" partRef="PartA" userDataRefs="UD1" />
  <UserData id="UD1" type="PartMeta" title="Part Metadata">
    <UserValue title="material" value="Steel" />
  </UserData>
  <Form id="F1" name="MasterForm" subType="PartMaster" subClass="PartMaster">
    <UserData>
      <UserValue title="owning_user" value="teamcenter" />
    </UserData>
  </Form>
  <AccessIntent id="AI1" name="ReadIntent" />
</PLMXML>
"""

    rows, stats = FileParser._parse_plmxml(plmxml.encode("utf-8"))
    schema = DataTransformer.auto_detect_schema(rows)
    executed_batches = []

    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.validate_before_ingest",
        lambda rows, schema: (True, ""),
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.check_duplicate_entries",
        lambda rows, schema: (0, []),
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.validate_indexes_and_constraints",
        lambda schema, merge_support_indexes: {"missing_indexes": [], "missing_constraints": []},
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.DataTransformer.create_indexes",
        lambda missing_indexes: [],
    )
    monkeypatch.setattr(
        UnifiedDataImportService,
        "_update_commit_state",
        classmethod(lambda cls, *args, **kwargs: None),
    )
    monkeypatch.setattr(
        UnifiedDataImportService,
        "_persist_task",
        classmethod(lambda cls, task_id: None),
    )

    def _capture_execute(queries, rows=None, batch_size=None, batch_callback=None):
        batch_rows = list(rows or [])
        executed_batches.append(batch_rows)
        if batch_callback:
            batch_callback(
                {
                    "batch_index": 1,
                    "rows_processed": len(batch_rows),
                }
            )
        return {
            "queries_executed": len(queries or []),
            "errors": [],
            "matched_rows": len(batch_rows),
        }

    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.execute_cypher",
        _capture_execute,
    )

    task = {
        "filename": "sample.plmxml",
        "file_type": "plmxml",
        "parsed_rows": rows,
        "stats": stats,
        "_xmi_relationships": stats.get("_xmi_relationships", []),
    }

    result = UnifiedDataImportService._commit_sync("task-plmxml-metadata", task, schema)

    flattened_rows = [row for batch in executed_batches for row in batch]
    node_rows = [row for row in flattened_rows if isinstance(row, dict) and "element_type" in row]
    rel_rows = [
        row for row in flattened_rows
        if isinstance(row, dict) and ("from_id" in row or "from_props" in row or "to_props" in row)
    ]

    assert node_rows
    assert {row["element_type"] for row in node_rows} == {"Part", "ProductInstance"}
    assert all(row.get("id") not in {"UD1", "F1", "AI1"} for row in node_rows)
    assert not any(row.get("from_id") in {"UD1", "F1", "AI1"} or row.get("to_id") in {"UD1", "F1", "AI1"} for row in rel_rows)
    assert result["nodes_created"] == 2


def test_plmxml_schema_prefers_import_row_key_for_multilabel_rows():
    schema = DataTransformer.auto_detect_schema(
        [
            {"element_type": "Part", "id": "PartA", "import_row_key": "PartA", "name": "Assembly A"},
            {"element_type": "ProductInstance", "id": "Inst1", "import_row_key": "Inst1", "name": "Instance A"},
        ]
    )

    merge_keys_by_label = {node["label"]: node["mergeKeys"] for node in schema["nodes"]}
    assert merge_keys_by_label["Part"] == ["import_row_key"]
    assert merge_keys_by_label["ProductInstance"] == ["import_row_key"]


def test_plmxml_commit_blocks_duplicate_source_identifiers(monkeypatch):
    rows = [{"element_type": "Part", "id": "PartA", "import_row_key": "PartA", "name": "Assembly A"}]
    schema = DataTransformer.auto_detect_schema(rows)

    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.validate_before_ingest",
        lambda rows, schema: (True, ""),
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.check_duplicate_entries",
        lambda rows, schema: (0, []),
    )

    task = {
        "filename": "duplicate.plmxml",
        "file_type": "plmxml",
        "parsed_rows": rows,
        "stats": {"ontology_prefix": "plmxml", "duplicate_ids": 1, "unresolved_references": 0},
        "_xmi_relationships": [],
    }

    with pytest.raises(ValueError, match="duplicate source identifiers"):
        UnifiedDataImportService._commit_sync("task-plmxml-duplicate", task, schema)


def test_plmxml_commit_preserves_relationship_properties(monkeypatch):
    rows = [
        {"element_type": "Part", "id": "PartA", "import_row_key": "PartA", "name": "Assembly A"},
        {"element_type": "ProductInstance", "id": "Inst1", "import_row_key": "Inst1", "name": "Instance A"},
    ]
    schema = DataTransformer.auto_detect_schema(rows)
    captured = {"queries": [], "rows": []}

    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.validate_before_ingest",
        lambda rows, schema: (True, ""),
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.check_duplicate_entries",
        lambda rows, schema: (0, []),
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.validate_indexes_and_constraints",
        lambda schema, merge_support_indexes: {"missing_indexes": [], "missing_constraints": []},
    )
    monkeypatch.setattr(
        "backend.Services.unified_data_import.DataTransformer.create_indexes",
        lambda missing_indexes: [],
    )
    monkeypatch.setattr(
        UnifiedDataImportService,
        "_update_commit_state",
        classmethod(lambda cls, *args, **kwargs: None),
    )
    monkeypatch.setattr(
        UnifiedDataImportService,
        "_persist_task",
        classmethod(lambda cls, task_id: None),
    )

    def _capture_execute(queries, rows=None, batch_size=None, batch_callback=None):
        captured["queries"].extend(list(queries or []))
        captured["rows"].extend(list(rows or []))
        return {
            "queries_executed": len(queries or []),
            "errors": [],
            "matched_rows": len(rows or []),
        }

    monkeypatch.setattr(
        "backend.Services.unified_data_import.Neo4jImporter.execute_cypher",
        _capture_execute,
    )

    task = {
        "filename": "relationships.plmxml",
        "file_type": "plmxml",
        "parsed_rows": rows,
        "stats": {"ontology_prefix": "plmxml", "duplicate_ids": 0, "unresolved_references": 0},
        "_xmi_relationships": [
            {
                "from_props": {"id": "Inst1"},
                "to_props": {"id": "PartA"},
                "type": "PART_REF",
                "properties": {"reference_key": "partRef", "source_tag": "ProductInstance"},
            }
        ],
    }

    result = UnifiedDataImportService._commit_sync("task-plmxml-rel-props", task, schema)

    assert any("SET rel +=" in query for query in captured["queries"])
    relationship_rows = [row for row in captured["rows"] if row.get("from_id") == "Inst1" and row.get("to_id") == "PartA"]
    assert relationship_rows
    assert relationship_rows[0]["properties"]["reference_key"] == "partRef"
    assert result["relationships_created"] >= 1


def test_xml_family_detector_prefers_specialized_plmxml_and_3dxml():
    plmxml = b'<?xml version="1.0"?><PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" />'
    threedxml = b'<?xml version="1.0"?><VPMRepReference xmlns="http://www.3ds.com/xsd/3DXML" />'

    assert _detect_xml_family(plmxml) == "plmxml"
    assert _detect_xml_family(threedxml) == "3dxml"


def test_fileparser_dispatches_xml_family_content_to_specialized_parsers(monkeypatch):
    called = {"plmxml": 0, "3dxml": 0}

    def fake_plmxml(*_args, **_kwargs):
        called["plmxml"] += 1
        return [{"id": "P1"}], {"format": "PLMXML"}

    def fake_3dxml(*_args, **_kwargs):
        called["3dxml"] += 1
        return [{"id": "D1"}], {"format": "3DXML"}

    monkeypatch.setattr(FileParser, "_parse_plmxml", staticmethod(fake_plmxml))
    monkeypatch.setattr(FileParser, "_parse_threedxml", staticmethod(fake_3dxml))

    rows_plmxml, stats_plmxml = FileParser.parse(
        b'<?xml version="1.0"?><PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" />',
        FileType.XML,
    )
    rows_3dxml, stats_3dxml = FileParser.parse(
        b'<?xml version="1.0"?><VPMRepReference xmlns="http://www.3ds.com/xsd/3DXML" />',
        FileType.XML,
    )

    assert rows_plmxml == [{"id": "P1"}]
    assert rows_3dxml == [{"id": "D1"}]
    assert stats_plmxml["format"] == "PLMXML"
    assert stats_3dxml["format"] == "3DXML"
    assert called["plmxml"] == 1
    assert called["3dxml"] == 1


def test_fileparser_explicit_threedxml_type_uses_dedicated_parser(monkeypatch):
    called = {"3dxml": 0}

    def fake_3dxml(*_args, **_kwargs):
        called["3dxml"] += 1
        return [{"id": "D1"}], {"format": "3DXML"}

    monkeypatch.setattr(FileParser, "_parse_threedxml", staticmethod(fake_3dxml))

    rows, stats = FileParser.parse(b"<root />", FileType.THREEDXML)

    assert rows == [{"id": "D1"}]
    assert stats["format"] == "3DXML"
    assert called["3dxml"] == 1
