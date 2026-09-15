from pathlib import Path

from backend.qif.ontology_builder import inspect_schema_set, validate_schema_set


def test_all_bundled_qif_schemas_compile_without_network():
    root = Path(__file__).resolve().parents[2] / "docs" / "xsd"
    paths = list(root.rglob("*.xsd"))
    assert len(list((root / "QIFApplications").glob("*.xsd"))) == 7
    result = validate_schema_set(inspect_schema_set(paths), paths)
    assert result["xsd_grammar_compiler"] == "lxml/libxml2"
    assert result["valid"], result["errors"]


def test_attribute_cardinality_respects_use(tmp_path):
    schema = tmp_path / "attributes.xsd"
    schema.write_text('''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:complexType name="Part">
        <xs:attribute name="optional" type="xs:string"/>
        <xs:attribute name="required" type="xs:string" use="required"/>
        <xs:attribute name="forbidden" type="xs:string" use="prohibited"/>
      </xs:complexType>
    </xs:schema>''', encoding="utf-8")
    terms = {t.name: t for t in inspect_schema_set([schema])["terms"]}
    assert (terms["optional"].min_occurs, terms["optional"].max_occurs) == ("0", "1")
    assert (terms["required"].min_occurs, terms["required"].max_occurs) == ("1", "1")
    assert (terms["forbidden"].min_occurs, terms["forbidden"].max_occurs) == ("0", "0")
