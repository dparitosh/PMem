"""AP242 correctness regressions runnable without database/service dependencies."""
import ast
import json
import tempfile
import unittest
import sys
import types
import xml.etree.ElementTree as ET
from unittest.mock import patch
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from backend.Services.step_parser import parse_step_with_pmi, _first_number, extract_step_strings
from backend.parsers.ap242_identity import is_ap242

HEADER = "ISO-10303-21;HEADER;FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));ENDSEC;DATA;"


class MappingContract:
    version = 'test'

    def __init__(self):
        self.pack = json.loads((Path(__file__).resolve().parents[2] / 'data/ceim/mapping-packs/ap242.json').read_text())

    def normalize_entity(self, *, standard, record):
        mapping = self.pack['entities'][record['source_type']]
        properties = {}
        for source, target in mapping['properties'].items():
            value = record['source_id'] if source == '$source_id' else record['attributes'].get(source)
            if value not in (None, ''):
                properties[target] = value
        return {'id': f"{standard}:{record['source_id']}", 'ceim_type': mapping['ceim_type'], 'properties': properties}

    def normalize_relationship(self, *, standard, record):
        return {'source_id': f"{standard}:{record['source_id']}", 'target_id': f"{standard}:{record['target_id']}",
                'relationship': self.pack['relationships'][record['source_type']]['relationship']}


def adapter():
    # Load the real adapter functions while replacing the database-linked contract.
    path = Path(__file__).resolve().parents[1] / 'ceim/ap242_adapter.py'
    tree = ast.parse(path.read_text())
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    scope = dict(Path=Path, NamedTemporaryFile=NamedTemporaryFile, Any=Any, CEIMContract=MappingContract,
                 contract=MappingContract(), parse_step_with_pmi=parse_step_with_pmi, is_ap242=is_ap242,
                 extract_step_strings=extract_step_strings)
    exec(compile(tree, str(path), 'exec'), scope)
    return scope['ap242_to_ceim_batch']


class AP242AuditTests(unittest.TestCase):
    def parse(self, body):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'source.stp'
            path.write_text(HEADER + body + 'ENDSEC;END-ISO-10303-21;', encoding='utf-8')
            return parse_step_with_pmi(path)

    def test_duplicate_and_malformed_records_fail(self):
        for body in ("#1=PRODUCT('a','first','',());#1=PRODUCT('b','second','',());",
                     "#1=PRODUCT('a','ok','',());#2=BROKEN(;", '#1=BROKEN;'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.parse(body)

    def test_quoted_comments_references_and_section_markers_are_data(self):
        doc = self.parse("#1=PRODUCT('business','keep /*text*/ #999 ENDSEC;','',());")
        self.assertEqual(doc.cad_products[0].name, 'keep /*text*/ #999 ENDSEC;')
        self.assertEqual(doc.entities[0].ref_ids, [])

    def test_compound_arguments_are_not_truncated(self):
        body = "#1=(LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.),#2) REPRESENTATION_ITEM('" + 'x' * 600 + "'));#2=SI_UNIT(.MILLI.,.METRE.);"
        self.assertGreater(len(self.parse(body).entities[0].raw_args), 600)

    def test_nonfinite_and_false_standard_are_rejected(self):
        with self.assertRaises(ValueError):
            _first_number('1.E999')
        self.assertFalse(is_ap242('AUTOMOTIVE_DESIGN', '', b'/* AP242 */'))

    def test_unit_and_offsets_survive_mapping_without_fake_limits(self):
        body = "#1=SHAPE_ASPECT('hole','',#9,.T.);#2=DIMENSIONAL_SIZE(#1,'diameter');#3=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(-0.2),#5);#4=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.05),#5);#5=SI_UNIT(.MILLI.,.METRE.);#6=TOLERANCE_VALUE(#3,#4);#7=PLUS_MINUS_TOLERANCE(#6,#2);#9=PRODUCT('part','Part','',());"
        dim = self.parse(body).dimensions[0]
        self.assertEqual((dim.unit, dim.lower_tolerance, dim.upper_tolerance), ('mm', -0.2, 0.05))
        batch = adapter()((HEADER + body + 'ENDSEC;END-ISO-10303-21;').encode())
        props = next(row['properties'] for row in batch['entities'] if row['id'] == 'ap242:2')
        self.assertEqual(props['lower_tolerance'], -0.2)
        self.assertNotIn('lower_limit', props)

    def test_assembly_direction_and_business_identifier_survive(self):
        body = "#1=PRODUCT_DEFINITION('parent','',#3,#4);#2=PRODUCT_DEFINITION('child','',#3,#4);#3=PRODUCT_DEFINITION_FORMATION('rev','',#5);#4=PRODUCT_DEFINITION_CONTEXT('ctx',#6,'design');#5=PRODUCT('business-part','Part','',());#6=APPLICATION_CONTEXT('ctx');#7=NEXT_ASSEMBLY_USAGE_OCCURRENCE('occ','child','',#1,#2,$);"
        batch = adapter()((HEADER + body + 'ENDSEC;END-ISO-10303-21;').encode())
        self.assertEqual([r for r in batch['relationships'] if r['relationship'] == 'HAS_PART'], [{'source_id': 'ap242:1', 'target_id': 'ap242:2', 'relationship': 'HAS_PART'}])
        self.assertIn({'source_id': 'ap242:3', 'target_id': 'ap242:5', 'relationship': 'DERIVED_FROM'}, batch['relationships'])
        self.assertEqual(next(row['properties']['external_id'] for row in batch['entities'] if row['id'] == 'ap242:5'), 'business-part')

    def test_empty_semantic_batch_is_rejected(self):
        with self.assertRaises(ValueError):
            adapter()((HEADER + 'ENDSEC;END-ISO-10303-21;').encode())

    def test_governed_import_rejects_dangling_references(self):
        with self.assertRaisesRegex(ValueError, 'unresolved STEP'):
            adapter()((HEADER + "#1=PRODUCT('id','Part','',(#999));ENDSEC;END-ISO-10303-21;").encode())

    def test_annotation_text_and_surface_finish_are_retained(self):
        body = "#1=ANNOTATION_TEXT_OCCURRENCE('note','Machined','Ra 1.6');#2=SURFACE_FINISH(1.6,#3);#3=SI_UNIT(.MICRO.,.METRE.);"
        batch = adapter()((HEADER + body + 'ENDSEC;END-ISO-10303-21;').encode())
        props = {row['id']: row['properties'] for row in batch['entities']}
        self.assertEqual(props['ap242:1']['text'], 'Ra 1.6')
        self.assertEqual(props['ap242:2']['unit'], 'um')

    def test_part28_alias_order_and_duplicates(self):
        # Trusted fixtures exercise alias logic with the same iterparse interface.
        # This does not test defusedxml's security behavior or XSD conformance.
        package = types.ModuleType('defusedxml')
        package.ElementTree = ET
        fixtures = [
            ('<Uos><Product id="first"/><Product id="second"/><ToleranceValue id="t" refs="second first"/></Uos>', False),
            ('<Uos><Product id="same"/><Product id="same"/></Uos>', True),
        ]
        with patch.dict(sys.modules, {'defusedxml': package, 'defusedxml.ElementTree': ET}):
            for content, invalid in fixtures:
                with self.subTest(content=content), tempfile.TemporaryDirectory() as root:
                    path = Path(root) / 'source.stpx'
                    path.write_text(content)
                    if invalid:
                        with self.assertRaisesRegex(ValueError, 'Duplicate Part-28'):
                            parse_step_with_pmi(path)
                    else:
                        doc = parse_step_with_pmi(path)
                        tolerance = next(e for e in doc.entities if e.entity_type == 'TOLERANCE_VALUE')
                        self.assertEqual(tolerance.ref_ids, [3, 2])


if __name__ == '__main__':
    unittest.main()
