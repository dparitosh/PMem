import ast
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from backend.Services.xmi_parser import XMIParser
from backend.tests.test_mbse_audit_fixes import load_source

HEADER = '<x:XMI xmlns:x="http://www.omg.org/XMI" xmlns:uml="http://www.omg.org/spec/UML/20131001" xmlns:s="urn:sysml">'


class XmiSysmlRegressions(unittest.TestCase):
    def setUp(self):
        self.adapter = load_source('backend/ceim/mbse_adapter.py', {
            'ET': ET, 'contract': SimpleNamespace(version='1', normalize_entity=lambda **kw: kw['record'],
                                                 normalize_relationship=lambda **kw: kw['record'])
        }, ('defusedxml', 'contract'))['mbse_to_ceim_batch']

    def parse(self, body):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'model.xmi'
            path.write_text(HEADER + body + '</x:XMI>')
            return XMIParser().parse(path)

    def test_comments_and_multiplicity_are_preserved(self):
        result = self.parse('<!-- note --><packagedElement x:id="a" x:type="uml:Class"><ownedAttribute x:id="p" x:type="uml:Property"><lowerValue value="0"/><upperValue value="*"/></ownedAttribute></packagedElement>')
        prop = next(node['properties'] for node in result['nodes'] if node['properties']['id'] == 'p')
        self.assertEqual((prop['lower'], prop['upper']), ('0', '*'))

    def test_duplicate_ids_rejected_by_both_parsers(self):
        body = '<packagedElement x:id="a" x:type="uml:Class"/><packagedElement x:id="a" x:type="uml:Class"/>'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.parse(body)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.adapter((HEADER + body + '</x:XMI>').encode(), version='1')

    def test_external_reference_never_becomes_local(self):
        with self.assertRaisesRegex(ValueError, 'External'):
            XMIParser()._normalize_ref('other.xmi#id')
        self.assertEqual(XMIParser()._normalize_ref('#id'), 'id')

    def test_type_attribute_order_and_child_dependency_refs(self):
        body = '<ownedAttribute type="a" x:type="uml:Property" x:id="p"/><packagedElement x:id="a" x:type="uml:Class"/><packagedElement x:id="r" x:type="uml:Class"/><packagedElement x:id="d" x:type="uml:Dependency"><client x:idref="a"/><supplier x:idref="r"/></packagedElement><s:Requirement base_Class="r"/><s:Satisfy base_Dependency="d"/>'
        batch = self.adapter((HEADER + body + '</x:XMI>').encode(), version='1')
        self.assertEqual(batch['entities'][0]['attributes']['model_type'], 'Property')
        self.assertEqual(next(entity for entity in batch['entities'] if entity['source_id'] == 'r')['source_type'], 'Requirement')
        self.assertIn({'source_type': 'SATISFIES', 'source_id': 'a', 'target_id': 'r'}, batch['relationships'])

    def test_plain_classifier_reference_is_not_a_metaclass(self):
        batch = self.adapter((HEADER + '<ownedAttribute type="a" x:id="p"/>' + '</x:XMI>').encode(), version='1')
        self.assertEqual(batch['entities'][0]['attributes']['model_type'], 'ownedAttribute')

    def test_wrong_root_and_dtd_rejected(self):
        for content in [b'<Other><item id="a"/></Other>', b'<!DOCTYPE XMI><XMI/>']:
            with self.assertRaises(ValueError):
                self.adapter(content, version='1')

    def test_memberships_are_not_requirements(self):
        batch = self.adapter(json.dumps([{'@id': 'm', '@type': 'RequirementVerificationMembership'},
                                       {'@id': 'r', '@type': 'RequirementUsage'}]).encode(), version='2')
        self.assertEqual([entity['source_type'] for entity in batch['entities']], ['Element', 'Requirement'])

    def test_ontology_resource_identity_is_not_lossy(self):
        tree = ast.parse(Path('backend/Services/owl_xmi_engine.py').read_text(encoding='utf-8-sig'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_xmi_identity_name')
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<XMI identity>', 'exec'), scope)
        encode = scope['_xmi_identity_name']
        ids = ['a-b', 'a_b', 'a.b', 'a:b', 'a/b', 'a%2Fb', '1', '_1']
        self.assertEqual(len({encode(identifier) for identifier in ids}), len(ids))
        self.assertEqual(encode('a/b'), 'a%2Fb')
        with self.assertRaises(ValueError):
            encode('')


if __name__ == '__main__':
    unittest.main()
