from backend.Services.unified_data_import import FileFormatDetector, FileParser, FileType


def test_reqif_extension_is_supported_by_import_detector():
    assert FileFormatDetector.detect("requirements.reqif") == FileType.REQIF
    assert FileFormatDetector.detect("requirements.reqifz") == FileType.REQIF
    assert ".reqif" in FileFormatDetector.get_supported_formats()
    assert ".reqifz" in FileFormatDetector.get_supported_formats()


def test_reqif_parser_extracts_requirements_specifications_and_relations():
    content = b"""<?xml version='1.0' encoding='UTF-8'?>
    <REQ-IF xmlns='http://www.omg.org/spec/ReqIF/20110401/reqif.xsd'>
      <CORE-CONTENT>
        <REQ-IF-CONTENT>
          <SPEC-OBJECTS>
            <SPEC-OBJECT IDENTIFIER='REQ-001' LONG-NAME='Bearing life requirement'>
              <DESC>Bearing life shall exceed target hours.</DESC>
              <VALUES>
                <ATTRIBUTE-VALUE-STRING THE-VALUE='40k hours'>
                  <DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>LifeTarget</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION>
                </ATTRIBUTE-VALUE-STRING>
              </VALUES>
              <TYPE><SPEC-OBJECT-TYPE-REF>RequirementType</SPEC-OBJECT-TYPE-REF></TYPE>
            </SPEC-OBJECT>
          </SPEC-OBJECTS>
          <SPECIFICATIONS>
            <SPECIFICATION IDENTIFIER='SPEC-001' LONG-NAME='Motor specification' />
          </SPECIFICATIONS>
          <SPEC-RELATIONS>
            <SPEC-RELATION IDENTIFIER='REL-001' LONG-NAME='satisfies'>
              <SOURCE><SPEC-OBJECT-REF>REQ-001</SPEC-OBJECT-REF></SOURCE>
              <TARGET><SPEC-OBJECT-REF>REQ-002</SPEC-OBJECT-REF></TARGET>
            </SPEC-RELATION>
          </SPEC-RELATIONS>
        </REQ-IF-CONTENT>
      </CORE-CONTENT>
    </REQ-IF>
    """

    rows, stats = FileParser.parse(content, FileType.REQIF)

    assert stats["file_format"] == "ReqIF"
    assert stats["target_reqif_version"] == "1.2"
    assert stats["requirements"] == 1
    assert stats["specifications"] == 1
    assert stats["relations"] == 1
    assert {row["entity_type"] for row in rows} == {"Requirement", "Specification", "RequirementRelation"}
    by_role = {row["row_type"]: row for row in rows}
    assert by_role["requirement"]["id"] == "REQ-001"
    assert by_role["requirement"]["source_format"] == "reqif"
    assert by_role["requirement"]["type_ref"] == "RequirementType"
    assert by_role["requirement"]["attribute_count"] == 1
    assert by_role["requirement"]["attributes"][0]["definition"] == "LifeTarget"
    assert by_role["requirement"]["attributes"][0]["value"] == "40k hours"
    assert by_role["relation"]["source_ref"] == "REQ-001"
    assert by_role["relation"]["target_ref"] == "REQ-002"


def test_reqif_parser_sniffs_reqif_xml_and_tracks_duplicate_ids():
    content = b"""<?xml version='1.0' encoding='UTF-8'?>
    <REQ-IF xmlns='http://www.omg.org/spec/ReqIF/20110401/reqif.xsd'>
      <CORE-CONTENT><REQ-IF-CONTENT><SPEC-OBJECTS>
        <SPEC-OBJECT IDENTIFIER='REQ-001' LONG-NAME='First' />
        <SPEC-OBJECT IDENTIFIER='REQ-001' LONG-NAME='Second' />
      </SPEC-OBJECTS></REQ-IF-CONTENT></CORE-CONTENT>
    </REQ-IF>
    """

    rows, stats = FileParser.parse(content, FileType.XML)

    assert stats["file_format"] == "ReqIF"
    assert stats["requirements"] == 2
    assert stats["duplicate_ids"] == 1
    assert [row["id"] for row in rows] == ["REQ-001", "REQ-001#2"]
    assert [row["original_id"] for row in rows] == ["REQ-001", "REQ-001"]
