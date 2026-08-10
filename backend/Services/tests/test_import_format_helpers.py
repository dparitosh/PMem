from backend.Services.import_format_helpers import (
    derive_prefix_from_namespace,
    detect_xml_family,
    plmxml_row_has_payload,
)


def test_derive_prefix_from_namespace_uses_known_patterns_and_fallbacks():
    assert derive_prefix_from_namespace("http://www.plmxml.org/Schemas/PLMXMLSchema") == "plmxml"
    assert derive_prefix_from_namespace("http://www.omg.org/XMI") == "xmi"
    assert derive_prefix_from_namespace("http://example.com/ns/custom-domain") == "customdomain"


def test_detect_xml_family_identifies_reqif_and_plmxml():
    reqif = b"<REQ-IF xmlns='http://www.omg.org/spec/ReqIF/20110401/reqif.xsd'></REQ-IF>"
    plmxml = b"<PLMXML xmlns='http://www.plmxml.org/Schemas/PLMXMLSchema'></PLMXML>"
    generic = b"<root><item /></root>"

    assert detect_xml_family(reqif) == "reqif"
    assert detect_xml_family(plmxml) == "plmxml"
    assert detect_xml_family(generic) == "xml"


def test_plmxml_row_has_payload_filters_structural_rows_but_keeps_descriptive_entities():
    metadata_only = {
        "id": "row-1",
        "name": "Part",
        "description": "Description only",
        "ontology_prefix": "plmxml",
        "source_ontology": "http://www.plmxml.org/Schemas/PLMXMLSchema",
    }
    row_with_payload = {
        **metadata_only,
        "mass": "12.5",
    }

    assert plmxml_row_has_payload(metadata_only, "Description") is False
    assert plmxml_row_has_payload(metadata_only, "Product") is True
    assert plmxml_row_has_payload(row_with_payload, "Product") is True
