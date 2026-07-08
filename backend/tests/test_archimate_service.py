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


ARCHI_TOOL_FOLDER_SAMPLE = b"""<?xml version="1.0"?>
<archimate:model xmlns:archimate="http://www.archimatetool.com/archimate"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 id="model-1">
  <name>Foldered Model</name>
  <folder name="Business" type="business">
    <element id="e1" xsi:type="BusinessActor" name="Customer" />
    <folder name="Processes" type="business-processes">
      <element id="e2" xsi:type="BusinessProcess" name="Approve Order" />
    </folder>
  </folder>
  <folder name="Views" type="diagrams">
    <element id="v1" xsi:type="archimate:DiagramModel" name="Business View">
      <child archimateElement="e1" />
    </element>
  </folder>
  <element id="r1" xsi:type="ServingRelationship" source="e1" target="e2" />
</archimate:model>
"""


def test_archimate_31_model_exchange_parser_preserves_semantics():
    assert looks_like_archimate_xml(ARCHIMATE_31_SAMPLE)
    assert _detect_xml_family(ARCHIMATE_31_SAMPLE) == "archimate"

    rows, stats = FileParser.parse(ARCHIMATE_31_SAMPLE, FileType.XML)

    assert stats["namespace"] == "https://www.opengroup.org//xsd/archimate/3.1/"
    assert stats["model_identifier"] == "m1"
    assert stats["model_name"] == "Process Reference Model"
    assert stats["element_count"] == 3
    assert stats["relationship_count"] == 2
    assert stats["view_count"] == 1
    assert stats["view_reference_count"] == 2
    assert stats["view_containment_count"] == 1
    assert stats["property_definition_count"] == 1
    assert stats["unresolved_relationship_count"] == 0

    business_process = next(row for row in rows if row["id"] == "bp1")
    assert business_process["element_type"] == "BusinessProcess"
    assert business_process["property_owner"] == "Operations"

    rel = next(item for item in stats["_xmi_relationships"] if item["type"] == "SERVING")
    assert rel["from_props"] == {"id": "app1"}
    assert rel["to_props"] == {"id": "bp1"}


def test_archimate_parser_reports_unresolved_relationship_endpoints():
    sample = ARCHIMATE_31_SAMPLE.replace(b'target="bp1"', b'target="missing"')

    rows, stats = parse_archimate_model_exchange(sample)

    assert len(rows) == 3
    assert stats["relationship_count"] == 1
    assert stats["unresolved_relationship_count"] == 1
    assert any(rel["type"] == "VIEW_CONTAINS" for rel in stats["_xmi_relationships"])
    assert stats["unresolved_relationships"][0]["target"] == "missing"


def test_archimate_parser_preserves_archi_folder_nodes_and_names():
    assert looks_like_archimate_xml(ARCHI_TOOL_FOLDER_SAMPLE)

    rows, stats = parse_archimate_model_exchange(ARCHI_TOOL_FOLDER_SAMPLE)

    names = {row["name"] for row in rows}
    assert {"Business", "Processes", "Views", "Customer", "Approve Order", "Business View"}.issubset(names)
    folders = [row for row in rows if row.get("semantic_role") == "folder"]
    assert len(folders) == 3
    assert stats["folder_count"] == 3
    assert stats["folder_containment_count"] >= 3
    assert any(rel["type"] == "CONTAINS" for rel in stats["_xmi_relationships"])
    assert any(rel["type"] == "VIEW_CONTAINS" for rel in stats["_xmi_relationships"])