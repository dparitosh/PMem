"""XSD parser: parse XSD bytes into an intermediate model and produce a source RDF graph."""
from lxml import etree
from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
from rdflib.namespace import OWL, XSD as XSD_NS
from typing import Dict, Any, Tuple, List
import uuid

XS = Namespace('http://www.w3.org/2001/XMLSchema#')
SRC = Namespace('http://example.org/source/')


class XSDParser:
    @staticmethod
    def parse_bytes(content: bytes, filename: str = '') -> Dict[str, Any]:
        root = etree.fromstring(content)
        model = {
            'types': {},
            'elements': {},
            'attributes': {},
            'source_file': filename,
        }
        nsmap = root.nsmap

        # find complexTypes and simpleTypes
        for ct in root.findall('.//{http://www.w3.org/2001/XMLSchema}complexType'):
            name = ct.get('name') or str(uuid.uuid4())
            model['types'][name] = {
                'kind': 'complex',
                'xml': etree.tostring(ct, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        for st in root.findall('.//{http://www.w3.org/2001/XMLSchema}simpleType'):
            name = st.get('name') or str(uuid.uuid4())
            model['types'][name] = {
                'kind': 'simple',
                'xml': etree.tostring(st, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        for el in root.findall('.//{http://www.w3.org/2001/XMLSchema}element'):
            name = el.get('name') or str(uuid.uuid4())
            model['elements'][name] = {
                'type': el.get('type'),
                'minOccurs': el.get('minOccurs'),
                'maxOccurs': el.get('maxOccurs'),
                'xml': etree.tostring(el, pretty_print=False).decode('utf-8'),
                'source': filename,
            }

        # attributes
        for attr in root.findall('.//{http://www.w3.org/2001/XMLSchema}attribute'):
            name = attr.get('name') or str(uuid.uuid4())
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

        source_uri = URIRef(SRC[model.get('source_file') or str(uuid.uuid4())])
        g.add((source_uri, RDF.type, SRC.SourceSchema))

        # Complex/simple types -> owl:Class in source ontology
        for tname, tinfo in model.get('types', {}).items():
            c = URIRef(SRC['type/' + tname])
            g.add((c, RDF.type, OWL.Class))
            g.add((c, RDFS.label, Literal(tname)))
            g.add((c, SRC.sourceXml, Literal(tinfo.get('xml'))))

        # elements -> properties
        for ename, einfo in model.get('elements', {}).items():
            p = URIRef(SRC['element/' + ename])
            # choose object vs datatype by type hint presence
            if einfo.get('type') and ':' in einfo.get('type'):
                g.add((p, RDF.type, OWL.ObjectProperty))
            else:
                g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(ename)))
            g.add((p, SRC.sourceXml, Literal(einfo.get('xml'))))

        # attributes
        for aname, ainfo in model.get('attributes', {}).items():
            p = URIRef(SRC['attribute/' + aname])
            g.add((p, RDF.type, OWL.DatatypeProperty))
            g.add((p, RDFS.label, Literal(aname)))
            g.add((p, SRC.sourceXml, Literal(ainfo.get('xml'))))

        return g
