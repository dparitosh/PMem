from backend.Services.unified_data_import import FileFormatDetector, DataTransformer


def test_recommended_indexes_include_composite_import_and_text_name():
    indexes = FileFormatDetector._recommended_indexes_for_label(
        "Part",
        "id",
        ["id", "import_id", "import_row_key", "name", "ontology_prefix", "part_ref"],
    )

    signatures = {(idx["type"], tuple(idx["properties"])) for idx in indexes}

    assert ("range", ("import_id", "import_row_key")) in signatures
    assert ("range", ("import_row_key",)) in signatures
    assert ("range", ("import_id", "id")) in signatures
    assert ("range", ("id",)) in signatures
    assert ("text", ("name",)) in signatures
    assert ("range", ("ontology_prefix",)) in signatures
    assert ("range", ("part_ref",)) in signatures


def test_auto_detect_schema_uses_recommended_indexes_for_heterogeneous_rows():
    rows = [
        {"element_type": "Part", "id": "P1", "import_id": "imp-1", "import_row_key": "P1", "name": "Rotor"},
        {"element_type": "Part", "id": "P2", "import_id": "imp-1", "import_row_key": "P2", "name": "Stator"},
    ]

    schema = DataTransformer.auto_detect_schema(rows)

    assert schema["indexes"]
    assert any(idx["properties"] == ["import_id", "import_row_key"] for idx in schema["indexes"])
    assert any(idx["properties"] == ["import_row_key"] for idx in schema["indexes"])
    assert any(idx["type"] == "text" and idx["properties"] == ["name"] for idx in schema["indexes"])
