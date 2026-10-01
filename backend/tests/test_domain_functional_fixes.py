import ast
import hashlib
import json
import os
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
import importlib.util
spec = importlib.util.spec_from_file_location('ceim_identity', 'backend/ceim/identity.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
scope_batch = identity.scope_batch

def extract(path, class_name, methods):
    cls = next(n for n in ast.parse(Path(path).read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef) and n.name==class_name)
    cls.body = [n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in methods]
    return ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),cls],type_ignores=[]))

class DomainFixes(unittest.TestCase):
    def test_identity_is_scoped_idempotent_and_relationships_remapped(self):
        entities=[{'id':'qif:1','provenance':{}},{'id':'qif:2','provenance':{}}]
        edges=[{'source_id':'qif:1','target_id':'qif:2','provenance':{}}]
        with patch.dict(os.environ,{'DEPO_TENANT_ID':'tenant','DEPO_PROJECT_ID':'project'},clear=True):
            a, links=scope_batch(entities,edges,source_system='system-a')
            b, _=scope_batch(entities,edges,source_system='system-b')
            self.assertNotEqual(a[0]['id'],b[0]['id'])
            self.assertEqual(links[0]['source_id'],a[0]['id'])
            self.assertEqual(scope_batch(a,links,source_system='system-a'),(a,links))
            with self.assertRaises(ValueError): scope_batch(a,links,source_system='system-b')
            with self.assertRaises(ValueError): scope_batch(entities,edges,required=True)
            self.assertEqual(scope_batch(entities,edges),(entities,edges))

    def test_xml_attributes_namespaces_and_legacy_text(self):
        namespace={}
        exec(compile(extract('backend/ingestion_service/profiles.py','SourceProfileStore',{'_xml_record','_local_name','_value_at'}),'profiles.py','exec'),namespace)
        profile=namespace['SourceProfileStore']()
        record=profile._xml_record(ET.fromstring('<M xmlns:a="urn:a" xmlns:b="urn:b"><a:Value unit="mm">3.2</a:Value><b:Value unit="inch">1</b:Value></M>'))
        self.assertEqual(record['Value'],['3.2','1'])
        self.assertEqual(profile._value_at(record,'Value_attributes.0.unit'),'mm')
        self.assertEqual(record['_xml']['children'][0]['tag'],'{urn:a}Value')
        self.assertEqual(record['_xml']['children'][1]['attributes']['unit'],'inch')

    def test_rdf_engineering_type_uses_current_entity(self):
        class Graph:
            def __init__(self): self.triples=[]
            def add(self,value): self.triples.append(value)
        class NS:
            def __init__(self,base): self.base=base
            def __getattr__(self,name): return self.base+name
            def __getitem__(self,name): return self.base+name
        namespace={'Graph':Graph,'Namespace':NS,'URIRef':str,'Literal':lambda value:value,'RDF':NS('rdf:'),'quote':quote,'hashlib':hashlib,'json':json,'normalize_record':lambda record:(dict(record),[]),'analyze_entities':lambda entities:{'blocking':False,'entities':entities}}
        exec(compile(extract('backend/ceim/contract.py','CEIMContract',{'to_rdf'}),'contract.py','exec'),namespace)
        entities=[{'id':'qif:1','ceim_type':'Characteristic','properties':{},'provenance':{'source_standard':'qif','source_type':'CharacteristicDefinition'}},{'id':'ap242:1','ceim_type':'Characteristic','properties':{},'provenance':{'source_standard':'ap242','source_type':'geometric_tolerance'}}]
        contract=SimpleNamespace(namespace='urn:test:',entity_types={'Characteristic'},_predicate_name=lambda value:value)
        for ordered in (entities,list(reversed(entities))):
            triples=namespace['CEIMContract'].to_rdf(contract,entities=ordered,relationships=[]).triples
            self.assertIn(('urn:test:entity/qif%3A1','rdf:type','https://depo.example.org/ontology/bill-of-characteristics/1.0/Characteristic'),triples)
            self.assertIn(('urn:test:entity/ap242%3A1','rdf:type','https://depo.example.org/ontology/bill-of-characteristics/1.0/TolerancedCharacteristic'),triples)

if __name__ == '__main__': unittest.main()
