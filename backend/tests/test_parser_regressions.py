"""Regression pins for parser bug fixes (tabular, OWL/CSV, XSD, STEP, EXPRESS,
PLMXML, AP239, ReqIF, XML analytics, 3DXML, recommendation resolution).

Each test exercises a public or module-level entry point with a small,
self-contained input so that the fixed behaviour cannot silently regress.
"""
import io
import time
import zipfile
from unittest.mock import patch

import pytest
from fastapi import HTTPException


# 1. tabular CSV: duplicate headers and overflowing rows ---------------------

def test_tabular_csv_duplicate_headers_raise():
    from backend.ingestion_service.tabular import load_table
    with pytest.raises(ValueError, match="duplicate column names"):
        load_table(b"name,name\n1,2\n", "parts.csv")


def test_tabular_csv_row_with_extra_nonempty_cell_raises():
    from backend.ingestion_service.tabular import load_table
    with pytest.raises(ValueError, match="more cells than the header"):
        load_table(b"a,b\n1,2,3\n", "parts.csv")


def test_tabular_csv_trailing_empty_cells_are_accepted():
    from backend.ingestion_service.tabular import load_table
    rows = load_table(b"a,b\n1,2,,\n", "parts.csv")
    assert rows == [{"a": "1", "b": "2"}]


# 2. OWL/CSV engine: duplicate headers ---------------------------------------

def test_owl_csv_conversion_rejects_duplicate_headers(tmp_path):
    from backend.Services.owl_csv_engine import convert_csv_to_ttl
    src = tmp_path / "dup.csv"
    src.write_text("id,id\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        convert_csv_to_ttl(str(src), str(tmp_path / "out.ttl"))
    assert not (tmp_path / "out.ttl").exists()


# 3. XSD attribute-group expansion budget ------------------------------------

def test_xsd_attribute_group_dag_expansion_is_budgeted(tmp_path):
    from backend.Services.xsd_semantics import expand_model_groups
    # g0..g{N-1} each reference g{i+1} twice (group-only, no leaf attributes).
    # Expansion visits ~2^N nodes; the 1,000,000-visit budget must trip well before that.
    depth = 21
    xsd = ['<?xml version="1.0"?>',
           '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
           'xmlns:t="urn:budget" targetNamespace="urn:budget" elementFormDefault="qualified">']
    for i in range(depth):
        xsd.append(f'<xs:attributeGroup name="g{i}">'
                   f'<xs:attributeGroup ref="t:g{i + 1}"/><xs:attributeGroup ref="t:g{i + 1}"/>'
                   '</xs:attributeGroup>')
    xsd.append(f'<xs:attributeGroup name="g{depth}"/>')
    xsd.append('<xs:element name="root"><xs:complexType>'
               '<xs:attributeGroup ref="t:g0"/></xs:complexType></xs:element>')
    xsd.append('</xs:schema>')
    path = tmp_path / "budget.xsd"
    path.write_text("".join(xsd), encoding="utf-8")
    started = time.perf_counter()
    with pytest.raises(ValueError, match="complexity limit"):
        expand_model_groups([path])
    assert time.perf_counter() - started < 10


# 4. STEP parser -------------------------------------------------------------

def test_step_unterminated_comment_is_fast_and_keeps_prefix():
    from backend.Services.step_parser import _strip_step_comments
    prefix = "#1=CARTESIAN_POINT('p',(0.,0.,0.));\n"
    text = prefix + "/*" + ("x" * 50000)
    started = time.perf_counter()
    result = _strip_step_comments(text)
    assert time.perf_counter() - started < 2.0
    assert result.startswith(prefix)
    assert result[len(prefix):].strip() == ""


def test_step_deep_measure_reference_chain_raises_value_error():
    from backend.Services.step_parser import StepP21Entity, _measure_number
    count = 1500
    entity_map = {
        i: StepP21Entity(step_id=i, entity_type="LENGTH_MEASURE", raw_args=f"#{i + 1}", ref_ids=[i + 1])
        for i in range(1, count)
    }
    entity_map[count] = StepP21Entity(step_id=count, entity_type="LENGTH_MEASURE", raw_args="", ref_ids=[])
    with pytest.raises(ValueError, match="too deep"):
        _measure_number(entity_map[1], entity_map)


def test_step_non_entity_record_in_data_section_raises_value_error():
    from backend.Services.step_parser import _extract_part21_data_records
    text = (
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
        "#1=CARTESIAN_POINT('p',(0.,0.,0.));\n"
        "JUNK_RECORD;\n"
        "ENDSEC;\nEND-ISO-10303-21;\n"
    )
    with pytest.raises(ValueError, match="Malformed STEP record in DATA section"):
        _extract_part21_data_records(text)


# 5. EXPRESS parser ----------------------------------------------------------

def test_express_unterminated_block_comment_is_fast_and_keeps_prefix():
    from backend.Services.express_parser import _strip_comments
    text = "ENTITY keep_me;\n(* open " + ("x" * 50000)
    started = time.perf_counter()
    result = _strip_comments(text)
    assert time.perf_counter() - started < 2.0
    assert "ENTITY keep_me;" in result
    assert "open" not in result


def test_express_two_unique_rules_are_both_kept():
    from backend.Services.express_parser import _parse_entity_block
    body = "  a : INTEGER;\n  b : STRING;\nUNIQUE\n  UR1: a;\n  UR2: b;\n"
    entity = _parse_entity_block("thing", body)
    assert [(u.name, u.attributes) for u in entity.unique_constraints] == [("UR1", ["a"]), ("UR2", ["b"])]


def test_express_bounded_simple_type_attribute_is_kept():
    from backend.Services.express_parser import _parse_entity_block
    entity = _parse_entity_block("thing", "  label : STRING(255);\n")
    names = [(attr.name, attr.type_ref) for attr in entity.attributes]
    assert ("label", "STRING") in names


def test_express_wrapped_aggregate_attribute_is_kept():
    from backend.Services.express_parser import _parse_entity_block
    entity = _parse_entity_block("thing", "  tags : SET [1:?] OF\n    INTEGER;\n")
    tags = [attr for attr in entity.attributes if attr.name == "tags"]
    assert len(tags) == 1
    assert tags[0].type_ref == "INTEGER"
    assert tags[0].is_aggregate is True
    assert tags[0].min_cardinality == 1


# 6. PLMXML parser -----------------------------------------------------------

@pytest.mark.parametrize("raw", ["inf", "1e400"])
def test_plmxml_non_finite_quantity_falls_back_to_one(raw):
    from backend.Services.plmxml_parser import _parse_quantity
    assert _parse_quantity({"quantity": raw}) == 1


def test_plmxml_product_instance_keeps_id_and_name_before_unrelated_sibling(tmp_path):
    from backend.Services.plmxml_parser import parse_plmxml_file
    xml = (
        '<?xml version="1.0"?>\n'
        '<PLMXML schemaVersion="6">\n'
        '  <ProductInstance id="PI1">\n'
        '    <ID>PI-1</ID>\n'
        '    <Name>Motor Assembly</Name>\n'
        '    <Unrelated>noise</Unrelated>\n'
        '  </ProductInstance>\n'
        '</PLMXML>\n'
    )
    path = tmp_path / "instances.plmxml"
    path.write_text(xml, encoding="utf-8")
    doc = parse_plmxml_file(path)
    assert len(doc.product_instances) == 1
    instance = doc.product_instances[0]
    assert instance.id == "PI1"
    assert instance.name == "Motor Assembly"
    assert instance.properties.get("ID") == "PI-1"


def test_plmxml_external_entity_does_not_expose_local_file(tmp_path):
    from backend.Services.plmxml_parser import parse_plmxml_file
    sentinel = "PMEM-SENTINEL-7f3a9c"
    secret = tmp_path / "secret.txt"
    secret.write_text(sentinel, encoding="utf-8")
    xml = (
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE PLMXML [<!ENTITY x SYSTEM "{secret.as_uri()}">]>\n'
        '<PLMXML schemaVersion="6">\n'
        '  <Product id="P1" name="&x;"/>\n'
        '</PLMXML>\n'
    )
    path = tmp_path / "xxe.plmxml"
    path.write_text(xml, encoding="utf-8")
    try:
        doc = parse_plmxml_file(path)
    except Exception:
        # Refusing the DTD outright is also acceptable; the local file must not leak.
        return
    assert sentinel not in repr(doc)


# 7. AP239 XMI parser -------------------------------------------------------

def test_ap239_xmi_with_comment_and_uml_class_is_parsed(tmp_path):
    from backend.Services.ap239_parser import parse_ap239_xmi
    xmi = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xmi:XMI xmlns:xmi="http://www.omg.org/spec/XMI/20131001" '
        'xmlns:uml="http://www.omg.org/spec/UML/20131001">\n'
        '  <!-- exported by a modelling tool -->\n'
        '  <uml:Model xmi:id="m1" name="Model">\n'
        '    <uml:Class xmi:id="c1" name="Part"/>\n'
        '  </uml:Model>\n'
        '</xmi:XMI>\n'
    )
    path = tmp_path / "model.xmi"
    path.write_text(xmi, encoding="utf-8")
    model = parse_ap239_xmi(path)
    assert "c1" in model.parts
    assert model.parts["c1"].name == "Part"


# 8. ReqIF zip handling -----------------------------------------------------

def _single_member_zip(payload: bytes) -> bytearray:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("spec.reqif", payload)
    return bytearray(buffer.getvalue())


def test_reqif_zip_with_bad_crc_raises_value_error():
    from backend.Services.reqif_source import reqif_xml
    payload = b"<REQ-IF>0123456789</REQ-IF>"
    data = _single_member_zip(payload)
    # Corrupt one byte of the stored member body; CRC check then fails on read.
    offset = data.index(b"0123456789")
    data[offset] = ord("9")
    with pytest.raises(ValueError, match="could not be read"):
        reqif_xml(bytes(data))


def test_reqif_zip_with_encrypted_member_raises_value_error():
    from backend.Services.reqif_source import reqif_xml
    data = _single_member_zip(b"<REQ-IF/>")
    # Set the encryption bit in the local header (offset 6) and central directory (offset 8).
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    data[local + 6] |= 0x01
    data[central + 8] |= 0x01
    with pytest.raises(ValueError):
        reqif_xml(bytes(data))


# 9. XML analytics scalar values --------------------------------------------

def test_xml_analytics_scalar_with_comment_is_not_truncated():
    from lxml import etree
    from backend.data_pipeline_service.xml_analytics import flatten_xml
    model = {
        "tables": [{
            "entity_id": "E_root",
            "source_kind": "scalar root",
            "columns": [{"name": "value", "source_kind": "text"}],
            "relationships": [],
        }],
        "roots": [{"source_qname": "a", "entity_id": "E_root"}],
    }
    document = etree.fromstring("<a>Part <!-- note --> A</a>")
    rows, _links = flatten_xml(model, document)
    assert rows[0][1] == ["Part  A"]


# 10. 3DXML summarize -------------------------------------------------------

def test_threedxml_summarize_without_entities_raises_value_error():
    from backend.Services.threedxml_import_service import ThreeDXMLImportService
    with pytest.raises(ValueError, match="No 3DXML entities"):
        ThreeDXMLImportService.summarize("broken.3dxml", b"this is not xml at all")


# 11. Recommendation object resolution with unhashable analysis -------------

@pytest.fixture
def _router_isolated():
    from backend.graph_service import context_router as api
    with patch.object(api.publisher, "search", side_effect=AssertionError("publisher must not be queried")):
        yield api


def test_recommendation_list_analysis_is_rejected_with_422(_router_isolated):
    api = _router_isolated
    with pytest.raises(HTTPException) as caught:
        api.resolve_recommendation_object({"part_name": "Motor", "analysis": ["similar-parts"]})
    assert caught.value.status_code == 422


def test_truncated_plmxml_is_rejected_not_imported_silently(tmp_path):
    from backend.Services.plmxml_parser import parse_plmxml_file
    path = tmp_path / "truncated.plmxml"
    path.write_bytes(b'<?xml version="1.0"?><PLM><Part id="p1"/><Part id="p3')
    with pytest.raises(ValueError, match="malformed or truncated"):
        parse_plmxml_file(path)


def test_same_named_local_xsd_elements_do_not_overwrite_each_other():
    from backend.Services.specialized_format_parser import SpecializedFormatParser
    xsd = b'''<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:t">
  <xs:element name="code" type="xs:string"/>
  <xs:complexType name="A"><xs:sequence><xs:element name="code" type="xs:int"/></xs:sequence></xs:complexType>
  <xs:complexType name="B"><xs:sequence><xs:element name="code" type="xs:date"/></xs:sequence></xs:complexType>
</xs:schema>'''
    rows, _ = SpecializedFormatParser.parse_xsd(xsd)
    types = {row["name"]: row.get("type") for row in rows if row.get("kind") == "element"}
    assert types == {"code": "xs:string", "A/code": "xs:int", "B/code": "xs:date"}


def test_stpx_part_display_name_comes_from_file_name_element(tmp_path):
    from backend.Services.step_parser import parse_step_with_pmi
    path = tmp_path / "named.stpx"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Uos xmlns="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model">\n'
        '  <Part uid="part-9" id="Scoped">\n'
        '    <Name>Motor Assembly</Name>\n'
        '  </Part>\n'
        '</Uos>\n',
        encoding="utf-8",
    )
    doc = parse_step_with_pmi(path)
    parts = [item for item in doc.cad_products if item.entity_type == "PART"]
    assert [(p.external_id, p.name) for p in parts] == [("part-9", "Motor Assembly")]


def test_two_unnamed_csv_columns_are_rejected_but_one_is_allowed():
    from backend.ingestion_service.tabular import load_table
    with pytest.raises(ValueError, match="unnamed column"):
        load_table(b"a,,\n1,2,3\n", "parts.csv")
    rows = load_table(b"a,\n1,2\n", "parts.csv")
    assert rows[0]["a"] == "1"


def test_csv_headers_colliding_after_normalization_are_rejected(tmp_path):
    from backend.Services.owl_csv_engine import convert_csv_to_ttl
    src = tmp_path / "parts.csv"
    src.write_text("a b,a_b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="collide after name normalization"):
        convert_csv_to_ttl(str(src), str(tmp_path / "out.ttl"))


def test_plmxml_parse_is_lossless_for_child_data_and_metadata(tmp_path):
    from backend.Services.plmxml_parser import parse_plmxml_file
    path = tmp_path / "lossless.plmxml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE PLMXML [<!ENTITY site "Plant-7">]>\n'
        '<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" time="09:10:11" language="en-us" schemaVersion="6">\n'
        '  <ProductInstance id="pi1" name="&site;">\n'
        '    <ID>PI-1</ID>\n'
        '    <Transform>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</Transform>\n'
        '    <ApplicationRef application="Teamcenter" label="LABEL-42" version="V-7"/>\n'
        '    <UserData id="ud1">\n'
        '      <UserValue title="BOM_precision_type" value="imprecise" type="real"/>\n'
        '    </UserData>\n'
        '  </ProductInstance>\n'
        '</PLMXML>\n',
        encoding="utf-8",
    )
    doc = parse_plmxml_file(path)
    # Internal entity is expanded, not dropped.
    assert any(getattr(item, "name", "") == "Plant-7" for item in doc.product_instances)
    # Child element text the streaming parser used to discard is kept.
    assert any("1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1" in repr(item) for item in doc.product_instances)
    # ApplicationRef label/version and UserValue type are retained with their owner.
    assert any(ref["label"] == "LABEL-42" and ref["version"] == "V-7" and ref["owner_id"] == "pi1"
               for ref in doc.application_refs)
    assert any(value["type"] == "real" and value["value"] == "imprecise" for value in doc.user_values)
    # Root metadata is kept.
    assert doc.root_attributes["time"] == "09:10:11"
    assert doc.root_attributes["language"] == "en-us"


_LOSSLESS_SAMPLE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" time="09:10:11" language="en-us" schemaVersion="6">\n'
    '  <ProductInstance id="pi1" name="Motor">\n'
    '    <ID>PI-1</ID>\n'
    '    <ApplicationRef application="Teamcenter" label="LABEL-42" version="V-7"/>\n'
    '    <UserData id="ud1"><UserValue title="BOM_precision_type" value="imprecise" type="real"/>'
    '<UserValue title="Mass Rank" value="7" type="int"/></UserData>\n'
    '  </ProductInstance>\n'
    '</PLMXML>\n'
)


def test_lossless_plmxml_fields_reach_import_entities(tmp_path):
    from backend.Services.data_import_service import DataImportService
    path = tmp_path / "lossless.plmxml"
    path.write_text(_LOSSLESS_SAMPLE, encoding="utf-8")
    parsed = DataImportService._parse_plmxml(str(path))
    instance = next(e for e in parsed["entities"] if e["type"] == "ProductInstance")
    assert instance["attributes"]["external_label"] == "LABEL-42"
    assert instance["attributes"]["external_version"] == "V-7"
    assert instance["attributes"]["BOM_precision_type"] == "imprecise"
    assert instance["attributes"]["BOM_precision_type_type"] == "real"
    assert parsed["root_attributes"]["time"] == "09:10:11"


def test_lossless_plmxml_fields_reach_ttl_output(tmp_path):
    from backend.Services.owl_plmxml_engine import convert_plmxml_file_to_ttl
    path = tmp_path / "lossless.plmxml"
    path.write_text(_LOSSLESS_SAMPLE, encoding="utf-8")
    out = convert_plmxml_file_to_ttl(path, tmp_path / "out")
    ttl = out.read_text(encoding="utf-8")
    assert "LABEL-42" in ttl
    assert "imprecise" in ttl
    assert "09:10:11" in ttl
    # Business attributes are real RDF predicates; numeric types keep their XSD datatype.
    # Turtle writes xsd:integer literals as bare numbers.
    assert "plmxml:Mass_Rank 7" in ttl
    assert 'plmxml:external_label "LABEL-42"' in ttl


def test_lossless_plmxml_fields_reach_csv_rows(tmp_path):
    from backend.Services.plmxml_parser import parse_plmxml_file
    from backend.Services.owl_plmxml_engine import _doc_to_csv_rows
    path = tmp_path / "lossless.plmxml"
    path.write_text(_LOSSLESS_SAMPLE, encoding="utf-8")
    rows = _doc_to_csv_rows(parse_plmxml_file(path), path)
    labels = [r["name"] for r in rows if r["entity_type"] == "ApplicationRef"]
    values = [r["description"] for r in rows if r["entity_type"] == "UserValue"]
    roots = [r["raw_attributes"] for r in rows if r["entity_type"] == "PLMXMLFile"]
    assert labels == ["LABEL-42"]
    assert values == ["imprecise", "7"]
    assert '"time":"09:10:11"' in roots[0]
