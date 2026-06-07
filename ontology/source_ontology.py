"""Create a source ontology graph from parser model."""
from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
from rdflib.namespace import OWL
from typing import Dict, Any

SRC = Namespace('http://example.org/source/')


class SourceOntology:
    @staticmethod
    def build_from_model(model: Dict[str, Any]) -> Graph:
        g = Graph()
        g.bind('src', SRC)
        g.bind('owl', OWL)

        # re-use parser helper: assume parser produced source triples already
        # This module can enrich with provenance and schema metadata.
        for tname, tinfo in model.get('types', {}).items():
            c = URIRef(SRC['type/' + tname])
            g.add((c, RDF.type, OWL.Class))
            g.add((c, RDFS.label, Literal(tname)))
            g.add((c, SRC.sourceXml, Literal(tinfo.get('xml'))))

        for ename, einfo in model.get('elements', {}).items():
            p = URIRef(SRC['element/' + ename])
            g.add((p, RDFS.label, Literal(ename)))
            g.add((p, SRC.sourceXml, Literal(einfo.get('xml'))))

        return g
