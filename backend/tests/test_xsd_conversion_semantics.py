import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from unittest.mock import patch
import sys
from backend.Services.xsd_semantics import element_particles, inspect_conversion_schemas

X = '{http://www.w3.org/2001/XMLSchema}'


class ConversionSemanticsTests(unittest.TestCase):
    def schema(self, directory, name, body, namespace='urn:test'):
        path = Path(directory) / name
        path.write_text(f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="{namespace}">{body}</xs:schema>', encoding='utf-8')
        return path

    def test_namespace_collisions_and_primitive_shadowing_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            a = self.schema(directory, 'a.xsd', '<xs:complexType name="Item"/>', 'urn:a')
            b = self.schema(directory, 'b.xsd', '<xs:complexType name="Item"/>', 'urn:b')
            with self.assertRaisesRegex(ValueError, 'Namespace collision'):
                inspect_conversion_schemas([a, b])
            c = self.schema(directory, 'c.xsd', '<xs:simpleType name="string"/>')
            with self.assertRaisesRegex(ValueError, 'shadows'):
                inspect_conversion_schemas([c], {'string'})

    def test_unsupported_overrides_fail_and_facets_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.schema(directory, 'a.xsd', '<xs:redefine/>')
            with self.assertRaisesRegex(ValueError, 'unsupported xs:redefine'):
                inspect_conversion_schemas([path])
            path = self.schema(directory, 'a.xsd', '<xs:pattern value="[A-Z]+"/>')
            self.assertIn('xs:pattern', inspect_conversion_schemas([path])[0])

    def test_invalid_occurrence_bounds_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            for bounds in ('minOccurs="-1"', 'minOccurs="2" maxOccurs="1"'):
                path = self.schema(directory, 'a.xsd', f'<xs:element name="a" {bounds}/>')
                with self.assertRaises(ValueError): inspect_conversion_schemas([path])

    def test_optional_repeating_compositor_preserves_bounds_and_anonymous_ownership(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:sequence minOccurs="0" maxOccurs="3"><xs:element name="a" minOccurs="2" maxOccurs="4"><xs:complexType><xs:element name="nested"/></xs:complexType></xs:element></xs:sequence></xs:complexType>')
        rows = list(element_particles(root))
        self.assertEqual([(row[0].get('name'), row[1], row[2]) for row in rows], [('a', '0', '12')])

    def test_choice_does_not_require_every_branch(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:choice><xs:element name="a"/><xs:element name="b"/></xs:choice></xs:complexType>')
        self.assertEqual([row[1] for row in element_particles(root)], ['0', '0'])

    def choice_function(self):
        # Exercise actual graph-emission code without requiring local RDF packages.
        class Terms:
            def __getattr__(self, key): return key
            def __getitem__(self, key): return key
        triples = set()
        counter = iter(range(1000))
        lists = []
        def rdf_list(graph, values):
            lists.append(values)
            return ('list', len(lists))
        scope = {'XSD_PRE': X, 'SH': Terms(), 'RDF': Terms(), 'RDFS': Terms(), 'XSD': Terms(),
                 'BNode': lambda: ('blank', next(counter)), 'Literal': lambda value, **kwargs: value,
                 '_local': lambda value: value.split(':')[-1], '_rdf_list': rdf_list}
        tree = ast.parse(Path('backend/Services/owl_xsd_engine.py').read_text(encoding='utf-8'))
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_add_choice_constraints')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'choices', 'exec'), scope)
        return scope['_add_choice_constraints'], SimpleNamespace(add=triples.add), SimpleNamespace(prop_uri=lambda owner, name: owner + ':' + name), triples, lists

    def test_choice_emits_exclusive_shape_and_optional_none_branch(self):
        function, graph, cfg, triples, lists = self.choice_function()
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:choice minOccurs="0"><xs:element name="a"/><xs:element name="b"/></xs:choice></xs:complexType>')
        function(graph, cfg, root, 'Owner', 'Owner')
        self.assertEqual(len(lists[0]), 3)
        self.assertTrue(any(predicate == 'xone' for _, predicate, _ in triples))
        self.assertEqual(sum(predicate == 'minCount' for _, predicate, _ in triples), 2)

    def test_repeating_choice_is_rejected(self):
        function, graph, cfg, _, _ = self.choice_function()
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:choice maxOccurs="unbounded"><xs:element name="a"/></xs:choice></xs:complexType>')
        with self.assertRaisesRegex(ValueError, 'cannot be faithfully'):
            function(graph, cfg, root, 'Owner', 'Owner')

    def test_generation_validation_fails_closed(self):
        tree = ast.parse(Path('backend/Services/owl_generation_service.py').read_text(encoding='utf-8'))
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_read_and_validate')
        scope = {'__name__': 'backend.Services.owl_generation_service', '__package__': 'backend.Services',
                 'Path': Path, 'Tuple': tuple, 'Dict': dict, 'Any': object}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'validation', 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'model.ttl'
            source.write_text('@prefix ex: <urn:test:> .', encoding='utf-8')
            for result in (False, True):
                validator = SimpleNamespace(validate_file=lambda path, valid=result: SimpleNamespace(to_dict=lambda: {'valid': valid}))
                module = SimpleNamespace(OntologyValidator=lambda: validator)
                with patch.dict(sys.modules, {'backend.Services.ontology_validator': module}):
                    if result:
                        self.assertTrue(scope['_read_and_validate'](source)[1]['valid'])
                    else:
                        with self.assertRaisesRegex(ValueError, 'failed validation'):
                            scope['_read_and_validate'](source)
            validator = SimpleNamespace(validate_file=lambda path: (_ for _ in ()).throw(RuntimeError('unavailable')))
            with patch.dict(sys.modules, {'backend.Services.ontology_validator': SimpleNamespace(OntologyValidator=lambda: validator)}):
                with self.assertRaisesRegex(ValueError, 'could not be completed'):
                    scope['_read_and_validate'](source)
