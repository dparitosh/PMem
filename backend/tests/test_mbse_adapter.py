import json
import pytest
from backend.ceim.mbse_adapter import mbse_to_ceim_batch
from backend.ceim.reqif_adapter import reqif_to_ceim_batch


def test_v1_preserves_requirement_and_satisfaction():
    data = b'<x:XMI xmlns:x="http://www.omg.org/XMI" xmlns:s="urn:sysml"><packagedElement x:id="b" x:type="uml:Class" name="Block"/><packagedElement x:id="r" x:type="uml:Class"/><packagedElement x:id="d" x:type="uml:Dependency" client="b" supplier="r"/><s:Requirement base_Class="r"/><s:Satisfy base_Dependency="d"/></x:XMI>'
    batch = mbse_to_ceim_batch(data, version='1')
    assert next(e for e in batch['entities'] if e['id'].endswith(':r'))['ceim_type'] == 'Requirement'
    assert batch['relationships'][0]['relationship'] == 'SATISFIES'


def test_v2_preserves_containment_and_rejects_missing_owner():
    data = [{'@id': 'p', '@type': 'Package'}, {'@id': 'r', '@type': 'RequirementUsage', 'owner': {'@id': 'p'}}]
    batch = mbse_to_ceim_batch(json.dumps(data).encode(), version='2')
    assert batch['relationships'][0]['relationship'] == 'HAS_PART'
    assert batch['entities'][1]['ceim_type'] == 'Requirement'
    with pytest.raises(ValueError, match='unresolved'):
        mbse_to_ceim_batch(json.dumps(data[1:]).encode(), version='2')


def test_reqif_nested_references():
    batch = reqif_to_ceim_batch(b'<REQ-IF><SPEC-OBJECT IDENTIFIER="a"/><SPEC-OBJECT IDENTIFIER="b"/><SPEC-RELATION><SOURCE><SPEC-OBJECT-REF>a</SPEC-OBJECT-REF></SOURCE><TARGET><SPEC-OBJECT-REF>b</SPEC-OBJECT-REF></TARGET></SPEC-RELATION></REQ-IF>')
    assert len(batch['relationships']) == 1
