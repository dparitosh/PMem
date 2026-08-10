from pathlib import Path

from backend.Services.express_parser import parse_express


def test_express_parser_keeps_named_unique_constraints(tmp_path: Path):
    express = """
SCHEMA demo_schema;

ENTITY Part;
  part_id : STRING;
UNIQUE
  unique_part_id : part_id;
END_ENTITY;

END_SCHEMA;
"""
    path = tmp_path / "demo.exp"
    path.write_text(express, encoding="utf-8")

    schema = parse_express(path)

    part = schema.entities["Part"]
    assert len(part.unique_constraints) == 1
    assert part.unique_constraints[0].name == "unique_part_id"
    assert part.unique_constraints[0].attributes == ["part_id"]


def test_express_parser_keeps_aggregate_aliases_without_bounds(tmp_path: Path):
    express = """
SCHEMA demo_schema;

TYPE PartSet = SET OF Part;
END_TYPE;

ENTITY Part;
  part_id : STRING;
END_ENTITY;

END_SCHEMA;
"""
    path = tmp_path / "aggregate_alias.exp"
    path.write_text(express, encoding="utf-8")

    schema = parse_express(path)

    assert schema.type_aliases["PartSet"] == "Part"
