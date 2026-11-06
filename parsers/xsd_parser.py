"""XSD parser: parse XSD bytes into an intermediate model and produce a source RDF graph."""
from lxml import etree
from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
from rdflib.namespace import OWL, XSD as XSD_NS
from typing import Dict, Any, Tuple, List
import uuid
import hashlib
from urllib.parse import quote

XS = Namespace('http://www.w3.org/2001/XMLSchema#')
SRC = Namespace('http://example.org/source/')


class XSDParser:
    @staticmethod
    def parse_bytes(content: bytes, filename: str = '') -> Dict[str, Any]:
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
        root = etree.fromstring(content, parser=parser)
        if root.getroottree().docinfo.doctype:
            raise ValueError('DTD declarations are not supported')
        if root.tag != '{http://www.w3.org/2001/XMLSchema}schema':
            raise ValueError('Expected an XML Schema root')
        model = {
            'types': {},
            'elements': {},
            'attributes': {},
            'source_file': filename,
            'target_namespace': root.get('targetNamespace', ''),
            'source_id': hashlib.sha256(content).hexdigest(),
        }
        nsmap = root.nsmap
        def identity(node):
            name = node.get('name') or node.get('ref') or 'anonymous'
            return name if node.getparent() is root else node.getroottree().getpath(node)
        def type_uri(node):
            value = node.get('type')
            if not value:
                return None
            prefix, local = value.split(':', 1) if ':' in value else (None, value)
            namespace = node.nsmap.get(prefix)
            if namespace == 'http://www.w3.org/2001/XMLSchema':
                namespace += '#'
            return namespace + local if namespace else None

        # find complexTypes and simpleTypes
        for ct in root.findall('.//{http://www.w3.org/2001/XMLSchema}complexType'):
            name = identity(ct)
            model['types'][name] = {
                'kind': 'complex',
                'xml': etree.tostring(ct, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        for st in root.findall('.//{http://www.w3.org/2001/XMLSchema}simpleType'):
            name = identity(st)
            model['types'][name] = {
                'kind': 'simple',
                'xml': etree.tostring(st, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        for el in root.findall('.//{http://www.w3.org/2001/XMLSchema}element'):
            name = identity(el)
            model['elements'][name] = {
                'type': el.get('type'),
                'type_uri': type_uri(el),
                'minOccurs': el.get('minOccurs'),
                'maxOccurs': el.get('maxOccurs'),
                'xml': etree.tostring(el, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        # attributes
        for attr in root.findall('.//{http://www.w3.org/2001/XMLSchema}attribute'):
            name = identity(attr)
            model['attributes'][name] = {
                'type': attr.get('type'),
                'use': attr.get('use'),
                'xml': etree.tostring(attr, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        return model

    @staticmethod
    def model_to_source_graph(model: Dict[str, Any]) -> Graph:
        g = Graph()
        g.bind('src', SRC)
        g.bind('owl', OWL)
        g.bind('xsd', XSD_NS)

        scope = model.get('source_id') or hashlib.sha256(str(model).encode('utf-8')).hexdigest()
        source_uri = URIRef(SRC[scope])
        g.add((source_uri, RDF.type, SRC.SourceSchema))

        # Complex/simple types -> owl:Class in source ontology
        for tname, tinfo in model.get('types', {}).items():
            c = URIRef(SRC[scope + '/type/' + quote(tname, safe='')])
            g.add((c, RDF.type, OWL.Class))
            g.add((c, RDFS.label, Literal(tname)))
            g.add((c, SRC.sourceXml, Literal(tinfo.get('xml'))))

        # elements -> properties
        for ename, einfo in model.get('elements', {}).items():
            p = URIRef(SRC[scope + '/element/' + quote(ename, safe='')])
            # choose object vs datatype by type hint presence
            datatype = str(einfo.get('type_uri') or '').startswith(str(XSD_NS))
            if einfo.get('type_uri') and not datatype:
                g.add((p, RDF.type, OWL.ObjectProperty))
            else:
                g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(ename)))
            g.add((p, SRC.sourceXml, Literal(einfo.get('xml'))))

        # attributes
        for aname, ainfo in model.get('attributes', {}).items():
            p = URIRef(SRC[scope + '/attribute/' + quote(aname, safe='')])
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(aname)))
            g.add((p, SRC.sourceXml, Literal(ainfo.get('xml'))))

        return g
