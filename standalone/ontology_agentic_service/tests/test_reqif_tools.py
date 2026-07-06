from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from ontology_agentic.tools.reqif_tools import inspect_reqif_file, export_reqif_to_ttl


def test_reqif_inspect_and_export(tmp_path) -> None:
    reqif = '<?xml version="1.0" encoding="UTF-8"?>\n<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd">\n  <CORE-CONTENT>\n    <REQ-IF-CONTENT>\n      <SPEC-OBJECTS>\n        <SPEC-OBJECT IDENTIFIER="REQ-001" LONG-NAME="Bearing life requirement">\n          <VALUES>\n            <ATTRIBUTE-VALUE-STRING THE-VALUE="Bearing shall meet 20000 hour life">\n              <DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>AD-1</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION>\n            </ATTRIBUTE-VALUE-STRING>\n          </VALUES>\n        </SPEC-OBJECT>\n      </SPEC-OBJECTS>\n      <SPEC-RELATIONS>\n        <SPEC-RELATION IDENTIFIER="REL-001" LONG-NAME="satisfies">\n          <SOURCE><SPEC-OBJECT-REF>REQ-001</SPEC-OBJECT-REF></SOURCE>\n          <TARGET><SPEC-OBJECT-REF>REQ-002</SPEC-OBJECT-REF></TARGET>\n        </SPEC-RELATION>\n      </SPEC-RELATIONS>\n      <SPECIFICATIONS>\n        <SPECIFICATION IDENTIFIER="SPEC-001" LONG-NAME="Motor requirements" />\n      </SPECIFICATIONS>\n    </REQ-IF-CONTENT>\n  </CORE-CONTENT>\n</REQ-IF>\n'
    source = tmp_path / "requirements.reqif"
    source.write_text(reqif, encoding="utf-8")

    summary = inspect_reqif_file(source)
    assert summary["target_reqif_version"] == "1.2"
    assert summary["namespace_uri"] == "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
    assert summary["schema_urls"]["driver_xsd"].endswith("/20110402/driver.xsd")
    assert summary["counts"]["spec_objects"] == 1
    assert summary["counts"]["spec_relations"] == 1
    assert summary["requirement_samples"][0]["identifier"] == "REQ-001"

    output = tmp_path / "requirements.ttl"
    exported = export_reqif_to_ttl(source, output_path=output)
    assert exported["status"] == "exported"
    assert exported["target_reqif_version"] == "1.2"
    assert output.exists()
    assert "Bearing life requirement" in output.read_text(encoding="utf-8")
