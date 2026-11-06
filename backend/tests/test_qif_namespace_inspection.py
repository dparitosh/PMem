"""Exercise QIF inspection without installing the API service dependencies."""
import ast
from dataclasses import dataclass
from pathlib import Path
import io
from typing import Iterable
import tempfile
import unittest
from xml.etree import ElementTree as ET

source = Path(__file__).resolve().parents[1]/'qif/ontology_builder.py'
tree = ast.parse(source.read_text())
nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and getattr(node, 'name', '') in {'SchemaTerm', '_documentation', '_local_name', 'inspect_schema_set'}]
scope = dict(dataclass=dataclass, Path=Path, io=io, Iterable=Iterable, ET=ET, XS='{http://www.w3.org/2001/XMLSchema}')
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)


class QifInspectionTests(unittest.TestCase):
    def test_cross_namespace_property_types_keep_distinct_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for suffix in ('a', 'b'):
                path = Path(directory)/(suffix+'.xsd')
                path.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:'+suffix+'" targetNamespace="urn:'+suffix+'"><xs:complexType name="SharedType"/><xs:complexType name="Owner'+suffix+'"><xs:sequence><xs:element name="value" type="t:SharedType"/></xs:sequence></xs:complexType></xs:schema>')
                paths.append(path)
            result = scope['inspect_schema_set'](paths)
            self.assertFalse(result['errors'])
            terms = result['terms']
            shared = {term.namespace: term.name for term in terms if term.kind == 'complex_type' and term.name.startswith('ns_')}
            self.assertEqual(len(set(shared.values())), 2)
            for term in terms:
                if term.kind == 'property':
                    self.assertEqual(term.value_type, shared[term.namespace])
