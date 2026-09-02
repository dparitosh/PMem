import pytest

from backend.ingestion_service.xsd_validation import inspect_xsd_structure


def test_xsd_structure_reports_scope_without_claiming_conformance():
    report = inspect_xsd_structure(b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:example">
      <xs:import namespace="urn:shared" schemaLocation="shared.xsd"/>
    </xs:schema>''')

    assert report["status"] == "structurally_valid"
    assert report["target_namespace"] == "urn:example"
    assert report["dependencies"][0]["schema_location"] == "shared.xsd"
    assert report["formal_xsd_instance_validation"] == "not_performed"


@pytest.mark.parametrize("source", [
    b"<!DOCTYPE schema><xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'/>",
    b"<root/>",
])
def test_xsd_structure_rejects_unsafe_or_non_schema_input(source):
    with pytest.raises(ValueError):
        inspect_xsd_structure(source)


def test_xsd_conversion_emits_rdfxml_only_when_explicitly_requested(tmp_path):
    from backend.Services.owl_xsd_engine import minimal_config, convert_xsd_to_owl

    (tmp_path / "sample.xsd").write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<xs:complexType name="Part"><xs:sequence><xs:element name="id" type="xs:string"/>'
        '</xs:sequence></xs:complexType></xs:schema>',
        encoding="utf-8",
    )
    ttl_path = tmp_path / "sample.ttl"
    config = minimal_config(base_uri="urn:test#", prefix="test", title="Test", schema_dir=str(tmp_path), output_ttl=str(ttl_path))
    convert_xsd_to_owl(config)

    assert ttl_path.is_file()
    assert not ttl_path.with_suffix(".owl").exists()


def test_xsd_conversion_rejects_concurrent_work(monkeypatch):
    from backend.ingestion_service.schema_conversion import EngineeringSchemaConverter, _XSD_CONVERSION_LOCK

    assert _XSD_CONVERSION_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ValueError, match="conversion is running"):
            EngineeringSchemaConverter().convert(
                filename="sample.xsd",
                content=b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>',
            )
    finally:
        _XSD_CONVERSION_LOCK.release()
