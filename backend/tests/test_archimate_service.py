from backend.Services.archimate_service import (
    looks_like_archimate_xml,
    parse_archimate_model_exchange,
)
from backend.Services.unified_data_import import FileParser, FileType, _detect_xml_family


ARCHIMATE_31_SAMPLE = b"""<?xml version="1.0"?>
<model xmlns="https://www.opengroup.org//xsd/archimate/3.1/"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       identifier="m1">
  <name>Process Reference Model</name>
  <propertyDefinitions>
    <propertyDefinition identifier="pd1"><name>Owner</name></propertyDefinition>
  </propertyDefinitions>
  <elements>
    <element identifier="bp1" xsi:type="BusinessProcess">
      <name>Order Fulfillment</name>
      <properties><property propertyDefinitionRef="pd1"><value>Operations</value></property></properties>
    </element>
    <element identifier="app1" xsi:type="ApplicationService">
      <name>ERP Service</name>
    </element>
  </elements>
  <relationships>
    <relationship identifier="r1" xsi:type="ServingRelationship" source="app1" target="bp1" />
  </relationships>
  <views>
    <diagrams>
      <view identifier="v1">
        <name>Process View</name>
        <node identifier="n1" elementRef="bp1" />
        <connection identifier="c1" relationshipRef="r1" />
      </view>
    </diagrams>
  </views>
</model>
"""


def test_archimate_31_model_exchange_parser_preserves_semantics():
    assert looks_like_archimate_xml(ARCHIMATE_31_SAMPLE)
    assert _detect_xml_family(ARCHIMATE_31_SAMPLE) == "archimate"

    rows, stats = FileParser.parse(ARCHIMATE_31_SAMPLE, FileType.XML)

    assert stats["namespace"] == "https://www.opengroup.org//xsd/archimate/3.1/"
    assert stats["model_identifier"] == "m1"
    assert stats["model_name"] == "Process Reference Model"
    assert stats["element_count"] == 2
    assert stats["relationship_count"] == 1
    assert stats["view_count"] == 1
    assert stats["view_reference_count"] == 2
    assert stats["property_definition_count"] == 1
    assert stats["unresolved_relationship_count"] == 0

    business_process = next(row for row in rows if row["id"] == "bp1")
    assert business_process["element_type"] == "BusinessProcess"
    assert business_process["property_owner"] == "Operations"

    rel = stats["_xmi_relationships"][0]
    assert rel["type"] == "SERVING"
    assert rel["from_props"] == {"id": "app1"}
    assert rel["to_props"] == {"id": "bp1"}


def test_archimate_parser_reports_unresolved_relationship_endpoints():
    sample = ARCHIMATE_31_SAMPLE.replace(b'target="bp1"', b'target="missing"')

    rows, stats = parse_archimate_model_exchange(sample)

    assert len(rows) == 2
    assert stats["relationship_count"] == 0
    assert stats["unresolved_relationship_count"] == 1
    assert stats["unresolved_relationships"][0]["target"] == "missing"

