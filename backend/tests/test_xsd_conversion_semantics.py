import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from unittest.mock import patch
import sys
import os
import logging
from backend.Services.xsd_semantics import element_particles, inspect_conversion_schemas, expand_model_groups, consolidated_element_particles

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
            for bounds in ('minOccurs="-1"', 'minOccurs="2" maxOccurs="1"', 'minOccurs="2"'):
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
                 '_local': lambda value: value.split(':')[-1], '_rdf_list': rdf_list, 'element_particles': element_particles}
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

    def test_repeating_choice_reports_limitation_without_false_exclusivity(self):
        function, graph, cfg, _, _ = self.choice_function()
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:choice maxOccurs="unbounded"><xs:element name="a"/></xs:choice></xs:complexType>')
        function(graph, cfg, root, 'Owner', 'Owner')
        self.assertFalse(any(predicate == 'xone' for _, predicate, _ in graph.add.__self__))
        self.assertTrue(any('Conversion limitation' in str(value) for _, _, value in graph.add.__self__))

    def test_group_reference_preserves_occurrence_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.schema(directory, 'a.xsd', '<xs:group name="Fields"><xs:sequence><xs:element name="value" type="xs:string" maxOccurs="2"/></xs:sequence></xs:group><xs:complexType name="Owner"><xs:group ref="Fields" minOccurs="0" maxOccurs="3"/></xs:complexType>')
            root = expand_model_groups([path])[path]
            rows = list(element_particles(root.find(X+'complexType')))
            self.assertEqual([(element.get('name'), low, high) for element, low, high in rows], [('value', '0', '6')])

    def test_group_cycles_and_missing_dependencies_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            for declaration, error in [('<xs:group name="Loop"><xs:sequence><xs:group ref="Loop"/></xs:sequence></xs:group>', 'Cyclic'), ('', 'Unresolved')]:
                path = self.schema(directory, 'a.xsd', declaration+'<xs:complexType name="Owner"><xs:group ref="Loop"/></xs:complexType>')
                with self.assertRaisesRegex(ValueError, error):
                    expand_model_groups([path])

    def test_repeating_choice_multiplies_branch_upper_bound(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:choice maxOccurs="3"><xs:element name="a" maxOccurs="2"/></xs:choice></xs:complexType>')
        self.assertEqual([(low, high) for _, low, high in element_particles(root)], [('1', '6')])

    def test_namespace_qualified_group_resolves_supplied_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            dependency = self.schema(directory, 'fields.xsd', '<xs:group name="Fields"><xs:sequence><xs:element name="external" type="xs:string"/></xs:sequence></xs:group>', 'urn:fields')
            owner = self.schema(directory, 'owner.xsd', '<xs:complexType name="Owner" xmlns:f="urn:fields"><xs:group ref="f:Fields"/></xs:complexType>')
            root = expand_model_groups([owner, dependency])[owner]
            self.assertEqual([element.get('name') for element, _, _ in element_particles(root.find(X+'complexType'))], ['external'])

    def test_bundled_domain_model_group_references_expand(self):
        path = Path(__file__).resolve().parents[2] / 'data/domain_models/managed_model_based_3d_engineering_domain/DomainModel.xsd'
        root = expand_model_groups([path])[path]
        self.assertGreater(len(root.findall(X+'complexType')), 100)
        self.assertFalse(any(node.get('ref') for node in root.iter(X+'group')))

    def test_chameleon_include_resolves_group_in_owner_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            dependency = Path(directory) / 'fields.xsd'
            dependency.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:group name="Fields"><xs:sequence><xs:element name="value" type="xs:string"/></xs:sequence></xs:group></xs:schema>')
            owner = self.schema(directory, 'owner.xsd', '<xs:include schemaLocation="fields.xsd"/><xs:complexType name="Owner" xmlns:o="urn:test"><xs:group ref="o:Fields"/></xs:complexType>')
            root = expand_model_groups([owner, dependency])[owner]
            self.assertEqual([element.get('name') for element, _, _ in element_particles(root.find(X+'complexType'))], ['value'])

    def test_single_branch_choice_preserves_required_minimum(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:choice minOccurs="2" maxOccurs="3"><xs:element name="a" minOccurs="2" maxOccurs="2"/></xs:choice></xs:complexType>')
        self.assertEqual([(low, high) for _, low, high in element_particles(root)], [('4', '6')])

    def test_zero_group_occurrences_suppress_unbounded_child(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:sequence minOccurs="0" maxOccurs="0"><xs:element name="a" maxOccurs="unbounded"/></xs:sequence></xs:complexType>')
        self.assertEqual([(low, high) for _, low, high in element_particles(root)], [('0', '0')])

    def test_utf16_dtd_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'unsafe.xsd'
            path.write_bytes('<!DOCTYPE schema [<!ENTITY value "unsafe">]><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'.encode('utf-16'))
            with self.assertRaisesRegex(ValueError, 'DOCTYPE'):
                inspect_conversion_schemas([path])

    def test_repeated_property_combines_bounds_instead_of_intersecting_them(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:sequence><xs:element name="a" type="xs:string"/><xs:element name="a" type="xs:string"/></xs:sequence></xs:complexType>')
        self.assertEqual([(low, high) for _, low, high in consolidated_element_particles(root)], [('2', '2')])
        function, graph, cfg, triples, _ = self.choice_function()
        function(graph, cfg, root, 'Owner', 'Owner')
        self.assertFalse(any(predicate == 'xone' for _, predicate, _ in triples))

    def test_conflicting_repeated_property_types_fail_explicitly(self):
        root = ET.fromstring('<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:sequence><xs:element name="a" type="xs:string"/><xs:element name="a" type="xs:int"/></xs:sequence></xs:complexType>')
        with self.assertRaisesRegex(ValueError, 'conflicting declarations'):
            list(consolidated_element_particles(root))

    def discovery_function(self):
        source = Path(__file__).resolve().parents[1] / 'Services/owl_xsd_engine.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_discover_related_xsds')
        scope = {'Path': Path, 'os': os, 'ET': ET, 'XSD_PRE': X, 'logger': logging.getLogger(__name__)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
        return scope['_discover_related_xsds']

    def test_dependency_discovery_rejects_directory_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            approved = Path(directory) / 'approved'
            approved.mkdir()
            outside = self.schema(directory, 'outside.xsd', '')
            owner = self.schema(approved, 'owner.xsd', '<xs:include schemaLocation="../outside.xsd"/>')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                self.discovery_function()([owner])

    def test_dependency_discovery_preserves_local_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            nested = Path(directory) / 'nested'
            nested.mkdir()
            dependency = self.schema(nested, 'fields.xsd', '')
            owner = self.schema(directory, 'owner.xsd', '<xs:include schemaLocation="nested/fields.xsd"/>')
            self.assertEqual(self.discovery_function()([owner]), [owner.resolve(), dependency.resolve()])

    def test_dependency_discovery_rejects_unsafe_xml_before_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'unsafe.xsd'
            source.write_bytes('<!DOCTYPE schema [<!ENTITY value "unsafe">]><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'.encode('utf-16'))
            with self.assertRaisesRegex(ValueError, 'DOCTYPE'):
                self.discovery_function()([source])

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
